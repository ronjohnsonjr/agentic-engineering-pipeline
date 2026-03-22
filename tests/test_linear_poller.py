import pytest
import respx
import httpx
from unittest.mock import AsyncMock, MagicMock

from src.integrations.linear.client import LinearClient, LINEAR_API_URL
from src.integrations.linear.poller import (
    LinearPoller,
    PollResult,
    make_thread_id,
    _has_sufficient_context,
    _extract_acceptance_criteria,
    READY_FOR_DEV_STATUS,
    NEEDS_CLARIFICATION_STATUS,
)


MOCK_API_KEY = "lin_api_testkey"
TEAM_ID = "team-1"


def _make_issue(
    issue_id: str = "issue-1",
    identifier: str = "AGE-5",
    title: str = "Build the thing",
    description: str = "Full description here.\n\n## Acceptance Criteria\n- [ ] Done",
) -> dict:
    return {
        "id": issue_id,
        "identifier": identifier,
        "title": title,
        "description": description,
        "priority": 2,
        "state": {"id": "state-1", "name": READY_FOR_DEV_STATUS},
        "team": {"id": TEAM_ID, "name": "Engineering"},
        "labels": {"nodes": []},
        "assignee": None,
    }


# ---------------------------------------------------------------------------
# Unit tests for pure helpers
# ---------------------------------------------------------------------------


def test_make_thread_id_is_deterministic():
    assert make_thread_id("issue-abc") == make_thread_id("issue-abc")


def test_make_thread_id_different_inputs():
    assert make_thread_id("issue-1") != make_thread_id("issue-2")


def test_make_thread_id_length():
    assert len(make_thread_id("any-id")) == 16


def test_has_sufficient_context_true():
    assert _has_sufficient_context({"description": "Some description"}) is True


def test_has_sufficient_context_false_empty():
    assert _has_sufficient_context({"description": ""}) is False


def test_has_sufficient_context_false_none():
    assert _has_sufficient_context({"description": None}) is False


def test_has_sufficient_context_false_missing():
    assert _has_sufficient_context({}) is False


def test_has_sufficient_context_whitespace_only():
    assert _has_sufficient_context({"description": "   \n  "}) is False


def test_extract_acceptance_criteria_present():
    description = "Intro.\n\n## Acceptance Criteria\n- [ ] Item one\n- [ ] Item two"
    result = _extract_acceptance_criteria(description)
    assert result.startswith("## Acceptance Criteria")
    assert "Item one" in result


def test_extract_acceptance_criteria_case_insensitive():
    description = "Intro.\n\n## acceptance criteria\n- [ ] Item"
    result = _extract_acceptance_criteria(description)
    assert "Item" in result


def test_extract_acceptance_criteria_absent():
    description = "No criteria section here."
    assert _extract_acceptance_criteria(description) == ""


# ---------------------------------------------------------------------------
# Integration-style tests using respx to mock Linear API
# ---------------------------------------------------------------------------


def _mock_issues_response(issues: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"data": {"team": {"issues": {"nodes": issues}}}},
    )


def _mock_states_response(states: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"data": {"team": {"states": {"nodes": states}}}},
    )


def _mock_mutation_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={"data": {"issueUpdate": {"success": True}, "commentCreate": {"success": True}}},
    )


@respx.mock
@pytest.mark.asyncio
async def test_poll_once_dispatches_ready_issue():
    client = LinearClient(api_key=MOCK_API_KEY)
    issue = _make_issue()

    respx.post(LINEAR_API_URL).mock(return_value=_mock_issues_response([issue]))

    received: list[PollResult] = []

    async def on_issue(result: PollResult) -> None:
        received.append(result)

    poller = LinearPoller(client=client, team_id=TEAM_ID, on_issue=on_issue)
    dispatched = await poller.poll_once()

    assert len(dispatched) == 1
    assert len(received) == 1
    r = received[0]
    assert r.issue_id == "issue-1"
    assert r.identifier == "AGE-5"
    assert r.title == "Build the thing"
    assert "Acceptance Criteria" in r.acceptance_criteria
    assert r.team_id == TEAM_ID


@respx.mock
@pytest.mark.asyncio
async def test_poll_once_thread_id_is_deterministic():
    client = LinearClient(api_key=MOCK_API_KEY)
    issue = _make_issue(issue_id="stable-id")
    respx.post(LINEAR_API_URL).mock(return_value=_mock_issues_response([issue]))

    received: list[PollResult] = []

    async def on_issue(result: PollResult) -> None:
        received.append(result)

    poller = LinearPoller(client=client, team_id=TEAM_ID, on_issue=on_issue)
    await poller.poll_once()

    assert received[0].thread_id == make_thread_id("stable-id")


