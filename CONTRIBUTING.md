# Contributing to agentic-engineering-pipeline

This repo eats its own cooking. Every reusable workflow published here is
also running on this repo via "dogfood" caller workflows. That means
contributions go through the same AI-assisted pipeline that consumers of
this repo will experience.

## How the dogfood setup works

Five thin caller workflows in `.github/workflows/dogfood-*.yml` call the
reusable workflows in `.github/workflows/` on this repo itself:

| Caller workflow | Trigger | Reusable workflow called |
|---|---|---|
| `dogfood-issue-to-pr.yml` | Issue labeled `dogfood` | `issue-to-pr.yml` |
| `dogfood-ci-remediate.yml` | Check suite fails on a PR | `ci-remediate.yml` |
| `dogfood-pr-review.yml` | PR opened/updated against `main` | `pr-review.yml` |
| `dogfood-pr-describe.yml` | PR opened against `main` | `pr-describe.yml` |
| `dogfood-quality-sweep.yml` | Weekly (Mon 09:00 UTC) or manual | `quality-sweep.yml` |

Each caller uses `secrets: inherit` so the single `ANTHROPIC_API_KEY`
repo secret flows through without duplication.

## What this means for contributors

### Opening a PR

When you open a PR targeting `main`:

1. **PR Describe** runs immediately and fills in any empty PR description
   from the diff. If you wrote a description (>50 chars), it skips.
2. **PR Review** runs after open or each push, polls for a Copilot review,
   then Claude resolves, acknowledges, or declines each comment and posts
   a summary.

You still own the PR. Claude's review comments and description are a first
pass, not a final verdict.

### Working on issues

Label any issue `dogfood` to have Claude implement it autonomously:

1. Assign yourself or leave unassigned.
2. Apply the `dogfood` label.
3. `dogfood-issue-to-pr.yml` triggers, runs the full issue-to-PR pipeline,
   and opens a PR with a comment on the issue linking back.

Use this for clearly-scoped tasks (bug fixes, small features, docs). For
large architectural changes, open a PR directly.

### When CI fails on your PR

`dogfood-ci-remediate.yml` triggers automatically on any failing check suite
attached to a PR. Claude diagnoses the failure, applies a minimal fix, and
pushes a corrective commit. It will not suppress tests or skip hooks.

If the same failure persists after the configured fix rounds, Claude posts
an escalation comment and stops.

### Weekly quality sweep

Every Monday Claude scans the repo for dead code, unused imports, generic
naming, and hygiene issues. If it finds fixes, it opens a `chore/quality-sweep-*`
PR for review. You can also trigger it manually from the Actions tab.

## Required secret

All dogfood workflows require one repo secret:

```
ANTHROPIC_API_KEY
```

Set it with:

```bash
gh secret set ANTHROPIC_API_KEY
```

No other secrets or tokens are needed — `GITHUB_TOKEN` permissions are
declared inside each reusable workflow.

## Modifying reusable workflows

The reusable workflows are the source of truth. The dogfood callers are
intentionally thin (trigger + `uses:` + `secrets: inherit`). When you
change a reusable workflow's `inputs:` or `secrets:`, update the matching
dogfood caller if any required inputs change.

To test a reusable workflow change end-to-end on this repo, the dogfood
triggers are live once merged to `main`. For pre-merge testing, use
`workflow_dispatch` on the dogfood caller or open a draft PR.

## Repo structure

```
.github/
  workflows/
    issue-to-pr.yml          # reusable: issue -> PR
    ci-remediate.yml         # reusable: diagnose + fix failing CI
    pr-review.yml            # reusable: AI-assisted PR review
    pr-describe.yml          # reusable: auto-generate PR descriptions
    quality-sweep.yml        # reusable: periodic code hygiene
    dependabot-review.yml    # reusable: triage Dependabot PRs
    stale-pr-nudge.yml       # reusable: nudge stale PRs
    dogfood-issue-to-pr.yml  # caller (this repo)
    dogfood-ci-remediate.yml # caller (this repo)
    dogfood-pr-review.yml    # caller (this repo)
    dogfood-pr-describe.yml  # caller (this repo)
    dogfood-quality-sweep.yml# caller (this repo)
scaffold/
  bootstrap.sh               # one-liner to add these workflows to any repo
```
