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


def test_prompt_waits_for_reviewed_changes_text(workflow):
    prompt = find_prompt(workflow)
    assert prompt, "No prompt found in workflow steps"
    assert "Reviewed changes" in prompt, (
        "Prompt must gate on the Copilot review body containing 'Reviewed changes'"
    )


def test_prompt_resolves_threads_via_graphql(workflow):
    prompt = find_prompt(workflow)
    assert prompt, "No prompt found in workflow steps"
    assert "resolveReviewThread" in prompt, (
        "Prompt must resolve each thread via the resolveReviewThread GraphQL mutation"
    )


def test_prompt_fetches_thread_ids_via_graphql(workflow):
    prompt = find_prompt(workflow)
    assert prompt, "No prompt found in workflow steps"
    assert "reviewThreads" in prompt, (
        "Prompt must fetch review thread IDs via GraphQL reviewThreads query"
    )


def test_prompt_resolves_thread_immediately_after_reply(workflow):
    prompt = find_prompt(workflow)
    assert prompt, "No prompt found in workflow steps"
    assert "immediately after replying" in prompt or "immediately after" in prompt, (
        "Prompt must instruct resolving a thread immediately after replying to it"
    )


def test_prompt_posts_summary_comment(workflow):
    prompt = find_prompt(workflow)
    assert prompt, "No prompt found in workflow steps"
    assert "Code Review Summary" in prompt, (
        "Prompt must instruct posting a 'Code Review Summary' comment on the PR"
    )


def test_prompt_does_not_exit_before_summary(workflow):
    prompt = find_prompt(workflow)
    assert prompt, "No prompt found in workflow steps"
    assert "Do NOT exit" in prompt, (
        "Prompt must contain 'Do NOT exit' to prevent premature termination"
    )