@respx.mock
@pytest.mark.asyncio
async def test_poll_once_skips_seen_issues():
    client = LinearClient(api_key=MOCK_API_KEY)
    issue = _make_issue()

    respx.post(LINEAR_API_URL).mock(return_value=_mock_issues_response([issue]))

    call_count = 0

    async def on_issue(result: PollResult) -> None:
        nonlocal call_count
        call_count += 1

    poller = LinearPoller(client=client, team_id=TEAM_ID, on_issue=on_issue)

    # First poll should dispatch
    await poller.poll_once()
    assert call_count == 1

    # Second poll: same issue should be skipped
    await poller.poll_once()
    assert call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_poll_once_empty_returns_no_dispatches():
    client = LinearClient(api_key=MOCK_API_KEY)
    respx.post(LINEAR_API_URL).mock(return_value=_mock_issues_response([]))

    async def on_issue(result: PollResult) -> None:
        pass

    poller = LinearPoller(client=client, team_id=TEAM_ID, on_issue=on_issue)
    dispatched = await poller.poll_once()
    assert dispatched == []


@respx.mock
@pytest.mark.asyncio
async def test_poll_once_moves_no_description_to_needs_clarification():
    client = LinearClient(api_key=MOCK_API_KEY)
    issue = _make_issue(description="")

    states = [
        {"id": "s-nc", "name": NEEDS_CLARIFICATION_STATUS, "type": "unstarted"},
        {"id": "s-rfd", "name": READY_FOR_DEV_STATUS, "type": "unstarted"},
    ]

    call_count = 0

    def mock_response(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        # First call: get_issues_by_state
        if call_count == 1:
            return _mock_issues_response([issue])
        # Second call: get_team_states
        if call_count == 2:
            return _mock_states_response(states)
        # Third and fourth calls: update_issue_state, add_comment
        return _mock_mutation_response()

    respx.post(LINEAR_API_URL).mock(side_effect=mock_response)

    dispatched_issues: list[PollResult] = []

    async def on_issue(result: PollResult) -> None:
        dispatched_issues.append(result)

    poller = LinearPoller(client=client, team_id=TEAM_ID, on_issue=on_issue)
    dispatched = await poller.poll_once()

    # Issue should NOT be dispatched to the pipeline
    assert dispatched == []
    assert dispatched_issues == []


@respx.mock
@pytest.mark.asyncio
async def test_poll_once_none_description_moves_to_needs_clarification():
    client = LinearClient(api_key=MOCK_API_KEY)
    issue = _make_issue(description=None)  # type: ignore[arg-type]

    states = [{"id": "s-nc", "name": NEEDS_CLARIFICATION_STATUS, "type": "unstarted"}]

    call_count = 0

    def mock_response(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _mock_issues_response([issue])
        if call_count == 2:
            return _mock_states_response(states)
        return _mock_mutation_response()

    respx.post(LINEAR_API_URL).mock(side_effect=mock_response)

    async def on_issue(result: PollResult) -> None:
        pass

    poller = LinearPoller(client=client, team_id=TEAM_ID, on_issue=on_issue)
    dispatched = await poller.poll_once()
    assert dispatched == []


@respx.mock
@pytest.mark.asyncio
async def test_poll_once_needs_clarification_state_missing_logs_warning(caplog):
    import logging

    client = LinearClient(api_key=MOCK_API_KEY)
    issue = _make_issue(description="")
    states = [{"id": "s-rfd", "name": READY_FOR_DEV_STATUS, "type": "unstarted"}]

    call_count = 0

    def mock_response(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _mock_issues_response([issue])
        return _mock_states_response(states)

    respx.post(LINEAR_API_URL).mock(side_effect=mock_response)

    async def on_issue(result: PollResult) -> None:
        pass

    poller = LinearPoller(client=client, team_id=TEAM_ID, on_issue=on_issue)
    with caplog.at_level(logging.WARNING):
        dispatched = await poller.poll_once()

    assert dispatched == []
    assert NEEDS_CLARIFICATION_STATUS in caplog.text


@respx.mock
@pytest.mark.asyncio
async def test_client_get_issues_by_state():
    client = LinearClient(api_key=MOCK_API_KEY)
    issue = _make_issue()
    respx.post(LINEAR_API_URL).mock(return_value=_mock_issues_response([issue]))

    result = await client.get_issues_by_state(team_id=TEAM_ID, state_name=READY_FOR_DEV_STATUS)
    assert len(result) == 1
    assert result[0]["identifier"] == "AGE-5"
