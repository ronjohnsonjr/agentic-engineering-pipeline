"""PipelineProgressReporter: facade for posting Linear status updates at pipeline milestones."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .mapper import map_pipeline_state_to_linear
from .state_machine import BLOCKED_STATE, StateMachine

if TYPE_CHECKING:
    from .client import LinearClient
    from .config import LinearConfig


class PipelineProgressReporter:
    """High-level facade that maps pipeline milestones to Linear state transitions.

    Usage::

        reporter = PipelineProgressReporter(client=linear_client, issue_id="abc-123", team_id="team-1")
        await reporter.report_milestone("plan", "success", summary="5 steps defined")
    """

    def __init__(self, client: "LinearClient", issue_id: str, team_id: str) -> None:
        self._client = client
        self._issue_id = issue_id
        self._sm = StateMachine(client=client, issue_id=issue_id, team_id=team_id)

    async def report_milestone(
        self,
        stage: str,
        status: str,
        *,
        summary: str = "",
        pr_url: str = "",
        errors: list[str] | None = None,
        attempt_count: int = 1,
    ) -> None:
        """Report a pipeline milestone to Linear by transitioning state and posting a comment.

        Args:
            stage: Pipeline stage name (e.g. "plan", "test", "pr-created").
            status: Stage outcome — "success" or "failure".
            summary: Optional human-readable summary included in the comment.
            pr_url: Optional PR URL to include in the comment.
            errors: Optional list of error strings (used when status is "failure").
            attempt_count: Retry attempt number, used in Blocked diagnostic comments.
        """
        target_state = map_pipeline_state_to_linear(stage, status)
        outcome = "PASS" if status == "success" else "FAIL"

        if target_state == BLOCKED_STATE:
            raw_parts = ([summary] if summary else []) + (errors or [])
            raw_error = "\n".join(raw_parts) if raw_parts else "Unknown error"
            await self._sm.transition_to_blocked(
                actor="orchestrator",
                stage=stage,
                error_output=raw_error,
                attempt_count=attempt_count,
                from_state=None,
            )
        else:
            await self._sm.transition(
                to_state=target_state,
                actor="orchestrator",
                stage=stage,
                outcome=outcome,
                pr_url=pr_url,
            )

    @classmethod
    def from_config(cls, config: "LinearConfig", issue_id: str) -> "PipelineProgressReporter":
        """Create a PipelineProgressReporter from a LinearConfig.

        Args:
            config: LinearConfig with api_key and team_id.
            issue_id: The Linear issue ID to update.
        """
        from .client import LinearClient

        client = LinearClient(api_key=config.api_key)
        return cls(client=client, issue_id=issue_id, team_id=config.team_id)
