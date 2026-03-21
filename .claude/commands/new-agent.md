# New Agent

Create a new agent definition file in `.claude/agents/` with proper frontmatter and behavior instructions.

## Instructions

You will create a new agent definition for **$ARGUMENTS**.

---

### Step 1 — Read existing agents

Before writing anything, read two or three existing agent files in `.claude/agents/` (e.g. `orchestrator.md`, `researcher.md`, `planner.md`) to understand the frontmatter format and instruction style.

Also read `CLAUDE.md` for:
- The required frontmatter fields (`name`, `description`, `model`, `tools`)
- Model selection cost guardrails (haiku for read/report, sonnet for implementation/review, opus only with justification)

### Step 2 — Determine the agent's role

Based on the name provided, identify:
- **What trigger or pipeline stage** invokes this agent
- **What inputs** it receives (e.g. a RESEARCH BRIEF, an issue summary, a diff)
- **What structured output** it produces (e.g. IMPLEMENTATION PLAN, UNIT TEST RESULT)
- **What tools** it needs (use the minimum necessary set)
- **Which model tier** is appropriate per CLAUDE.md cost guardrails

### Step 3 — Create the agent file

File: `.claude/agents/<name>.md`

The file must begin with this exact frontmatter:

```yaml
---
name: <slug matching filename without .md>
description: >
  <multi-line description used by the orchestrator to route tasks>
model: <full model ID: claude-haiku-4-5-20251001 | claude-sonnet-4-6 | claude-opus-4-6>
tools:
  - <Tool>
---
```

Rules:
- `name` must exactly match the filename without `.md`
- `description` must be a clear, specific summary the orchestrator can use to decide when to invoke this agent — not a generic statement
- Do not add extra frontmatter keys, reorder fields, or omit `description` or `tools`
- Choose the minimum tool set required; do not add tools speculatively

After the frontmatter, write the agent's behavior instructions:
- State the agent's single responsibility clearly in the first paragraph
- Define what structured input it expects
- Define the exact structured output format it must produce (use a code block)
- List any constraints or failure conditions

### Step 4 — Confirm

Show the created file path and frontmatter, and explain how the orchestrator would route tasks to this agent.
