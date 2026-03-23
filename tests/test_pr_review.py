"""Validation tests for .github/workflows/pr-review.yml."""

import pytest
from tests.conftest import load_workflow, get_on, find_all_prompts

WORKFLOW_NAME = "pr-review"


@pytest.fixture
def workflow() -> dict:
    return load_workflow(WORKFLOW_NAME)


@pytest.fixture
def all_prompts(workflow) -> str:
    """Concatenate all prompts across sub-agent steps for content checks."""
    return "\n".join(find_all_prompts(workflow))


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
    assert "CLAUDE_CODE_OAUTH_TOKEN" in secrets, (
        "CLAUDE_CODE_OAUTH_TOKEN secret not declared"
    )


def test_prompt_has_agent_override_section(all_prompts):
    assert "## Agent override" in all_prompts, (
        "Prompt is missing '## Agent override' section"
    )


def test_prompt_has_rules_section(all_prompts):
    assert "## Rules" in all_prompts, "Prompt is missing '## Rules' section"


def test_copilot_polling_is_bash_step(workflow):
    """Copilot polling must be a pure bash step, not inside a Claude prompt."""
    steps = workflow["jobs"]["pr-review"]["steps"]
    poll_steps = [
        s
        for s in steps
        if "copilot" in s.get("name", "").lower()
        and "wait" in s.get("name", "").lower()
    ]
    assert poll_steps, "No Copilot polling step found"
    for step in poll_steps:
        assert "run" in step, (
            "Copilot polling step must be a bash 'run' step, not a Claude action"
        )
        assert "uses" not in step, (
            "Copilot polling step must not use claude-code-action"
        )


def test_copilot_polling_checks_reviewed_changes(workflow):
    """The bash polling step must check for the 'Reviewed changes' text."""
    steps = workflow["jobs"]["pr-review"]["steps"]
    poll_steps = [
        s
        for s in steps
        if "copilot" in s.get("name", "").lower()
        and "wait" in s.get("name", "").lower()
    ]
    assert poll_steps, "No Copilot polling step found"
    poll_script = poll_steps[0].get("run", "")
    assert "Reviewed changes" in poll_script, (
        "Copilot polling bash step must check for 'Reviewed changes' text"
    )


def test_prompt_resolves_threads_via_graphql(all_prompts):
    assert "resolveReviewThread" in all_prompts, (
        "Prompt must resolve each thread via the resolveReviewThread GraphQL mutation"
    )


def test_prompt_fetches_thread_ids_via_graphql(all_prompts):
    assert "reviewThreads" in all_prompts, (
        "Prompt must fetch review thread IDs via GraphQL reviewThreads query"
    )


def test_prompt_resolves_thread_immediately_after_reply(all_prompts):
    assert (
        "immediately after replying" in all_prompts
        or "immediately after" in all_prompts
    ), "Prompt must instruct resolving a thread immediately after replying to it"


def test_prompt_posts_summary_comment(all_prompts):
    assert "Code Review Summary" in all_prompts, (
        "Prompt must instruct posting a 'Code Review Summary' comment on the PR"
    )


def test_prompt_does_not_exit_before_summary(all_prompts):
    assert "Do NOT exit" in all_prompts, (
        "Prompt must contain 'Do NOT exit' to prevent premature termination"
    )


def test_claude_args_default_includes_dangerously_skip_permissions(workflow):
    inputs = get_on(workflow)["workflow_call"].get("inputs", {})
    default = inputs.get("claude_args", {}).get("default", "")
    assert "--dangerously-skip-permissions" in default, (
        "claude_args default must include --dangerously-skip-permissions so Claude "
        "can run gh/bash commands in CI without interactive permission prompts"
    )


def test_claude_args_default_includes_max_turns(workflow):
    inputs = get_on(workflow)["workflow_call"].get("inputs", {})
    default = inputs.get("claude_args", {}).get("default", "")
    assert "--max-turns" in default, (
        "claude_args default must include --max-turns to allow enough turns to "
        "process all review threads (9+ threads × 3 sub-steps each)"
    )


def test_prompt_uses_database_id_for_reply_endpoint(all_prompts):
    assert "databaseId" in all_prompts, (
        "Prompt must use databaseId (numeric comment ID) for the REST reply endpoint; "
        "the GraphQL node ID (PRRT_...) is not accepted by /comments/{id}/replies"
    )


def test_has_multiple_claude_steps(workflow):
    """The workflow should decompose into multiple focused Claude sub-agent steps."""
    steps = workflow["jobs"]["pr-review"]["steps"]
    claude_steps = [
        s
        for s in steps
        if s.get("uses", "").startswith("anthropics/claude-code-action")
    ]
    assert len(claude_steps) >= 3, (
        f"Expected at least 3 Claude sub-agent steps, found {len(claude_steps)}. "
        "The review should be decomposed into focused sub-agents."
    )


def test_escalation_step_checks_all_claude_steps(workflow):
    """The escalation step must check max-turns on all Claude sub-agent step IDs."""
    steps = workflow["jobs"]["pr-review"]["steps"]
    escalation = [s for s in steps if "escalate" in s.get("name", "").lower()]
    assert escalation, "No escalation step found"
    condition = escalation[0].get("if", "")
    # All Claude steps with IDs should be checked
    claude_steps = [
        s
        for s in steps
        if s.get("uses", "").startswith("anthropics/claude-code-action") and "id" in s
    ]
    for step in claude_steps:
        step_id = step["id"]
        assert step_id in condition, (
            f"Escalation step must check max-turns for Claude step '{step_id}'"
        )
