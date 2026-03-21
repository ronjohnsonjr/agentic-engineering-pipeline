# agentic-ci

Repo-agnostic GitHub Actions workflows that wire Claude-powered agentic loops
into your CI/CD pipeline. Drop these into any repository to get autonomous PR
reviews, CI failure remediation, issue-to-PR implementation, and more.

Built on [claude-code-action](https://github.com/anthropics/claude-code-action)
and the `.claude/agents/` convention for project-specific agent behavior.

## Workflows

| Workflow | Trigger | What it does |
|----------|---------|-------------|
| **pr-review** | PR opened/ready | Copilot + Claude collaborative review cycle. Waits for Copilot, catalogs all comments, resolves each one (fix/acknowledge/decline), pushes fixes, posts summary. |
| **ci-remediate** | CI check fails | Reads failure logs, diagnoses root cause, applies minimal fix, pushes, re-verifies. Up to 3 rounds before escalating. |
| **issue-to-pr** | Issue assigned/labeled | Takes an issue from "assigned" to "PR created": plans, implements, tests, commits, pushes, creates PR with full description. |
| **quality-sweep** | Weekly schedule/dispatch | Scans for dead code, unused imports, generic naming, redundant comments. Auto-commits a cleanup PR. |
| **pr-describe** | PR opened (empty body) | Auto-generates a rich PR description from the diff and commit history. |
| **dependabot-review** | Dependabot PR opened | Reviews changelog, checks for breaking changes, posts risk assessment. Optionally auto-approves patch bumps. |
| **stale-pr-nudge** | Daily schedule | Finds PRs inactive for 5+ days, diagnoses the blocker (CI failing, review needed, conflicts, etc.), posts a helpful nudge comment. |

## Quick Start

### Option 1: Bootstrap script

From the root of any repo:

```bash
curl -sL https://raw.githubusercontent.com/onyx-point/agentic-ci/main/scaffold/bootstrap.sh | bash
```

This creates the consumer workflows in `.github/workflows/` and minimal agent
stubs in `.claude/agents/`.

### Option 2: Manual setup

1. Copy the consumer workflows you want from `examples/consumer-workflows/`
   into your repo's `.github/workflows/`.

2. Set `CLAUDE_CODE_OAUTH_TOKEN` as a repository or organization secret:
   ```bash
   gh secret set CLAUDE_CODE_OAUTH_TOKEN
   ```

3. Update the `uses:` references in each workflow if your org name differs
   from `onyx-point`:
   ```yaml
   uses: YOUR-ORG/agentic-ci/.github/workflows/pr-review.yml@main
   ```

4. (Optional) Add project-specific agent definitions in `.claude/agents/`.

## Architecture

```
your-repo/
  .github/workflows/
    agentic-pr-review.yml      <-- thin caller (5-20 lines)
    agentic-ci-remediate.yml   <-- thin caller
    ...
  .claude/
    agents/
      coder.md                 <-- project-specific (optional)
      reviewer.md              <-- project-specific (optional)
      ci-remediate.md          <-- project-specific (optional)
      ...
  CLAUDE.md                    <-- project conventions (optional)

onyx-point/agentic-ci/          (this repo)
  .github/workflows/
    pr-review.yml              <-- reusable workflow (workflow_call)
    ci-remediate.yml           <-- reusable workflow
    ...
```

The consumer workflows are thin callers that define triggers and pass
secrets. The reusable workflows in this repo handle all the orchestration.

At runtime, Claude reads `.claude/agents/` from the checked-out repo. If a
project-specific agent definition exists (e.g., `.claude/agents/ci-remediate.md`),
it overrides the generic behavior in the reusable workflow prompt. This lets you
customize behavior per-repo without forking the shared workflows.

## Self-Improvement Loop

This repo uses its own workflows to improve itself. The intended cycle:

1. **Open a GitHub issue** describing the change (bug, doc update, new workflow, etc.).
2. **Trigger the agent** — either add the `local` label to the issue, or dispatch the Linear workflow:
   ```bash
   gh issue edit <number> --add-label local
   ```
3. **Agent implements and opens a PR** — the `local-issue-to-pr` workflow runs, creates a branch, implements the change, and opens a PR.
4. **`pr-review` runs automatically** — on PR open, the `local-pr-review` workflow fires and Claude reviews the diff for correctness, conventions, and test coverage.
5. **Human approves and merges** — a maintainer reads the review summary, verifies the change looks right, and merges.

### Parallel dispatch

To dispatch multiple agents in parallel — for example, to implement several queued issues at once — label all of them in one shot:

```bash
# Dispatch 4 agents in parallel for issues 16, 17, 18, 19
for issue in 16 17 18 19; do
  gh issue edit "$issue" --add-label local &
done
wait
```

Each issue gets its own workflow run (concurrency is keyed on issue number), so all four agents implement their respective issues simultaneously. PRs land independently and are reviewed as they arrive.

## Customization

### Per-repo agent overrides

Each reusable workflow prompt includes an "Agent override" section:

> If the repo contains `.claude/agents/pr-review-orchestrator.md`, read it
> and follow its project-specific instructions. Those instructions take
> precedence over the generic steps above for any conflicts.

This means you can keep all your project-specific review conventions, quality
gates, domain vocabulary, and architectural invariants in `.claude/agents/`
and the shared workflow will respect them automatically.

### Workflow inputs

Every reusable workflow accepts inputs for common configuration:

```yaml
jobs:
  review:
    uses: onyx-point/agentic-ci/.github/workflows/pr-review.yml@main
    secrets:
      CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
    with:
      model: sonnet                  # Claude model (haiku, sonnet, opus)
      max_copilot_wait_minutes: 15   # How long to wait for Copilot
      max_review_rounds: 3           # Max Copilot feedback rounds
      claude_args: "--max-turns 20"  # Additional CLI args
```

### CLAUDE.md

If your repo has a `CLAUDE.md` at the root, all agents read it for project
conventions (line length, docstring style, import ordering, naming rules,
architectural invariants, etc.). This is the single source of truth that
keeps agent behavior consistent with your team's standards.

## Integrating with Your Existing Stack

### Linear/Jira/project management

The `issue-to-pr` workflow works with GitHub Issues by default. To integrate
with Linear, pass an MCP config:

```yaml
with:
  mcp_config: '{"mcpServers":{"Linear":{"type":"http","url":"https://mcp.linear.app/mcp"}}}'
```

Then add a `.claude/agents/linear.md` with your project-specific status
mappings and comment templates.

### Existing CI

The workflows complement your existing CI, they don't replace it. The
`ci-remediate` workflow watches your existing CI checks and responds to
failures. Your `ci.yml`, `premerge.yml`, and other workflows continue to
run as-is.

### Copilot

The `pr-review` workflow is designed to work alongside GitHub Copilot
code review. It waits for Copilot to post its review, then systematically
addresses each comment. If Copilot is not enabled, the workflow skips the
wait and reviews the PR directly.

## Secrets

| Secret | Required | Used by |
|--------|----------|---------|
| `CLAUDE_CODE_OAUTH_TOKEN` | Yes | All workflows |
| `LINEAR_API_KEY` | No | issue-to-pr (if using Linear MCP) |

Set at the org level to avoid per-repo configuration:

```bash
gh secret set CLAUDE_CODE_OAUTH_TOKEN --org onyx-point --visibility all
```

## Cost Considerations

Each workflow invocation uses Claude API tokens. Approximate per-invocation costs
(varies with repo size and diff complexity):

| Workflow | Typical tokens | Approximate cost |
|----------|---------------|-----------------|
| pr-describe | 5-15K | ~$0.01-0.05 |
| stale-pr-nudge | 5-20K per PR | ~$0.01-0.05/PR |
| dependabot-review | 10-30K | ~$0.03-0.10 |
| pr-review | 20-100K | ~$0.10-0.50 |
| ci-remediate | 30-150K | ~$0.15-0.75 |
| quality-sweep | 50-200K | ~$0.25-1.00 |
| issue-to-pr | 100-500K | ~$0.50-2.50 |

To control costs:
- Use `haiku` model for lightweight tasks (pr-describe, stale-pr-nudge)
- Use `sonnet` for most review and implementation tasks
- Reserve `opus` for complex architectural work
- Set `timeout-minutes` on jobs to cap runaway sessions
- Use concurrency groups (already configured) to avoid duplicate runs

## License

MIT
