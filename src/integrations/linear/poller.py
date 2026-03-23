"""Linear issue poller for the agentic engineering pipeline.

Polls the Linear API for issues in "Ready for Dev" status,
validates context completeness, and dispatches them to the pipeline.
"""

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from .client import LinearClient

logger = logging.getLogger(__name__)

READY_FOR_DEV_STATUS = "Ready for Dev"
NEEDS_CLARIFICATION_STATUS = "Needs Clarification"
DEFAULT_POLL_INTERVAL = 30  # seconds


@dataclass
class PollResult:
    issue_id: str
    identifier: str
    title: str
    description: str
    acceptance_criteria: str
    thread_id: str
    team_id: str


def make_thread_id(issue_id: str) -> str:
    """Generate a deterministic thread ID from the issue ID."""
    return hashlib.sha256(issue_id.encode()).hexdigest()[:16]


def _has_sufficient_context(issue: dict) -> bool:
    """Return True if the issue has a non-empty description."""
    description = (issue.get("description") or "").strip()
    return bool(description)


def _extract_acceptance_criteria(description: str) -> str:
    """Extract acceptance criteria section from description if present."""
    lower = description.lower()
    idx = lower.find("## acceptance criteria")
    if idx != -1:
        return description[idx:]
    return ""


class LinearPoller:
    """Polls Linear for issues in 'Ready for Dev' status.

    Dispatches issues to the provided callback. Issues without a description
    are moved to 'Needs Clarification' instead of being dispatched.
    """

    def __init__(
        self,
        client: LinearClient,
        team_id: str,
        on_issue: Callable[[PollResult], Awaitable[None]],
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        ready_status: str = READY_FOR_DEV_STATUS,
    ) -> None:
        self._client = client
        self._team_id = team_id
        self._on_issue = on_issue
        self._poll_interval = poll_interval
        self._ready_status = ready_status
        # NOTE: deduplication is in-process only. If the poller restarts while an
        # issue is still being processed, it will be dispatched again. Add a
        # persistent store (e.g. Redis or a database) or an idempotency guard in
        # the on_issue callback if duplicate runs are unacceptable.
        self._seen: set[str] = set()

    async def poll_once(self) -> list[PollResult]:
        """Run one poll cycle. Returns the list of dispatched PollResults."""
        issues = await self._client.get_issues_by_state(
            team_id=self._team_id, state_name=self._ready_status
        )
        dispatched: list[PollResult] = []
        _team_states: list[dict] | None = None
        for issue in issues:
            issue_id = issue["id"]
            if issue_id in self._seen:
                continue

            if not _has_sufficient_context(issue):
                if _team_states is None:
                    _team_states = await self._client.get_team_states(self._team_id)
                await self._move_to_needs_clarification(issue, _team_states)
                continue

            description = (issue.get("description") or "").strip()
            result = PollResult(
                issue_id=issue_id,
                identifier=issue.get("identifier", ""),
                title=issue.get("title", ""),
                description=description,
                acceptance_criteria=_extract_acceptance_criteria(description),
                thread_id=make_thread_id(issue_id),
                team_id=self._team_id,
            )
            await self._on_issue(result)
            self._seen.add(issue_id)
            dispatched.append(result)

        return dispatched

    async def _move_to_needs_clarification(self, issue: dict, states: list[dict] | None = None) -> None:
        issue_id = issue["id"]
        identifier = issue.get("identifier", issue_id)
        logger.warning(
            "Issue %s has no description; moving to '%s'",
            identifier,
            NEEDS_CLARIFICATION_STATUS,
        )
        try:
            if states is None:
                states = await self._client.get_team_states(self._team_id)
            state_id = next(
                (
                    s["id"]
                    for s in states
                    if s["name"].lower() == NEEDS_CLARIFICATION_STATUS.lower()
                ),
                None,
            )
            if state_id:
                await self._client.update_issue_state(issue_id, state_id)
                await self._client.add_comment(
                    issue_id,
                    f"⚠️ Moved to **{NEEDS_CLARIFICATION_STATUS}**: "
                    "the issue has no description or acceptance criteria. "
                    "Please add context before re-queuing for development.",
                )
            else:
                logger.warning(
                    "State '%s' not found in team states; skipping transition",
                    NEEDS_CLARIFICATION_STATUS,
                )
        except Exception:
            logger.exception("Failed to move issue %s to Needs Clarification", identifier)

    async def run(self) -> None:
        """Run the poller indefinitely, sleeping between poll cycles."""
        logger.info(
            "LinearPoller starting: team=%s status='%s' interval=%ss",
            self._team_id,
            self._ready_status,
            self._poll_interval,
        )
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                logger.info("LinearPoller cancelled; stopping run loop")
                raise
            except Exception:
                logger.exception("Poll cycle failed")
            await asyncio.sleep(self._poll_interval)
