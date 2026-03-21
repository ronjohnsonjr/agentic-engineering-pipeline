"""Validation tests for .github/workflows/pr-review.yml."""

import pytest
from tests.conftest import load_workflow, get_on, find_prompt

WORKFLOW_NAME = "pr-review"


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
