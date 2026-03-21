# Run Pipeline

Walk a GitHub issue through all pipeline stages using the agentic engineering workflow.

## Instructions

Run the full pipeline for issue **$ARGUMENTS**.

---

### Step 1 — Load context

Read:
- `CLAUDE.md` for pipeline conventions and agent override pattern
- `.claude/agents/orchestrator.md` for routing rules and stage definitions

### Step 2 — Fetch the issue

Retrieve the issue using `gh issue view <number> --json number,title,body,labels,assignees`.

Parse the issue to identify:
- The stated goal or feature request
- Acceptance criteria (explicit or implicit)
- Any labels that affect routing (e.g. `bug`, `enhancement`, `chore`)

### Step 3 — Clarify (Stage 1)

Delegate to the `clarifier` agent.

- If clarifier returns unresolved questions, halt here and surface them as a comment on the issue. Do not proceed until the questions are answered.
- If clarifier confirms the issue is unambiguous, proceed.

Skip clarification only if the issue already contains explicit acceptance criteria and no ambiguous scope.

### Step 4 — Research (Stage 2)

Delegate to the `researcher` agent. Pass:
- The clarified issue summary
- Any answers provided to clarifier questions

Researcher produces a RESEARCH BRIEF. Validate that the brief contains: scope, affected files, risks, and open questions.

### Step 5 — Plan (Stage 3)

Delegate to the `planner` agent. Pass the RESEARCH BRIEF.

Planner produces an IMPLEMENTATION PLAN. The plan must include: approach, files to change, test strategy, and rollback notes. Do not proceed without a complete plan.

### Step 6 — Implement (Stage 4)

Delegate to the `programmer` agent. Pass the IMPLEMENTATION PLAN.

Programmer writes code and runs the quality gate. If the quality gate fails, pass the failure back to `remediator` and retry up to 2 times before halting.

### Step 7 — Test (Stage 5)

Run in parallel where possible:
- Delegate to `unit-tester` for unit tests
- Delegate to `test-integration` if the change touches API contracts or database schemas
- Delegate to `test-e2e` if the change has a UI surface

Skip `test-e2e` for pure backend or library changes. Skip `test-integration` for changes with no API or schema impact.

All test agents must return PASS before proceeding.

### Step 8 — Review (Stage 6)

Delegate to `ai-reviewer`. If reviewer returns CHANGES REQUIRED, delegate to `remediator` then re-run `ai-reviewer`. Repeat up to 3 cycles. If still failing after 3 cycles, halt and escalate.

### Step 9 — Create PR (Stage 7)

Delegate to `pr-creator`. Pass the issue number, branch name, and pipeline summary.

### Step 10 — Report

Output the structured pipeline result:

```
PIPELINE RESULT: [COMPLETE | HALTED]
ISSUE: #<number>
STAGES: <comma-separated list of completed stages>
SKIPPED: <comma-separated list with reason, or "none">
PR: <url or "not created">
NOTES: <any important context for human reviewer>
```
