"""Tests for the Linear pipeline state machine."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.integrations.linear.state_machine import (
    AUTHORIZED_ACTOR,
    BLOCKED_STATE,
    PIPELINE_STATES,
    VALID_TRANSITIONS,
    InvalidTransitionError,
    StateMachine,
    _build_transition_comment,
)


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


def _make_sm(client=None, state_name: str = "In Progress") -> StateMachine:
    if client is None:
        client = _make_client(state_name=state_name)
    return StateMachine(client=client, issue_id="issue-1", team_id="team-1")


# ---------------------------------------------------------------------------
# Pipeline state ordering
# ---------------------------------------------------------------------------


class TestPipelineStates:
    def test_ordered_forward_path(self):
        expected = [
            "Backlog",
            "Ready for Dev",
            "Triage",
            "In Progress",
            "In Testing",
            "In Review",
            "Done",
        ]
        assert PIPELINE_STATES == expected

    def test_blocked_state_defined(self):
        assert BLOCKED_STATE == "Blocked"

    def test_every_state_except_done_can_reach_blocked(self):
        for state in PIPELINE_STATES[:-1]:  # exclude "Done"
            assert BLOCKED_STATE in VALID_TRANSITIONS[state], (
                f"'{state}' should be able to transition to Blocked"
            )

    def test_done_has_no_forward_transitions(self):
        assert VALID_TRANSITIONS["Done"] == []

    def test_blocked_can_return_to_triage_or_in_progress(self):
        assert "Triage" in VALID_TRANSITIONS[BLOCKED_STATE]
        assert "In Progress" in VALID_TRANSITIONS[BLOCKED_STATE]


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


class TestAuthorization:
    @pytest.mark.asyncio
    async def test_non_orchestrator_raises_permission_error(self):
        sm = _make_sm(state_name="In Progress")
        with pytest.raises(PermissionError, match="orchestrator"):
            await sm.transition(to_state="In Testing", actor="coder")

    @pytest.mark.asyncio
    async def test_orchestrator_actor_is_authorized(self):
        sm = _make_sm(state_name="In Testing")
        # Should not raise
        await sm.transition(to_state="In Testing", actor=AUTHORIZED_ACTOR)


# ---------------------------------------------------------------------------
# Valid / invalid transitions
# ---------------------------------------------------------------------------


class TestTransitionValidation:
    @pytest.mark.asyncio
    async def test_valid_forward_transition(self):
        sm = _make_sm(state_name="In Progress")
        await sm.transition(
            to_state="In Progress",
            actor=AUTHORIZED_ACTOR,
            from_state="Triage",
        )
        sm._client.update_issue_state.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_transition_raises(self):
        sm = _make_sm(state_name="Done")
        with pytest.raises(InvalidTransitionError, match="Backlog"):
            await sm.transition(
                to_state="Done",
                actor=AUTHORIZED_ACTOR,
                from_state="Backlog",
            )

    @pytest.mark.asyncio
    async def test_transition_without_from_state_skips_validation(self):
        """Without from_state, any target state is accepted (API is still called)."""
        sm = _make_sm(state_name="Done")
        # No from_state → no validation → no error
        await sm.transition(to_state="Done", actor=AUTHORIZED_ACTOR)
        sm._client.update_issue_state.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_blocked_requires_stage(self):
        sm = _make_sm(state_name=BLOCKED_STATE)
        with pytest.raises(ValueError, match="stage"):
            await sm.transition(
                to_state=BLOCKED_STATE, actor=AUTHORIZED_ACTOR, error_output="err"
            )
        sm._client.update_issue_state.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_blocked_requires_error_output(self):
        sm = _make_sm(state_name=BLOCKED_STATE)
        with pytest.raises(ValueError, match="error_output"):
            await sm.transition(
                to_state=BLOCKED_STATE, actor=AUTHORIZED_ACTOR, stage="test"
            )
        sm._client.update_issue_state.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_any_state_can_transition_to_blocked_with_from_state(self):
        for from_state in PIPELINE_STATES[:-1]:
            client = _make_client(state_name=BLOCKED_STATE, state_id="blocked-id")
            sm = StateMachine(client=client, issue_id="issue-x", team_id="team-x")
            await sm.transition(
                to_state=BLOCKED_STATE,
                actor=AUTHORIZED_ACTOR,
                from_state=from_state,
                stage="test",
                error_output="assertion error",
            )
            client.update_issue_state.assert_awaited_with("issue-x", "blocked-id")


# ---------------------------------------------------------------------------
# Linear API calls
# ---------------------------------------------------------------------------


class TestLinearAPICalls:
    @pytest.mark.asyncio
    async def test_update_issue_state_called_with_resolved_id(self):
        client = _make_client(state_name="In Testing", state_id="state-42")
        sm = StateMachine(client=client, issue_id="issue-7", team_id="team-7")
        await sm.transition(to_state="In Testing", actor=AUTHORIZED_ACTOR)
        client.update_issue_state.assert_awaited_once_with("issue-7", "state-42")

    @pytest.mark.asyncio
    async def test_add_comment_called_after_state_update(self):
        client = _make_client(state_name="In Review")
        sm = StateMachine(client=client, issue_id="issue-8", team_id="team-8")
        await sm.transition(to_state="In Review", actor=AUTHORIZED_ACTOR, stage="review")
        client.add_comment.assert_awaited_once()
        comment_body = client.add_comment.call_args.args[1]
        assert "In Review" in comment_body

    @pytest.mark.asyncio
    async def test_transition_passes_agent_name_duration_outcome_to_comment(self):
        client = _make_client(state_name="In Testing", state_id="state-42")
        sm = StateMachine(client=client, issue_id="issue-7", team_id="team-7")
        await sm.transition(
            to_state="In Testing",
            actor=AUTHORIZED_ACTOR,
            stage="test",
            agent_name="unit-tester",
            duration_seconds=15.3,
            outcome="PASS",
        )
        comment_body = client.add_comment.call_args.args[1]
        assert "unit-tester" in comment_body
        assert "15.3s" in comment_body
        assert "PASS" in comment_body

    @pytest.mark.asyncio
    async def test_unknown_state_name_raises_value_error(self):
        client = MagicMock()
        client.get_team_states = AsyncMock(return_value=[{"id": "s1", "name": "Todo", "type": "unstarted"}])
        sm = StateMachine(client=client, issue_id="issue-9", team_id="team-9")
        with pytest.raises(ValueError, match="not found in team states"):
            await sm.transition(to_state="NonExistentState", actor=AUTHORIZED_ACTOR)


# ---------------------------------------------------------------------------
# transition_to_blocked convenience wrapper
# ---------------------------------------------------------------------------


class TestTransitionToBlocked:
    @pytest.mark.asyncio
    async def test_posts_diagnostic_comment(self):
        client = _make_client(state_name=BLOCKED_STATE, state_id="blocked-1")
        sm = StateMachine(client=client, issue_id="issue-b", team_id="team-b")
        await sm.transition_to_blocked(
            actor=AUTHORIZED_ACTOR,
            stage="test",
            error_output="pytest: 3 failed",
            attempt_count=2,
        )
        comment_body = client.add_comment.call_args.args[1]
        assert "pytest: 3 failed" in comment_body
        assert "Blocked" in comment_body

    @pytest.mark.asyncio
    async def test_attempt_count_in_comment(self):
        client = _make_client(state_name=BLOCKED_STATE)
        sm = StateMachine(client=client, issue_id="issue-c", team_id="team-c")
        await sm.transition_to_blocked(
            actor=AUTHORIZED_ACTOR,
            stage="implement",
            error_output="build failed",
            attempt_count=3,
        )
        comment_body = client.add_comment.call_args.args[1]
        assert "Attempt: 3" in comment_body

    @pytest.mark.asyncio
    async def test_stage_name_in_comment(self):
        client = _make_client(state_name=BLOCKED_STATE)
        sm = StateMachine(client=client, issue_id="issue-d", team_id="team-d")
        await sm.transition_to_blocked(
            actor=AUTHORIZED_ACTOR,
            stage="ci-remediate",
            error_output="timeout",
        )
        comment_body = client.add_comment.call_args.args[1]
        assert "ci-remediate" in comment_body


# ---------------------------------------------------------------------------
# Audit comment format
# ---------------------------------------------------------------------------


class TestBuildTransitionComment:
    def test_includes_timestamp(self):
        comment = _build_transition_comment(
            to_state="In Progress", stage="plan", error_output=None, attempt_count=1
        )
        # ISO-8601 UTC timestamp pattern
        assert "T" in comment and "Z" in comment

    def test_includes_target_state(self):
        comment = _build_transition_comment(
            to_state="Done", stage=None, error_output=None, attempt_count=1
        )
        assert "Done" in comment

    def test_includes_stage_when_provided(self):
        comment = _build_transition_comment(
            to_state="In Testing", stage="test", error_output=None, attempt_count=1
        )
        assert "test" in comment

    def test_no_diagnostic_for_non_blocked(self):
        comment = _build_transition_comment(
            to_state="In Review", stage="review", error_output="some error", attempt_count=1
        )
        # error_output only rendered when to_state is Blocked
        assert "some error" not in comment

    def test_diagnostic_rendered_for_blocked(self):
        comment = _build_transition_comment(
            to_state=BLOCKED_STATE,
            stage="test",
            error_output="tests failed: 5 errors",
            attempt_count=2,
        )
        assert "tests failed: 5 errors" in comment

    def test_attempt_count_shown_when_gt_1(self):
        comment = _build_transition_comment(
            to_state="In Progress", stage="plan", error_output=None, attempt_count=2
        )
        assert "Attempt: 2" in comment

    def test_attempt_count_hidden_when_1_for_non_blocked(self):
        comment = _build_transition_comment(
            to_state="In Progress", stage="plan", error_output=None, attempt_count=1
        )
        assert "Attempt" not in comment

    def test_attempt_count_always_shown_for_blocked(self):
        comment = _build_transition_comment(
            to_state=BLOCKED_STATE, stage="test", error_output="build failed", attempt_count=1
        )
        assert "Attempt: 1" in comment

    def test_includes_attribution(self):
        comment = _build_transition_comment(
            to_state="In Progress", stage="plan", error_output=None, attempt_count=1
        )
        assert AUTHORIZED_ACTOR in comment

    def test_agent_name_included_when_provided(self):
        comment = _build_transition_comment(
            to_state="In Progress", stage="implement", error_output=None,
            attempt_count=1, agent_name="programmer"
        )
        assert "programmer" in comment

    def test_agent_name_omitted_when_none(self):
        comment = _build_transition_comment(
            to_state="In Progress", stage="plan", error_output=None, attempt_count=1
        )
        assert "Agent:" not in comment

    def test_duration_included_when_provided(self):
        comment = _build_transition_comment(
            to_state="In Testing", stage="test", error_output=None,
            attempt_count=1, duration_seconds=42.5
        )
        assert "42.5s" in comment

    def test_duration_omitted_when_none(self):
        comment = _build_transition_comment(
            to_state="In Testing", stage="test", error_output=None, attempt_count=1
        )
        assert "Duration:" not in comment

    def test_outcome_included_when_provided(self):
        comment = _build_transition_comment(
            to_state="In Review", stage="review", error_output=None,
            attempt_count=1, outcome="APPROVED"
        )
        assert "APPROVED" in comment

    def test_outcome_omitted_when_none(self):
        comment = _build_transition_comment(
            to_state="In Review", stage="review", error_output=None, attempt_count=1
        )
        assert "Outcome:" not in comment

    def test_outcome_fail_set_by_transition_to_blocked(self):
        """transition_to_blocked() convenience wrapper sets outcome=FAIL."""
        comment = _build_transition_comment(
            to_state=BLOCKED_STATE, stage="test", error_output="err",
            attempt_count=1, outcome="FAIL"
        )
        assert "FAIL" in comment
