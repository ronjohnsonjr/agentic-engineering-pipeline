import pytest
import respx
import httpx

from src.integrations.linear.client import LinearClient, LINEAR_API_URL


MOCK_API_KEY = "lin_api_testkey"


@respx.mock
@pytest.mark.asyncio
async def test_get_issue_returns_issue_data():
    client = LinearClient(api_key=MOCK_API_KEY)
    issue_payload = {
        "id": "abc-123",
        "identifier": "ENG-42",
        "title": "Fix the thing",
        "description": "Do the fix",
        "priority": 2,
        "state": {"id": "state-1", "name": "Todo"},
        "team": {"id": "team-1", "name": "Engineering"},
        "labels": {"nodes": []},
        "assignee": None,
    }
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json={"data": {"issue": issue_payload}})
    )
    result = await client.get_issue("abc-123")
    assert result["identifier"] == "ENG-42"
    assert result["title"] == "Fix the thing"


@respx.mock
@pytest.mark.asyncio
async def test_update_issue_state_calls_mutation():
    client = LinearClient(api_key=MOCK_API_KEY)
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(
            200, json={"data": {"issueUpdate": {"success": True}}}
        )
    )
    # Should not raise
    await client.update_issue_state("abc-123", "state-99")


@respx.mock
@pytest.mark.asyncio
async def test_add_comment_calls_mutation():
    client = LinearClient(api_key=MOCK_API_KEY)
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(
            200, json={"data": {"commentCreate": {"success": True}}}
        )
    )
    await client.add_comment("abc-123", "Great PR!")


@respx.mock
@pytest.mark.asyncio
async def test_get_team_states_returns_list():
    client = LinearClient(api_key=MOCK_API_KEY)
    states = [
        {"id": "s1", "name": "Todo", "type": "unstarted"},
        {"id": "s2", "name": "In Progress", "type": "started"},
        {"id": "s3", "name": "Done", "type": "completed"},
    ]
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={"data": {"team": {"states": {"nodes": states}}}},
        )
    )
    result = await client.get_team_states("team-1")
    assert len(result) == 3
    assert result[1]["name"] == "In Progress"


@respx.mock
@pytest.mark.asyncio
async def test_graphql_error_raises_value_error():
    client = LinearClient(api_key=MOCK_API_KEY)
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={"errors": [{"message": "Not found"}]},
        )
    )
    with pytest.raises(ValueError, match="Linear GraphQL error"):
        await client.get_issue("bad-id")


@respx.mock
@pytest.mark.asyncio
async def test_http_error_raises():
    client = LinearClient(api_key=MOCK_API_KEY)
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(401, text="Unauthorized")
    )
    with pytest.raises(httpx.HTTPStatusError):
        await client.get_issue("abc-123")
