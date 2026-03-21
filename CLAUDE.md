# CLAUDE.md

This file is read by all agents that run in this repository. It documents project conventions, structure, and contribution guidelines for the `agentic-engineering-pipeline` repo.

---

## Project Overview

This repo provides reusable GitHub Actions workflows that wire Claude-powered agentic loops into any CI/CD pipeline. Drop the consumer workflows into any repository to get autonomous PR reviews, CI failure remediation, issue-to-PR implementation, dependency review, and more.

Built on [claude-code-action](https://github.com/anthropics/claude-code-action) and the `.claude/agents/` convention for per-project agent behavior overrides.

The pipeline follows the Stripe Minions "Blueprint" pattern: each agentic node produces a structured output that acts as a deterministic gate before the next node runs. Agents do not free-form chain; they pass typed briefs (RESEARCH BRIEF, IMPLEMENTATION PLAN, UNIT TEST RESULT, etc.) that a downstream agent or the orchestrator validates before proceeding. This makes failures observable and retryable at the gate rather than buried mid-run.

---

## Repo Structure

```
agentic-engineering-pipeline/
  .github/workflows/              # Reusable workflows (no prefix)
    ci-remediate.yml
    dependabot-review.yml
    issue-to-pr.yml
    pr-describe.yml
    pr-review.yml
    quality-sweep.yml
    stale-pr-nudge.yml

  examples/
    consumer-workflows/           # Drop-in caller workflows (agentic- prefix)
      agentic-ci-remediate.yml
      agentic-dependabot-review.yml
      agentic-issue-to-pr.yml
      agentic-pr-describe.yml
      agentic-pr-review.yml
      agentic-quality-sweep.yml
      agentic-stale-pr-nudge.yml

  scaffold/
    bootstrap.sh                  # One-command setup script for consumer repos

  README.md
  CLAUDE.md                       # This file
```

---

## Naming Conventions

**Reusable workflows** live in `.github/workflows/` and have no prefix. They use `on: workflow_call` and are the single source of orchestration logic.

```
pr-review.yml
ci-remediate.yml
issue-to-pr.yml
```

**Consumer workflows** live in `examples/consumer-workflows/` and use the `agentic-` prefix. They are thin callers (5-20 lines) that define triggers, pass secrets, and delegate to the reusable workflow via `uses:`.

```
agentic-pr-review.yml
agentic-ci-remediate.yml
agentic-issue-to-pr.yml
```

This naming distinction makes it immediately clear, in any repo's `.github/workflows/` directory, which files are local trigger wrappers and which are shared logic.

---

## Workflow Inventory

| Reusable Workflow | Consumer Example | Trigger | What it does |
|---|---|---|---|
| `pr-review.yml` | `agentic-pr-review.yml` | PR opened/ready | Copilot + Claude collaborative review: catalogs comments, fixes/acknowledges/declines each one, pushes fixes, posts summary. |
| `ci-remediate.yml` | `agentic-ci-remediate.yml` | CI check fails | Reads failure logs, diagnoses root cause, applies minimal fix, pushes, re-verifies. Up to 3 rounds before escalating. |
| `issue-to-pr.yml` | `agentic-issue-to-pr.yml` | Issue assigned/labeled | Plans, implements, tests, commits, pushes, and creates a PR from a GitHub issue. |
| `quality-sweep.yml` | `agentic-quality-sweep.yml` | Weekly schedule/dispatch | Scans for dead code, unused imports, generic naming, redundant comments. Auto-commits a cleanup PR. |
| `pr-describe.yml` | `agentic-pr-describe.yml` | PR opened (empty body) | Auto-generates a rich PR description from the diff and commit history. |
| `dependabot-review.yml` | `agentic-dependabot-review.yml` | Dependabot PR opened | Reviews changelog, checks for breaking changes, posts risk assessment. Optionally auto-approves patch bumps. |
| `stale-pr-nudge.yml` | `agentic-stale-pr-nudge.yml` | Daily schedule | Finds PRs inactive 5+ days, diagnoses the blocker, posts a helpful nudge comment. |

---

## How to Add a New Workflow

1. **Create the reusable workflow** in `.github/workflows/<name>.yml`.
   - Use `on: workflow_call` with explicit `inputs:` and `secrets:` blocks.
   - Always include a `model` input (default: `"sonnet"`) and a `claude_args` input (default: `""`).
   - Always require `ANTHROPIC_API_KEY` as a secret.
   - Set `timeout-minutes` on the job (30 minutes is a reasonable default).
   - Include a concise comment block at the top with the workflow name, one-line description, and usage example.
   - End the Claude prompt with an `## Agent override` section pointing to a `.claude/agents/<name>.md` file in the consumer repo, so projects can customize behavior without forking.

2. **Create the consumer example** in `examples/consumer-workflows/agentic-<name>.yml`.
   - File must use the `agentic-` prefix.
   - Keep it thin: define triggers, a `concurrency` group, and a single job that calls the reusable workflow.
   - Include commented-out `with:` lines showing common customizations.
   - Add prerequisite comments at the top referencing `ANTHROPIC_API_KEY` and any optional agent override file.

3. **Add the workflow to `scaffold/bootstrap.sh`**.
   - Append `"agentic-<name>.yml"` to the `WORKFLOWS` array so new repos bootstrapped with the script get the workflow automatically.
   - **Never add, remove, or rename a consumer-facing `inputs:` or `secrets:` field on a reusable workflow without making the matching change in `scaffold/bootstrap.sh`.** Consumer repos copy the bootstrap template verbatim; a mismatch silently breaks their pipelines with no error until the workflow fires.

4. **Update `README.md`**.
   - Add a row to the Workflows table.
   - Add a row to the Cost Considerations table with typical token and cost estimates.

---

## Reusable Workflow Conventions

- All reusable workflows use `actions/checkout@v4` with `fetch-depth: 0`.
- All reusable workflows use `anthropics/claude-code-action@v1`.
- Permissions are declared explicitly at the workflow level. Request only what the workflow needs.
- Prompts are written inline in the YAML `prompt:` field. Keep them structured with `##` headers and numbered steps.
- Use conventional commit messages in any commits the agent makes (`feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`).
- Concurrency groups in consumer workflows use the pattern `agentic-<name>-${{ github.ref }}` or a more specific key when the workflow targets a specific branch or PR.

---

## Agent Override Pattern

Every workflow prompt ends with a section like:

```
## Agent override

If the repo contains `.claude/agents/<workflow-name>.md`, read it
and follow its project-specific instructions. Those instructions take
precedence over the generic steps above for any conflicts.
```

This allows consumer repos to customize agent behavior per-workflow without forking this repo. When writing prompts, always include this section and reference the conventional agent file name (matching the reusable workflow filename without the `.yml` extension).

### Agent definition frontmatter

Every file in `.claude/agents/` must begin with YAML frontmatter in this exact format:

```yaml
---
name: <slug matching the filename without .md>
description: >
  <multi-line description used by the orchestrator to decide when to invoke this agent>
model: <full model ID, e.g. claude-sonnet-4-6>
tools:
  - <Tool>
---
```

Always preserve this frontmatter structure. Do not add extra keys, reorder fields, or omit the `description` or `tools` blocks. The orchestrator parses frontmatter to route tasks; malformed frontmatter silently disables the agent.

---

## Claude Model Selection and Cost Guardrails

| Role | Model | Examples |
|---|---|---|
| Verification, lightweight analysis | `haiku` | clarifier, verifier, stale-pr-nudge, pr-describe |
| Implementation, review, remediation | `sonnet` | coder, reviewer, remediator, ci-remediate, pr-review |
| Complex planning only | `opus` | planner |

**Guardrails that must be followed:**

- **Default to `sonnet`** for any new workflow or agent unless the task is clearly lightweight (use `haiku`) or requires multi-step architectural reasoning across a large context (use `opus`).
- **Never default a new agent or workflow to `opus` without explicit written justification** in the PR description. "It might need to reason deeply" is not sufficient justification.
- **Use `haiku` for all verification and analysis agents** that only read and report (no code writing). These tasks do not benefit from a larger model and run frequently.
- **Set `timeout-minutes`** on every job. Runaway `opus` sessions are the primary cost risk in this repo.

The `model` input on each reusable workflow defaults to the appropriate tier. Consumer workflows can override this, but the default communicates the intended cost tier.

---

## Testing

Run the test suite with:

```bash
# Python
pytest

# JavaScript
jest
```

**Rules:**

- Every new reusable workflow must have a corresponding test file in `tests/`. The test file name mirrors the workflow name: `tests/test_<workflow-name>.py` (Python) or `tests/<workflow-name>.test.js` (JS).
- Tests for workflows validate the prompt structure, required inputs, and any shell logic in non-Claude steps (e.g., the `find-pr` job in `ci-remediate`).
- Do not merge a new workflow without its test file. CI will fail on missing coverage.
- Agent definition files (`.claude/agents/*.md`) do not require test files, but any shell commands embedded in agent prompts should be validated manually in a scratch repo before merging.

---

## Secrets

| Secret | Required | Used by |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | All workflows |
| `LINEAR_API_KEY` | No | `issue-to-pr` (if using Linear MCP) |

Set at the org level to avoid per-repo configuration:

```bash
gh secret set ANTHROPIC_API_KEY --org <your-org> --visibility all
```

---

## Claude Code Commands

Project-specific slash commands live in `.claude/commands/`. Invoke them with `/project:<name>` in Claude Code.

| Command | Usage | What it does |
|---|---|---|
| `new-workflow` | `/project:new-workflow <name>` | Creates a reusable workflow, consumer example, and test file for a new workflow named `<name>`. Also updates `scaffold/bootstrap.sh` and `README.md`. |
| `new-agent` | `/project:new-agent <name>` | Creates a new `.claude/agents/<name>.md` file with correct frontmatter and behavior instructions. |
| `run-pipeline` | `/project:run-pipeline <issue-number>` | Walks a GitHub issue through all pipeline stages (clarify → research → plan → implement → test → review → PR). |
| `validate-all` | `/project:validate-all` | Runs the test suite, lints all workflow YAML, validates all agent frontmatter, and cross-checks the workflow inventory. |

---

## Contribution Guidelines

- **Read before editing.** Understand an existing workflow fully before modifying it.
- **Minimal changes.** Fix the specific thing that needs fixing. Do not refactor surrounding prompts or inputs unless that is the stated goal.
- **No force pushes** to `main`.
- **No --no-verify.** Never bypass pre-commit hooks or CI checks.
- **Test consumer workflows manually** by bootstrapping a scratch repo and verifying the trigger fires as expected before merging.
- **Keep consumer workflows thin.** Logic belongs in the reusable workflow, not in the caller. If you find yourself adding steps to a consumer example, that logic likely belongs in the reusable workflow prompt instead.
- **Prompt changes are behavioral changes.** Treat modifications to the `prompt:` field with the same care as code changes. Changes to agent instructions affect every downstream repo using the workflow.
- **Prefer `sonnet` defaults** for new workflows unless the task is clearly lightweight (haiku) or complex architectural reasoning is required (opus).
- Commit messages must follow conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`.
