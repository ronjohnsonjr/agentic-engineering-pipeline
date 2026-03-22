"""Deterministic Linear status state machine for the agentic pipeline.

Only the Orchestrator may call transition(); any other actor raises PermissionError.
Each transition posts a timestamped comment to the Linear issue.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import LinearClient


# Ordered forward path
PIPELINE_STATES: list[str] = [
    "Backlog",
    "Ready for Dev",
    "Triage",
    "In Progress",
    "In Testing",
    "In Review",
    "Done",
]

BLOCKED_STATE = "Blocked"

# Valid transitions per source state.
# Any state can move to Blocked (failure path).
# Forward movement follows the pipeline order; some backward steps are
# allowed for remediation cycles.
VALID_TRANSITIONS: dict[str, list[str]] = {
    "Backlog":       ["Ready for Dev", BLOCKED_STATE],
    "Ready for Dev": ["Triage",        BLOCKED_STATE],
    "Triage":        ["In Progress",   BLOCKED_STATE],
    "In Progress":   ["In Testing",    BLOCKED_STATE],
    "In Testing":    ["In Review", "In Progress", BLOCKED_STATE],
    "In Review":     ["Done", "In Testing",       BLOCKED_STATE],
    "Done":          [],
    BLOCKED_STATE:   ["Triage", "In Progress"],
}

AUTHORIZED_ACTOR = "orchestrator"


class InvalidTransitionError(Exception):
    """Raised when a state transition is not permitted."""


class StateMachine:
    """Manages Linear issue state transitions for the agentic pipeline.

    Usage::

        sm = StateMachine(client=linear_client, issue_id="abc-123", team_id="team-1")
        await sm.transition(
            to_state="In Progress",
            actor="orchestrator",
        )
    """

    def __init__(self, client: "LinearClient", issue_id: str, team_id: str) -> None:
        self._client = client
        self._issue_id = issue_id
        self._team_id = team_id

    async def _resolve_state_id(self, state_name: str) -> str:
        """Look up the Linear state ID by name for the configured team."""
        states = await self._client.get_team_states(self._team_id)
        for state in states:
            if state["name"].lower() == state_name.lower():
                return state["id"]
        available = [s["name"] for s in states]
        raise ValueError(
            f"State '{state_name}' not found in team states. Available: {available}"
        )

    async def transition(
        self,
        to_state: str,
        actor: str,
        *,
        from_state: str | None = None,
        stage: str | None = None,
        error_output: str | None = None,
        attempt_count: int = 1,
    ) -> None:
        """Transition the issue to *to_state* and post a timestamped comment.

        Args:
            to_state: Target Linear state name (must be in VALID_TRANSITIONS).
            actor: Caller identity. Must be ``"orchestrator"`` or PermissionError is raised.
            from_state: Current state name. If provided, validates the transition is
                allowed before calling the Linear API.
            stage: Pipeline stage name (used in audit comment).
            error_output: Error details when transitioning to Blocked.
            attempt_count: Number of attempts (used in Blocked diagnostic comment).

        Raises:
            PermissionError: If *actor* is not the authorized orchestrator.
            InvalidTransitionError: If *from_state* is provided and the transition
                from *from_state* to *to_state* is not in VALID_TRANSITIONS.
            ValueError: If *to_state* is not a recognised state name.
        """
        if actor != AUTHORIZED_ACTOR:
            raise PermissionError(
                f"Only '{AUTHORIZED_ACTOR}' may transition Linear states; got '{actor}'."
            )

        # Validate transition if we know the current state
        if from_state is not None:
            allowed = VALID_TRANSITIONS.get(from_state, [])
            if to_state not in allowed:
                raise InvalidTransitionError(
                    f"Transition '{from_state}' → '{to_state}' is not permitted. "
                    f"Allowed from '{from_state}': {allowed}"
                )

        state_id = await self._resolve_state_id(to_state)
        await self._client.update_issue_state(self._issue_id, state_id)

        comment = _build_transition_comment(
            to_state=to_state,
            stage=stage,
            error_output=error_output,
            attempt_count=attempt_count,
        )
        await self._client.add_comment(self._issue_id, comment)

    async def transition_to_blocked(
        self,
        actor: str,
        stage: str,
        error_output: str,
        attempt_count: int = 1,
        from_state: str | None = None,
    ) -> None:
        """Convenience wrapper: transition to Blocked with a diagnostic comment."""
        await self.transition(
            to_state=BLOCKED_STATE,
            actor=actor,
            from_state=from_state,
            stage=stage,
            error_output=error_output,
            attempt_count=attempt_count,
        )


def _build_transition_comment(
    to_state: str,
    stage: str | None,
    error_output: str | None,
    attempt_count: int,
) -> str:
    """Build the audit comment posted to Linear on each state change."""
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = [
        f"**Status → {to_state}** _(pipeline audit)_",
        f"- Timestamp: `{timestamp}`",
    ]
    if stage:
        lines.append(f"- Stage: `{stage}`")
    if attempt_count > 1:
        lines.append(f"- Attempt: {attempt_count}")
    if to_state == BLOCKED_STATE and error_output:
        lines.append("\n**Diagnostic:**")
        lines.append(f"```\n{error_output.strip()}\n```")
    return "\n".join(lines)
