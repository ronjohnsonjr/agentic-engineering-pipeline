"""Clarification loop for ambiguous pipeline issues.

When the clarifier agent returns a low confidence score or a NEEDS_CLARITY
verdict, this module manages the multi-round clarification workflow:

1. Posts clarification questions as a formatted Linear comment.
2. Transitions the issue to "Needs Clarification" status.
3. Tracks question history across rounds (max 2).
4. Escalates to human review (Blocked) if clarity is not reached after
   the maximum number of rounds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.pipeline.briefs import CLARIFIER_CONFIDENCE_THRESHOLD, ClarifierBrief
from src.integrations.linear.state_machine import (
    NEEDS_CLARIFICATION_STATE,
    StateMachine,
)

if TYPE_CHECKING:
    from src.integrations.linear.client import LinearClient


CONFIDENCE_THRESHOLD: float = CLARIFIER_CONFIDENCE_THRESHOLD
MAX_CLARIFICATION_ROUNDS: int = 2


@dataclass
class ClarificationRound:
    """Record of a single clarification round."""

    round_number: int
    questions: list[str]
    confidence_score: float
    timestamp: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )


@dataclass
class ClarificationResult:
    """Outcome of running one or more clarification rounds."""

    resolved: bool
    rounds_used: int
    history: list[ClarificationRound] = field(default_factory=list)
    escalated: bool = False


class ClarificationLoop:
    """Manages the human-in-the-loop clarification workflow.

    Usage::

        loop = ClarificationLoop(client=linear_client, issue_id="abc-123", team_id="team-1")
        result = await loop.run_round(brief, round_num=1)
        if result.resolved:
            # proceed to research
        elif result.escalated:
            # pipeline is blocked; human must intervene
        else:
            # wait for human response, then re-evaluate with a new brief
    """

    CONFIDENCE_THRESHOLD: float = CONFIDENCE_THRESHOLD
    MAX_ROUNDS: int = MAX_CLARIFICATION_ROUNDS

    def __init__(
        self,
        client: "LinearClient",
        issue_id: str,
        team_id: str,
    ) -> None:
        self._client = client
        self._issue_id = issue_id
        self._team_id = team_id
        self._history: list[ClarificationRound] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def needs_clarification(self, brief: ClarifierBrief) -> bool:
        """Return True if *brief* requires human clarification before proceeding."""
        return (
            brief.verdict == "NEEDS_CLARITY"
            or brief.confidence_score < self.CONFIDENCE_THRESHOLD
        )

    async def run_round(
        self,
        brief: ClarifierBrief,
        round_num: int,
    ) -> ClarificationResult:
        """Run one clarification round.

        If the brief is clear, returns a resolved result immediately.
        If the round budget is exhausted, escalates to human (Blocked state).
        Otherwise posts questions and transitions to Needs Clarification.

        Args:
            brief: Output from the clarifier agent for this round.
            round_num: 1-based round counter (must be >= 1).

        Returns:
            ClarificationResult describing whether the issue is resolved,
            still pending, or escalated.
        """
        if not self.needs_clarification(brief):
            return ClarificationResult(
                resolved=True,
                rounds_used=round_num - 1,
                history=list(self._history),
            )

        if round_num > self.MAX_ROUNDS:
            await self._escalate(rounds_used=self.MAX_ROUNDS)
            return ClarificationResult(
                resolved=False,
                rounds_used=self.MAX_ROUNDS,
                history=list(self._history),
                escalated=True,
            )

        if round_num != len(self._history) + 1:
            raise ValueError(
                f"round_num {round_num} does not match history length "
                f"{len(self._history)} + 1; rounds must be called sequentially."
            )
        await self._post_questions(brief, round_num)
        return ClarificationResult(
            resolved=False,
            rounds_used=round_num,
            history=list(self._history),
            escalated=False,
        )

    async def get_clarification_history(self) -> list[dict]:
        """Fetch all comments from the Linear issue that mention clarification.

        Useful for retrieving human responses between rounds.
        """
        comments = await self._client.get_issue_comments(self._issue_id)
        return [
            c
            for c in comments
            if "clarification" in c.get("body", "").lower()
            and not c.get("body", "").startswith("**Clarification Required**")
            and not c.get("body", "").startswith("**Escalation:")
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _post_questions(self, brief: ClarifierBrief, round_num: int) -> None:
        """Post questions as a Linear comment and transition to Needs Clarification."""
        record = ClarificationRound(
            round_number=round_num,
            questions=list(brief.questions),
            confidence_score=brief.confidence_score,
        )
        self._history.append(record)

        comment = self._build_questions_comment(brief, round_num)
        await self._client.add_comment(self._issue_id, comment)

        sm = StateMachine(
            client=self._client,
            issue_id=self._issue_id,
            team_id=self._team_id,
        )
        await sm.transition(
            to_state=NEEDS_CLARIFICATION_STATE,
            actor="orchestrator",
            stage="clarify",
            outcome="NEEDS_CLARIFICATION",
        )

    async def _escalate(self, rounds_used: int) -> None:
        """Post an escalation comment and transition the issue to Blocked."""
        comment = self._build_escalation_comment(rounds_used)
        await self._client.add_comment(self._issue_id, comment)

        sm = StateMachine(
            client=self._client,
            issue_id=self._issue_id,
            team_id=self._team_id,
        )
        await sm.transition_to_blocked(
            actor="orchestrator",
            stage="clarify",
            error_output=(
                f"Clarification could not be resolved after {rounds_used} round(s). "
                "Human intervention required."
            ),
        )

    def _build_questions_comment(
        self, brief: ClarifierBrief, round_num: int
    ) -> str:
        """Return a formatted Linear comment with the clarification questions."""
        lines = [
            f"**Clarification Required** _(round {round_num}/{self.MAX_ROUNDS})_",
            f"- Confidence Score: `{brief.confidence_score:.2f}` "
            f"(threshold: `{self.CONFIDENCE_THRESHOLD}`)",
            "",
        ]
        if brief.questions:
            lines += [
                "The following questions must be answered before implementation can proceed:",
                "",
            ]
            for i, question in enumerate(brief.questions, start=1):
                lines.append(f"{i}. {question}")
        else:
            lines.append(
                "The confidence score is below the required threshold — "
                "please add more detail to the issue description."
            )
        lines += [
            "",
            "_Please reply to this comment with answers. "
            "The pipeline will re-evaluate after your response._",
        ]
        return "\n".join(lines)

    def _build_escalation_comment(self, rounds_used: int) -> str:
        """Return a formatted escalation comment after max rounds are exhausted."""
        lines = [
            f"**Escalation: Human Review Required** "
            f"_(after {rounds_used} clarification round(s))_",
            "",
            "The clarifier agent could not reach sufficient confidence after the "
            "maximum number of clarification rounds.",
            "Manual review and intervention is required to proceed with this issue.",
        ]
        if self._history:
            lines += ["", "**Clarification history:**"]
            for record in self._history:
                lines.append(
                    f"\n_Round {record.round_number} ({record.timestamp}):_"
                )
                for q in record.questions:
                    lines.append(f"- {q}")
        return "\n".join(lines)
