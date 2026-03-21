# Validate All

Run all tests, lint all YAML, and validate all agent frontmatter in the repo.

## Instructions

Perform a full validation sweep. Report failures clearly; do not stop at the first failure — collect all issues before summarizing.

---

### Step 1 — Run the test suite

```bash
pytest tests/ -v 2>&1
```

Record: number of tests passed, failed, and any error output.

### Step 2 — Lint all workflow YAML

For every file in `.github/workflows/` and `examples/consumer-workflows/`:

```bash
python3 -c "import yaml, sys; yaml.safe_load(open(sys.argv[1]))" <file>
```

Or use `yamllint` if available:

```bash
yamllint .github/workflows/ examples/consumer-workflows/
```

Record: any files that fail to parse or have lint warnings.

### Step 3 — Validate agent frontmatter

For every file in `.claude/agents/`:

Check that the frontmatter:
1. Is present (file starts with `---`)
2. Contains exactly these fields: `name`, `description`, `model`, `tools`
3. `name` matches the filename without `.md`
4. `model` is one of: `claude-haiku-4-5-20251001`, `claude-sonnet-4-6`, `claude-opus-4-6`
5. `tools` is a non-empty list

Report any agent file that fails any check.

### Step 4 — Validate workflow inventory

Cross-check that every reusable workflow in `.github/workflows/` has:
- A matching consumer example in `examples/consumer-workflows/agentic-<name>.yml`
- A matching test file in `tests/test_<name>.py`
- An entry in `scaffold/bootstrap.sh`'s `WORKFLOWS` array
- A row in the README.md Workflows table

Report any workflow that is missing any of these.

### Step 5 — Validate consumer examples

For every file in `examples/consumer-workflows/`:
- Filename must start with `agentic-`
- Must contain a `uses:` reference to the matching reusable workflow
- Must define a `concurrency:` group

Report any consumer example that fails these checks.

### Step 6 — Summary report

Output a structured report:

```
VALIDATION RESULT: [PASS | FAIL]

Tests:         <N passed, N failed>
YAML lint:     <N files ok, N files failed>
Agent frontmatter: <N valid, N invalid>
Workflow inventory: <N complete, N missing artifacts>
Consumer examples: <N valid, N invalid>

ISSUES:
- <file>: <description of problem>
```

If all checks pass, output `VALIDATION RESULT: PASS` with counts. If any check fails, output `VALIDATION RESULT: FAIL` and list every issue found.
