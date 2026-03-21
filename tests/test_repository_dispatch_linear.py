"""Validation tests for .github/workflows/repository-dispatch-linear.yml."""

import pytest
from tests.conftest import load_workflow, get_on, find_prompt

WORKFLOW_NAME = "repository-dispatch-linear"


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


def test_issue_id_input_is_required(workflow):
    inputs = get_on(workflow)["workflow_call"].get("inputs", {})
    assert "issue_id" in inputs, "Missing 'issue_id' input"
    assert inputs["issue_id"].get("required") is True, "'issue_id' must be required"


def test_issue_title_input_is_required(workflow):
    inputs = get_on(workflow)["workflow_call"].get("inputs", {})
    assert "issue_title" in inputs, "Missing 'issue_title' input"
    assert inputs["issue_title"].get("required") is True, "'issue_title' must be required"


def test_anthropic_api_key_secret_required(workflow):
    secrets = get_on(workflow)["workflow_call"].get("secrets", {})
    assert "ANTHROPIC_API_KEY" in secrets, "ANTHROPIC_API_KEY secret not declared"


def test_prompt_has_agent_override_section(workflow):
    prompt = find_prompt(workflow)
    assert prompt, "No prompt found in workflow steps"
    assert "## Agent override" in prompt, "Prompt is missing '## Agent override' section"


def test_prompt_has_rules_section(workflow):
    prompt = find_prompt(workflow)
    assert prompt, "No prompt found in workflow steps"
    assert "## Rules" in prompt, "Prompt is missing '## Rules' section"


def test_prompt_references_issue_id_input(workflow):
    prompt = find_prompt(workflow)
    assert prompt, "No prompt found in workflow steps"
    assert "issue_id" in prompt, "Prompt must reference the issue_id input"


def test_prompt_references_repository_dispatch_linear_agent(workflow):
    prompt = find_prompt(workflow)
    assert prompt, "No prompt found in workflow steps"
    assert "repository-dispatch-linear" in prompt, (
        "Prompt must reference the .claude/agents/repository-dispatch-linear.md override"
    )
