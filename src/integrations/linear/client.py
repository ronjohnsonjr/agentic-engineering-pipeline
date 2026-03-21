import httpx


LINEAR_API_URL = "https://api.linear.app/graphql"


class LinearClient:
    def __init__(self, api_key: str) -> None:
        self._headers = {
            "Authorization": api_key,
            "Content-Type": "application/json",
        }

    async def _query(self, query: str, variables: dict | None = None) -> dict:
        payload: dict = {"query": query}
        if variables:
            payload["variables"] = variables
        async with httpx.AsyncClient() as client:
            response = await client.post(
                LINEAR_API_URL, json=payload, headers=self._headers
            )
            response.raise_for_status()
            body = response.json()
            if "errors" in body:
                raise ValueError(f"Linear GraphQL error: {body['errors']}")
            return body["data"]

    async def get_issue(self, issue_id: str) -> dict:
        query = """
        query GetIssue($id: String!) {
          issue(id: $id) {
            id
            identifier
            title
            description
            priority
            state { id name }
            team { id name }
            labels { nodes { id name } }
            assignee { id name email }
          }
        }
        """
        data = await self._query(query, {"id": issue_id})
        return data["issue"]

    async def update_issue_state(self, issue_id: str, state_id: str) -> None:
        mutation = """
        mutation UpdateIssueState($id: String!, $stateId: String!) {
          issueUpdate(id: $id, input: { stateId: $stateId }) {
            success
          }
        }
        """
        await self._query(mutation, {"id": issue_id, "stateId": state_id})

    async def add_comment(self, issue_id: str, body: str) -> None:
        mutation = """
        mutation AddComment($issueId: String!, $body: String!) {
          commentCreate(input: { issueId: $issueId, body: $body }) {
            success
          }
        }
        """
        await self._query(mutation, {"issueId": issue_id, "body": body})

    async def get_team_states(self, team_id: str) -> list[dict]:
        query = """
        query GetTeamStates($teamId: String!) {
          team(id: $teamId) {
            states { nodes { id name type } }
          }
        }
        """
        data = await self._query(query, {"teamId": team_id})
        return data["team"]["states"]["nodes"]
