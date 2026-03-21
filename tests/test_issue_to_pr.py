"""Validation tests for .github/workflows/issue-to-pr.yml."""

import pytest
from tests.conftest import load_workflow, get_on, find_prompt

WORKFLOW_NAME = "issue-to-pr"


@pytest.fixture
def workflow() -> dict:
    return load_workflow(WORKFLOW_NAME)


def test_has_workflow_call(workflow):
    assert "workflow_call" in get_on(workflow)


def test_has_permissions(workflow):
    assert "permissions" in workflow


def test_has_jobs(workflow):
    assert "jobs" in workflow


def test_all_jobs_have_timeout(workflow):
    for name, job in workflow["jobs"].items():
        assert "timeout-minutes" in job, f"Job '{name}' is missing timeout-minutes"


def test_model_input_has_default(workflow):
    inputs = get_on(workflow)["workflow_call"].get("inputs", {})
    assert "model" in inputs, "Missing 'model' input"
    assert inputs["model"].get("default") is not None, "'model' input has no default"


def test_claude_code_oauth_token_secret_required(workflow):
    secrets = get_on(workflow)["workflow_call"].get("secrets", {})
    assert "CLAUDE_CODE_OAUTH_TOKEN" in secrets, "CLAUDE_CODE_OAUTH_TOKEN secret not declared"


def test_prompt_has_agent_override_section(workflow):
    prompt = find_prompt(workflow)
    assert prompt, "No prompt found in workflow steps"
    assert "## Agent override" in prompt, "Prompt is missing '## Agent override' section"


def test_prompt_has_rules_section(workflow):
    prompt = find_prompt(workflow)
    assert prompt, "No prompt found in workflow steps"
    assert "## Rules" in prompt, "Prompt is missing '## Rules' section"


# --- Linear integration tests ---


def _find_action_step(workflow: dict, action_prefix: str) -> dict | None:
    """Return the first step whose 'uses' starts with action_prefix."""
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []) or []:
            if isinstance(step, dict) and str(step.get("uses", "")).startswith(action_prefix):
                return step
    return None


def test_mcp_config_input_declared(workflow):
    """mcp_config input must be declared so callers can pass Linear MCP config."""
    inputs = get_on(workflow)["workflow_call"].get("inputs", {})
    assert "mcp_config" in inputs, "Missing 'mcp_config' input"


def test_mcp_config_input_type_is_string(workflow):
    inputs = get_on(workflow)["workflow_call"].get("inputs", {})
    assert inputs["mcp_config"].get("type") == "string", "'mcp_config' input must be type string"


def test_mcp_config_default_is_empty_string(workflow):
    """Empty default means no MCP servers configured — safe fallback."""
    inputs = get_on(workflow)["workflow_call"].get("inputs", {})
    default = inputs["mcp_config"].get("default")
    assert default == "", f"Expected empty string fallback, got {default!r}"


@pytest.mark.xfail(strict=True, reason="mcp_config is declared but not yet forwarded to claude-code-action")
def test_mcp_config_wired_to_action(workflow):
    """mcp_config must be forwarded to claude-code-action, otherwise it has no effect."""
    step = _find_action_step(workflow, "anthropics/claude-code-action")
    assert step is not None, "claude-code-action step not found"
    with_block = step.get("with", {}) or {}
    assert "mcp_config" in with_block, (
        "mcp_config input is declared but not passed to claude-code-action"
    )


def test_linear_api_key_not_required(workflow):
    """LINEAR_API_KEY must not be required — repos without Linear should still work.

    CLAUDE.md lists LINEAR_API_KEY as optional. If/when the secret is formally
    declared in the workflow, it must not have required=true.
    """
    secrets = get_on(workflow)["workflow_call"].get("secrets", {})
    assert secrets.get("LINEAR_API_KEY", {}).get("required") is not True, (
        "LINEAR_API_KEY must not be required=true"
    )


def test_prompt_has_phase_sections(workflow):
    """Prompt must contain all five implementation phases."""
    prompt = find_prompt(workflow)
    for phase in ("Phase 1", "Phase 2", "Phase 3", "Phase 4", "Phase 5"):
        assert phase in prompt, f"Prompt is missing '{phase}' section"


def test_prompt_references_coder_agent(workflow):
    """Prompt must reference the coder.md agent override so projects can inject coding standards."""
    prompt = find_prompt(workflow)
    assert "coder.md" in prompt, "Prompt does not reference .claude/agents/coder.md override"
