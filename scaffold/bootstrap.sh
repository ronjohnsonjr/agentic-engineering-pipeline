#!/usr/bin/env bash
# bootstrap.sh
# Bootstraps a repo with the agentic-ci consumer workflows and minimal
# agent scaffold. Run from the root of the target repo.
#
# Usage:
#   curl -sL https://raw.githubusercontent.com/onyx-point/agentic-ci/main/scaffold/bootstrap.sh | bash
#   # or
#   ./bootstrap.sh
#
# What it does:
#   1. Creates .github/workflows/ with all agentic consumer workflows
#   2. Creates .claude/agents/ with minimal agent stubs
#   3. Reminds you to set CLAUDE_CODE_OAUTH_TOKEN as a repo secret

set -euo pipefail

AGENTIC_CI_RAW="https://raw.githubusercontent.com/onyx-point/agentic-ci/main"

echo "=== agentic-ci bootstrap ==="
echo ""

# ---- Create directories ----
mkdir -p .github/workflows
mkdir -p .claude/agents

# ---- Download consumer workflows ----
WORKFLOWS=(
  "agentic-pr-review.yml"
  "agentic-ci-remediate.yml"
  "agentic-issue-to-pr.yml"
  "agentic-quality-sweep.yml"
  "agentic-pr-describe.yml"
  "agentic-dependabot-review.yml"
  "agentic-stale-pr-nudge.yml"
  "agentic-repository-dispatch-linear.yml"
)

echo "Downloading consumer workflows..."
for wf in "${WORKFLOWS[@]}"; do
  if [ -f ".github/workflows/$wf" ]; then
    echo "  SKIP: .github/workflows/$wf (already exists)"
  else
    curl -sL "$AGENTIC_CI_RAW/examples/consumer-workflows/$wf" -o ".github/workflows/$wf"
    echo "  OK:   .github/workflows/$wf"
  fi
done

# ---- Create minimal agent stubs (only if .claude/agents/ is empty) ----
AGENT_COUNT=$(find .claude/agents/ -name "*.md" 2>/dev/null | wc -l)

if [ "$AGENT_COUNT" -eq 0 ]; then
  echo ""
  echo "Creating minimal agent stubs in .claude/agents/..."

  cat > .claude/agents/coder.md << 'AGENT'
---
name: coder
description: >
  Implementation agent. Reads CLAUDE.md for project conventions, writes
  code and tests, verifies with the repo's quality gates.
model: claude-sonnet-4-6
tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
---

You are an implementation engineer. Before writing any code:

1. Read the project CLAUDE.md (if it exists) for coding standards.
2. Follow the language and framework conventions of the existing codebase.

After implementation, run the repo's quality gate:
- If Makefile with `check` target: `make check`
- Else if pyproject.toml: `ruff check . && pytest`
- Else if package.json: `npm test`

Do not report completion if any checks fail.
AGENT

  cat > .claude/agents/verifier.md << 'AGENT'
---
name: verifier
description: >
  Run after ANY code changes. Executes the repo's quality gate and
  reports structured pass/fail. Never skip verification.
model: claude-haiku-4-5
tools:
  - Bash
  - Read
---

You are a verification agent. Detect the project type and run checks:

Python (pyproject.toml): ruff check . && ruff format --check . && mypy src/ && pytest
Node (package.json): npm test
Go (go.mod): go vet ./... && go test ./...
Rust (Cargo.toml): cargo clippy && cargo test
Makefile: make check (if target exists)

Report:
  VERIFICATION RESULT: [PASS | FAIL]

If PASS: test count and coverage (if available).
If FAIL: which command failed and the first 20 lines of error output.

Do not attempt to fix failures. Report and stop.
AGENT

  cat > .claude/agents/reviewer.md << 'AGENT'
---
name: reviewer
description: >
  Final quality gate before marking work complete. Checks conventions,
  security, and correctness. Returns APPROVED or CHANGES REQUIRED.
model: claude-sonnet-4-6
tools:
  - Read
  - Bash
  - Glob
  - Grep
---

You are an automated code reviewer. Review the current branch diff against
the default branch.

## Checklist

### Critical (blocking)
- Security: no hardcoded secrets, no shell injection, no unsafe deserialization
- Data safety: no PII in logs, no credentials in output
- Type safety: no unhandled None/null, no unsafe casts
- Tests: new code paths have corresponding tests

### Informational (non-blocking)
- Code quality: functions do one thing, DRY, no magic numbers
- Dead code: unused imports, unreachable branches
- Documentation: public APIs have docstrings/comments

## Report

```
REVIEW RESULT: [APPROVED | CHANGES REQUIRED]

BLOCKING ISSUES: (list with file:line or "none")
NON-BLOCKING COMMENTS: (list or "none")
SUMMARY: (2-3 sentence assessment)
```
AGENT

  echo "  OK:   .claude/agents/coder.md"
  echo "  OK:   .claude/agents/verifier.md"
  echo "  OK:   .claude/agents/reviewer.md"
else
  echo ""
  echo "SKIP: .claude/agents/ already has $AGENT_COUNT agent(s), not overwriting."
fi

# ---- Reminder ----
echo ""
echo "=== Bootstrap complete ==="
echo ""
echo "Next steps:"
echo "  1. Set CLAUDE_CODE_OAUTH_TOKEN as a repo secret:"
echo "     gh secret set CLAUDE_CODE_OAUTH_TOKEN"
echo ""
echo "  2. Review and customize the workflows in .github/workflows/agentic-*.yml"
echo "     - Update 'onyx-point/agentic-ci' to your org's agentic-ci repo"
echo "     - Adjust trigger conditions, timeouts, and inputs"
echo ""
echo "  3. Customize agent definitions in .claude/agents/ for your project's"
echo "     specific conventions, quality gates, and domain rules."
echo ""
echo "  4. (Optional) Add a CLAUDE.md to your repo root with project conventions."
echo "     Agents read this file before starting work."
echo ""
echo "  5. Commit and push:"
echo "     git add .github/workflows/agentic-*.yml .claude/agents/"
echo "     git commit -m 'chore: bootstrap agentic-ci workflows'"
echo "     git push"
