"""Tests for PipelineProgressReporter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.integrations.linear.config import LinearConfig
from src.integrations.linear.progress import PipelineProgressReporter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(state_name: str = "In Progress", state_id: str = "state-99") -> MagicMock:
    client = MagicMock()
    client.get_team_states = AsyncMock(
        return_value=[{"id": state_id, "name": state_name, "type": "started"}]
    )
    client.update_issue_state = AsyncMock()
    client.add_comment = AsyncMock()
    return client


def _make_reporter(state_name: str = "In Progress", state_id: str = "state-99") -> tuple[PipelineProgressReporter, MagicMock]:
    client = _make_client(state_name=state_name, state_id=state_id)
    reporter = PipelineProgressReporter(client=client, issue_id="issue-1", team_id="team-1")
    return reporter, client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPipelineProgressReporter:
    @pytest.mark.asyncio
    async def test_report_plan_success(self):
        reporter, client = _make_reporter(state_name="In Progress")
        await reporter.report_milestone("plan", "success", summary="5 steps defined")
        client.update_issue_state.assert_awaited_once()
        client.add_comment.assert_awaited_once()
        comment_body = client.add_comment.call_args.args[1]
        assert "plan" in comment_body
        assert "5 steps defined" in comment_body

    @pytest.mark.asyncio
    async def test_report_test_success(self):
        reporter, client = _make_reporter(state_name="In Review")
        await reporter.report_milestone("test", "success")
        client.update_issue_state.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_report_test_failure_transitions_to_in_progress(self):
        # test failure maps to "In Progress" (remediation cycle), not Blocked
        reporter, client = _make_reporter(state_name="In Progress", state_id="state-ip")
        await reporter.report_milestone(
            "test",
            "failure",
            errors=["3 tests failed"],
            attempt_count=2,
        )
        client.update_issue_state.assert_awaited_once()
        comment_body = client.add_comment.call_args.args[1]
        assert "3 tests failed" in comment_body

    @pytest.mark.asyncio
    async def test_report_pr_created(self):
        reporter, client = _make_reporter(state_name="In Review")
        await reporter.report_milestone(
            "pr-created",
            "success",
            pr_url="https://github.com/org/repo/pull/42",
        )
        client.update_issue_state.assert_awaited_once()
        comment_body = client.add_comment.call_args.args[1]
        assert "https://github.com/org/repo/pull/42" in comment_body

    @pytest.mark.asyncio
    async def test_report_remediation_success(self):
        reporter, client = _make_reporter(state_name="In Progress")
        await reporter.report_milestone("remediation", "success", summary="Fixed lint errors")
        client.update_issue_state.assert_awaited_once()
        comment_body = client.add_comment.call_args.args[1]
        assert "Fixed lint errors" in comment_body

    def test_from_config(self):
        config = LinearConfig(
            api_key="test-key",
            webhook_secret="test-secret",
            team_id="team-abc",
        )
        reporter = PipelineProgressReporter.from_config(config, issue_id="issue-xyz")
        assert isinstance(reporter, PipelineProgressReporter)
        assert reporter._issue_id == "issue-xyz"

    @pytest.mark.asyncio
    async def test_report_plan_failure_transitions_to_blocked(self):
        # plan failure maps to "Blocked" state
        reporter, client = _make_reporter(state_name="Blocked", state_id="state-blocked")
        await reporter.report_milestone(
            "plan",
            "failure",
            summary="Plan failed at step 3",
            errors=["Step 3 failed"],
            attempt_count=2,
        )
        # transition_to_blocked should be called; update_issue_state must be awaited
        client.update_issue_state.assert_awaited_once()
        client.add_comment.assert_awaited_once()
        comment_body = client.add_comment.call_args.args[1]
        # error output must appear in the Blocked comment
        assert "Step 3 failed" in comment_body
        # milestone_body (which contains the summary) must also appear
        assert "Plan failed at step 3" in comment_body
        # attempt count must appear
        assert "2" in comment_body

    @pytest.mark.asyncio
    async def test_report_clarify_failure_transitions_to_blocked(self):
        # clarify failure also maps to "Blocked"
        reporter, client = _make_reporter(state_name="Blocked", state_id="state-blocked")
        await reporter.report_milestone(
            "clarify",
            "failure",
            summary="Clarification failed",
            errors=["Ambiguous requirements"],
            attempt_count=1,
        )
        client.update_issue_state.assert_awaited_once()
        client.add_comment.assert_awaited_once()
        comment_body = client.add_comment.call_args.args[1]
        assert "Ambiguous requirements" in comment_body
        assert "Clarification failed" in comment_body
        assert "1" in comment_body

    @pytest.mark.asyncio
    async def test_report_remediation_failure_transitions_to_blocked(self):
        # remediation failure maps to "Blocked"
        reporter, client = _make_reporter(state_name="Blocked", state_id="state-blocked")
        await reporter.report_milestone(
            "remediation",
            "failure",
            summary="Could not fix lint errors",
            errors=["lint: 5 errors remain"],
            attempt_count=3,
        )
        client.update_issue_state.assert_awaited_once()
        client.add_comment.assert_awaited_once()
        comment_body = client.add_comment.call_args.args[1]
        assert "lint: 5 errors remain" in comment_body
        assert "Could not fix lint errors" in comment_body
        assert "3" in comment_body
