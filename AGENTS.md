# AGENTS.md

Guidance for AI agents working in this repository.

---

## Project Overview

This is **agentic-ci**: a collection of repo-agnostic, reusable GitHub Actions workflows that wire Claude-powered agentic loops into any CI/CD pipeline. The workflows are built on [claude-code-action](https://github.com/anthropics/claude-code-action) and the `.claude/agents/` convention for per-project behavior overrides.

Consumers copy thin caller workflows from `examples/consumer-workflows/` into their own `.github/workflows/`, then point the `uses:` key at the reusable workflows in this repo. All orchestration logic lives here; consumer files are intentionally minimal (5-20 lines).

**Workflows provided:**

| File | Trigger | Purpose |
|------|---------|---------|
| `pr-review.yml` | PR opened / ready | Copilot + Claude collaborative review cycle |
| `ci-remediate.yml` | CI check fails | Diagnose, fix, and verify failing CI checks |
| `issue-to-pr.yml` | Issue assigned / labeled | Full issue-to-PR autonomous implementation loop |
| `quality-sweep.yml` | Weekly schedule / dispatch | Dead code, unused imports, naming hygiene |
| `pr-describe.yml` | PR opened with empty body | Auto-generate rich PR description from diff |
| `dependabot-review.yml` | Dependabot PR opened | Changelog review and risk assessment |
| `stale-pr-nudge.yml` | Daily schedule | Find and nudge stale PRs with a status comment |

---

## Build Commands

This repo contains no compiled code. There is no build step.

To validate YAML workflow syntax locally:

```bash
# Lint all workflow files with actionlint (install separately)
actionlint .github/workflows/*.yml

# Or validate with the GitHub CLI (requires auth)
gh workflow list
```

To bootstrap a consumer repo from the scaffold:

```bash
./scaffold/bootstrap.sh
```

---

## Test Commands

There is no automated test suite in this repo. Correctness is validated by:

1. Running the example consumer workflows against a real GitHub repository.
2. Reviewing workflow run logs in the GitHub Actions UI.
3. Checking that `examples/consumer-workflows/` files remain syntactically valid YAML.

When modifying a reusable workflow, manually trigger the corresponding consumer workflow against a test repo before merging.

---

## Coding Conventions

### YAML Formatting

- **Indentation**: 2 spaces. Never use tabs.
- **Keys**: lowercase with hyphens (`timeout-minutes`, `fetch-depth`, `cancel-in-progress`).
- **Strings**: use double quotes for all `name:` fields and all values that contain GitHub expression syntax (`${{ ... }}`). Use single quotes or unquoted strings elsewhere.
- **Multiline strings**: use the `|` literal block scalar for `prompt:` fields. Keep the prompt body at one additional indent level.
- **Comments**: place a top-of-file block comment on every reusable workflow explaining its purpose and the `uses:` line a consumer needs. See existing files for the exact format.
- **Blank lines**: separate top-level keys (`on:`, `permissions:`, `jobs:`) with one blank line. Do not add blank lines inside `steps:` blocks unless separating logically distinct groups.

### Naming Patterns

**Workflow files** (reusable, in `.github/workflows/`):
- Lowercase, hyphen-separated, no prefix: `pr-review.yml`, `ci-remediate.yml`.

**Consumer workflow files** (in `examples/consumer-workflows/`):
- Prefixed with `agentic-`: `agentic-pr-review.yml`, `agentic-ci-remediate.yml`.

**Job IDs**: match the workflow filename without extension, hyphen-separated: `pr-review`, `ci-remediate`, `issue-to-pr`.

**Step names**: title case, imperative phrasing: `Checkout repository`, `Run Claude PR Review Orchestrator`, `Find associated PR`.

**Inputs**: lowercase, underscore-separated: `max_fix_rounds`, `auto_approve_patch`, `claude_args`.

**Concurrency groups**: prefixed with `agentic-<workflow-name>-` followed by a unique context key such as PR number or branch name.

**Agent override files** (consumed by workflows at runtime, stored in consumer repos under `.claude/agents/`): lowercase, hyphen-separated, named after the workflow that reads them: `pr-review-orchestrator.md`, `ci-remediate.md`, `quality-sweep.md`, `ship-pipeline.md`.

### Prompt Style in Workflows

- Structure prompts with `##` section headers.
- Use numbered lists for sequential steps and bullet lists for options or rules.
- Always include an `## Agent override` section that instructs Claude to read `.claude/agents/<name>.md` if it exists and to give it precedence over the generic instructions.
- Always include a `## Rules` section at the end of every prompt with hard constraints (never force push, never skip quality gates, etc.).
- Close every generated comment or PR body with an attribution footer: `*<action> by Claude via agentic-ci.*`

---

## Architecture Decisions

### Thin Callers vs. Fat Reusable Workflows

Consumer workflows (the files users copy into their own repos) are intentionally thin: they define triggers, a concurrency group, and a `uses:` reference. They contain no orchestration logic. All logic lives in the reusable workflows in this repo.

This separation means:
- Bug fixes and prompt improvements ship to all consumers by updating this repo at the pinned ref.
- Consumers can customize behavior without touching the shared workflows.
- Diffs on consumer files stay small and reviewable.

**Do not** move orchestration logic (prompt content, step sequences, quality gate detection) into consumer workflows. If a consumer needs different behavior, they should use the `.claude/agents/` override pattern (see below).

### The `.claude/agents/` Override Pattern

Every reusable workflow prompt contains an `## Agent override` section. At runtime, Claude checks the checked-out consumer repo for a named agent file (e.g., `.claude/agents/ci-remediate.md`). If the file exists, its instructions take precedence over the generic prompt for any conflicts.

This means:
- Project-specific coding standards, quality gates, domain vocabulary, and architectural invariants live in the consumer repo, not in this repo.
- This repo never needs to know about consumer-specific conventions.
- Consumers never need to fork or patch the shared workflows.

When adding a new reusable workflow, always include the `## Agent override` section and document which filename Claude will look for.

### Quality Gate Detection

Prompts detect the consumer repo's quality gate at runtime using a fixed priority order:

1. `Makefile` with a `check` target: `make check`
2. `pyproject.toml`: `ruff check . && pytest` (or `ruff check . && ruff format --check . && pytest` for stricter runs)
3. `package.json`: `npm test`
4. `go.mod`: `go vet ./... && go test ./...`
5. `Cargo.toml`: `cargo clippy && cargo test`
6. No gate found: note it and continue.

Do not change this order or add new cases without updating all affected workflow prompts consistently.

### Model Selection Defaults

Default models are chosen per workflow based on typical token usage and task complexity:

- `haiku`: lightweight, high-frequency tasks (`pr-describe`, `stale-pr-nudge`).
- `sonnet`: review, remediation, and implementation tasks (`pr-review`, `ci-remediate`, `issue-to-pr`, `quality-sweep`, `dependabot-review`).
- `opus`: reserved for consumer override via `with: model: opus` when dealing with complex architectural work.

Consumers can override the model via the `model` input on any workflow.

### Permissions

Each reusable workflow declares only the permissions it actually uses. The current grants per workflow:

| Workflow | `contents` | `pull-requests` | `issues` | `checks` | `actions` |
|---------|-----------|----------------|---------|---------|---------|
| pr-review | write | write | write | - | read |
| ci-remediate | write | write | write | read | read |
| issue-to-pr | write | write | write | - | read |
| quality-sweep | write | write | - | - | - |
| pr-describe | read | write | - | - | - |
| dependabot-review | read | write | - | - | - |
| stale-pr-nudge | read | write | - | read | read |

Do not add `write` to `contents` or `pull-requests` unless the workflow actually pushes commits or edits PRs.

### Concurrency Groups

All workflows use a concurrency group keyed on a unique identifier (PR number or branch name) to prevent duplicate runs. Consumer workflows use `cancel-in-progress: true` for most workflows. The `issue-to-pr` consumer sets `cancel-in-progress: false` to avoid cancelling an in-progress implementation mid-commit.

---

## Off-Limits Areas

Do not modify these without explicit discussion:

- **`examples/consumer-workflows/`**: these files are what users copy into their repos. Changes here are a breaking change for anyone who has already done so and diffed against the originals. Treat them like a public API.
- **`scaffold/bootstrap.sh`**: the bootstrap script is fetched and piped directly to bash by users. Any change takes effect immediately for new bootstraps. Test thoroughly before merging.
- **The `## Agent override` section in any prompt**: removing or weakening this section breaks the customization contract.
- **The `## Rules` section in any prompt**: these are hard safety constraints. Do not relax them (e.g., do not remove "Never force push" or "Never skip quality gates").
- **`permissions:` blocks**: do not broaden permissions beyond what a workflow demonstrably needs.
- **`timeout-minutes:`**: do not remove timeouts. Current values are set to cap runaway Claude sessions and API costs.

---

## PR Template

Use this format for all PRs to this repository:

```
## Summary

- What changed and why (2-4 bullets)

## Type of Change

- [ ] Bug fix (prompt correction, step logic, YAML syntax)
- [ ] New workflow
- [ ] Workflow improvement (better prompt, new input, default change)
- [ ] Scaffold / bootstrap change
- [ ] Documentation

## Affected Workflows

List any `.github/workflows/*.yml` files modified.

## Consumer Impact

Does this change require consumers to update their caller files or agent overrides?
If yes, describe what they need to do.

## Testing

Describe how you validated the change (workflow run link, test repo, manual review, etc.).
```
