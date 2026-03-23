"""Tests for the ClarificationLoop module (AGE-90)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call

import pytest

from src.pipeline.briefs import ClarifierBrief
from src.pipeline.clarification import (
    CONFIDENCE_THRESHOLD,
    MAX_CLARIFICATION_ROUNDS,
    ClarificationLoop,
    ClarificationResult,
    ClarificationRound,
)
from src.integrations.linear.state_machine import NEEDS_CLARIFICATION_STATE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(state_name: str = NEEDS_CLARIFICATION_STATE, state_id: str = "nc-1") -> MagicMock:
    client = MagicMock()
    client.get_team_states = AsyncMock(
        return_value=[{"id": state_id, "name": state_name, "type": "unstarted"}]
    )
    client.update_issue_state = AsyncMock()
    client.add_comment = AsyncMock()
    client.get_issue_comments = AsyncMock(return_value=[])
    return client


def _make_loop(client=None) -> tuple[ClarificationLoop, MagicMock]:
    if client is None:
        client = _make_client()
    loop = ClarificationLoop(client=client, issue_id="issue-42", team_id="team-1")
    return loop, client


def _clear_brief(confidence: float = 0.95) -> ClarifierBrief:
    return ClarifierBrief(verdict="CLEAR", confidence_score=confidence)


def _needs_clarity_brief(
    questions: list[str] | None = None,
    confidence: float = 0.5,
) -> ClarifierBrief:
    return ClarifierBrief(
        verdict="NEEDS_CLARITY",
        questions=questions or ["What is the expected output format?"],
        confidence_score=confidence,
    )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_confidence_threshold_is_085():
    assert CONFIDENCE_THRESHOLD == 0.85


def test_max_rounds_is_2():
    assert MAX_CLARIFICATION_ROUNDS == 2


def test_loop_respects_constants():
    loop, _ = _make_loop()
    assert loop.CONFIDENCE_THRESHOLD == CONFIDENCE_THRESHOLD
    assert loop.MAX_ROUNDS == MAX_CLARIFICATION_ROUNDS


# ---------------------------------------------------------------------------
# needs_clarification
# ---------------------------------------------------------------------------


def test_needs_clarification_false_when_clear_and_high_confidence():
    loop, _ = _make_loop()
    brief = _clear_brief(confidence=0.95)
    assert loop.needs_clarification(brief) is False


def test_needs_clarification_true_when_needs_clarity_verdict():
    loop, _ = _make_loop()
    brief = _needs_clarity_brief()
    assert loop.needs_clarification(brief) is True


def test_needs_clarification_true_when_confidence_below_threshold():
    loop, _ = _make_loop()
    brief = ClarifierBrief(verdict="CLEAR", confidence_score=0.84)
    assert loop.needs_clarification(brief) is True


def test_needs_clarification_false_at_exact_threshold():
    loop, _ = _make_loop()
    brief = ClarifierBrief(verdict="CLEAR", confidence_score=0.85)
    assert loop.needs_clarification(brief) is False


def test_needs_clarification_true_when_clear_verdict_but_low_confidence():
    loop, _ = _make_loop()
    brief = ClarifierBrief(verdict="CLEAR", confidence_score=0.0)
    assert loop.needs_clarification(brief) is True


# ---------------------------------------------------------------------------
# run_round — resolved path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_round_returns_resolved_when_clear():
    loop, client = _make_loop()
    brief = _clear_brief(confidence=0.95)
    result = await loop.run_round(brief, round_num=1)
    assert result.resolved is True
    assert result.escalated is False
    assert result.rounds_used == 0
    client.add_comment.assert_not_awaited()
    client.update_issue_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_round_resolved_carries_empty_history_when_no_prior_rounds():
    loop, _ = _make_loop()
    brief = _clear_brief()
    result = await loop.run_round(brief, round_num=1)
    assert result.history == []


# ---------------------------------------------------------------------------
# run_round — needs clarification path (round 1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_round_posts_comment_when_needs_clarity():
    loop, client = _make_loop()
    brief = _needs_clarity_brief(questions=["What is scope?"])
    await loop.run_round(brief, round_num=1)
    # First call is our questions comment; second is the state-machine audit comment
    assert client.add_comment.await_count >= 1
    questions_comment = client.add_comment.call_args_list[0].args[1]
    assert "What is scope?" in questions_comment


@pytest.mark.asyncio
async def test_run_round_transitions_to_needs_clarification_state():
    loop, client = _make_loop()
    brief = _needs_clarity_brief()
    await loop.run_round(brief, round_num=1)
    client.update_issue_state.assert_awaited_once_with("issue-42", "nc-1")


@pytest.mark.asyncio
async def test_run_round_returns_unresolved_non_escalated_result():
    loop, client = _make_loop()
    brief = _needs_clarity_brief()
    result = await loop.run_round(brief, round_num=1)
    assert result.resolved is False
    assert result.escalated is False
    assert result.rounds_used == 1


@pytest.mark.asyncio
async def test_run_round_records_history():
    loop, client = _make_loop()
    brief = _needs_clarity_brief(questions=["Q1", "Q2"], confidence=0.6)
    await loop.run_round(brief, round_num=1)
    assert len(loop._history) == 1
    record = loop._history[0]
    assert record.round_number == 1
    assert record.questions == ["Q1", "Q2"]
    assert record.confidence_score == pytest.approx(0.6)


@pytest.mark.asyncio
async def test_run_round_includes_confidence_score_in_comment():
    loop, client = _make_loop()
    brief = ClarifierBrief(verdict="NEEDS_CLARITY", questions=["Q?"], confidence_score=0.72)
    await loop.run_round(brief, round_num=1)
    questions_comment = client.add_comment.call_args_list[0].args[1]
    assert "0.72" in questions_comment


@pytest.mark.asyncio
async def test_run_round_includes_round_number_in_comment():
    loop, client = _make_loop()
    brief = _needs_clarity_brief()
    await loop.run_round(brief, round_num=2)
    questions_comment = client.add_comment.call_args_list[0].args[1]
    assert "round 2" in questions_comment.lower() or "2/" in questions_comment


@pytest.mark.asyncio
async def test_run_round_comment_includes_reply_instructions():
    loop, client = _make_loop()
    brief = _needs_clarity_brief()
    await loop.run_round(brief, round_num=1)
    questions_comment = client.add_comment.call_args_list[0].args[1]
    assert "reply" in questions_comment.lower() or "respond" in questions_comment.lower()


# ---------------------------------------------------------------------------
# run_round — low confidence with CLEAR verdict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_round_triggers_when_confidence_below_threshold():
    loop, client = _make_loop()
    brief = ClarifierBrief(verdict="CLEAR", confidence_score=0.7, questions=["Are you sure?"])
    result = await loop.run_round(brief, round_num=1)
    assert result.resolved is False
    assert client.add_comment.await_count >= 1


# ---------------------------------------------------------------------------
# run_round — escalation path (round > MAX_ROUNDS)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_round_escalates_after_max_rounds():
    client = _make_client(state_name="Blocked", state_id="blocked-1")
    loop = ClarificationLoop(client=client, issue_id="issue-42", team_id="team-1")
    # Seed history so escalation comment has data
    loop._history.append(
        ClarificationRound(round_number=1, questions=["Q?"], confidence_score=0.5)
    )
    brief = _needs_clarity_brief()
    result = await loop.run_round(brief, round_num=MAX_CLARIFICATION_ROUNDS + 1)
    assert result.resolved is False
    assert result.escalated is True
    assert result.rounds_used == MAX_CLARIFICATION_ROUNDS


@pytest.mark.asyncio
async def test_escalation_posts_comment_before_blocking():
    client = _make_client(state_name="Blocked", state_id="blocked-1")
    loop = ClarificationLoop(client=client, issue_id="issue-42", team_id="team-1")
    brief = _needs_clarity_brief()
    await loop.run_round(brief, round_num=MAX_CLARIFICATION_ROUNDS + 1)
    # First call is our escalation comment; second is the state-machine audit comment
    assert client.add_comment.await_count >= 1
    escalation_comment = client.add_comment.call_args_list[0].args[1]
    assert "escalat" in escalation_comment.lower() or "human" in escalation_comment.lower()


@pytest.mark.asyncio
async def test_escalation_transitions_to_blocked():
    client = _make_client(state_name="Blocked", state_id="blocked-99")
    loop = ClarificationLoop(client=client, issue_id="issue-42", team_id="team-1")
    brief = _needs_clarity_brief()
    await loop.run_round(brief, round_num=MAX_CLARIFICATION_ROUNDS + 1)
    client.update_issue_state.assert_awaited_once_with("issue-42", "blocked-99")


@pytest.mark.asyncio
async def test_escalation_comment_includes_history():
    client = _make_client(state_name="Blocked", state_id="blocked-1")
    loop = ClarificationLoop(client=client, issue_id="issue-42", team_id="team-1")
    loop._history.append(
        ClarificationRound(round_number=1, questions=["What is scope?"], confidence_score=0.6)
    )
    brief = _needs_clarity_brief()
    await loop.run_round(brief, round_num=MAX_CLARIFICATION_ROUNDS + 1)
    # First call is our escalation comment (with history); second is state-machine audit
    escalation_comment = client.add_comment.call_args_list[0].args[1]
    assert "What is scope?" in escalation_comment


# ---------------------------------------------------------------------------
# Multi-round tracking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_rounds_accumulate_history():
    loop, client = _make_loop()
    brief1 = _needs_clarity_brief(questions=["Q1?"], confidence=0.6)
    await loop.run_round(brief1, round_num=1)
    assert len(loop._history) == 1

    brief2 = _needs_clarity_brief(questions=["Q2?"], confidence=0.7)
    await loop.run_round(brief2, round_num=2)
    assert len(loop._history) == 2
    assert loop._history[0].round_number == 1
    assert loop._history[1].round_number == 2


@pytest.mark.asyncio
async def test_resolved_after_round_two_carries_prior_history():
    loop, client = _make_loop()
    brief1 = _needs_clarity_brief(questions=["Q1?"])
    await loop.run_round(brief1, round_num=1)

    brief2 = _clear_brief(confidence=0.95)
    result = await loop.run_round(brief2, round_num=2)
    assert result.resolved is True
    assert len(result.history) == 1  # round 1 history is carried


# ---------------------------------------------------------------------------
# get_clarification_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_clarification_history_filters_relevant_comments():
    client = _make_client()
    client.get_issue_comments = AsyncMock(
        return_value=[
            {"id": "c1", "body": "Clarification Required (round 1/2)", "createdAt": "2026-01-01T00:00:00Z", "user": {"id": "u1", "name": "bot"}},
            {"id": "c2", "body": "LGTM, let's proceed", "createdAt": "2026-01-01T01:00:00Z", "user": {"id": "u2", "name": "human"}},
            {"id": "c3", "body": "Answered the clarification questions above", "createdAt": "2026-01-01T02:00:00Z", "user": {"id": "u2", "name": "human"}},
        ]
    )
    loop = ClarificationLoop(client=client, issue_id="issue-42", team_id="team-1")
    history = await loop.get_clarification_history()
    # Comments c1 and c3 contain "clarification"
    assert len(history) == 2
    assert history[0]["id"] == "c1"
    assert history[1]["id"] == "c3"


@pytest.mark.asyncio
async def test_get_clarification_history_returns_empty_when_no_matching_comments():
    client = _make_client()
    client.get_issue_comments = AsyncMock(
        return_value=[
            {"id": "c1", "body": "All good", "createdAt": "2026-01-01T00:00:00Z", "user": {"id": "u1", "name": "human"}},
        ]
    )
    loop = ClarificationLoop(client=client, issue_id="issue-42", team_id="team-1")
    history = await loop.get_clarification_history()
    assert history == []
