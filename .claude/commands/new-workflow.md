# New Workflow

Create a complete new agentic workflow following the repo conventions in CLAUDE.md.

## Instructions

You will create three artifacts for a new workflow named **$ARGUMENTS**:

1. **Reusable workflow** at `.github/workflows/<name>.yml`
2. **Consumer example** at `examples/consumer-workflows/agentic-<name>.yml`
3. **Test file** at `tests/test_<name>.py`

Then update `scaffold/bootstrap.sh` and `README.md`.

---

### Step 1 — Read existing conventions

Before writing anything, read:
- `CLAUDE.md` for naming conventions, required inputs/secrets, and prompt structure
- An existing reusable workflow (e.g. `.github/workflows/pr-review.yml`) as a structural reference
- Its matching consumer example (e.g. `examples/consumer-workflows/agentic-pr-review.yml`)
- `scaffold/bootstrap.sh` to understand the WORKFLOWS array format

### Step 2 — Create the reusable workflow

File: `.github/workflows/<name>.yml`

Requirements:
- `on: workflow_call` with explicit `inputs:` and `secrets:` blocks
- Required inputs: `model` (default `"claude-sonnet-4-6"`), `claude_args` (default `""`)
- Required secret: `CLAUDE_CODE_OAUTH_TOKEN`
- `timeout-minutes: 30` on the job
- Comment block at the top: workflow name, one-line description, usage example
- Uses `actions/checkout@v4` with `fetch-depth: 0`
- Uses `anthropics/claude-code-action@v1`
- Prompt structured with `##` headers and numbered steps
- Ends with `## Agent override` section pointing to `.claude/agents/<name>.md` in the consumer repo
- Select model tier per CLAUDE.md cost guardrails (haiku for lightweight read/report, sonnet for implementation/review, opus only with written justification)

### Step 3 — Create the consumer example

File: `examples/consumer-workflows/agentic-<name>.yml`

Requirements:
- Thin caller: triggers, concurrency group, single job that calls the reusable workflow via `uses:`
- Concurrency group pattern: `agentic-<name>-${{ github.ref }}`
- Commented-out `with:` lines showing common customizations
- Comment at top noting `CLAUDE_CODE_OAUTH_TOKEN` requirement and optional agent override file path

### Step 4 — Create the test file

File: `tests/test_<name>.py`

Requirements:
- Validate prompt structure (required `##` sections are present)
- Validate required inputs exist in the workflow YAML (`model`, `claude_args`, `CLAUDE_CODE_OAUTH_TOKEN`)
- Validate any shell logic in non-Claude steps
- Follow the pattern of existing test files in `tests/`

### Step 5 — Update supporting files

In `scaffold/bootstrap.sh`: append `"agentic-<name>.yml"` to the `WORKFLOWS` array.

In `README.md`:
- Add a row to the Workflows table
- Add a row to the Cost Considerations table with model tier and estimated token/cost range

### Step 6 — Confirm

List all files created or modified and summarize what each one does.
