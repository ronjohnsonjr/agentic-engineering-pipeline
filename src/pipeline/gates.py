"""Gate validation functions for each pipeline stage.

Each gate returns True if the downstream stage may proceed, False if it is
blocked. Raising ValueError signals a configuration error (e.g. cycle count
exceeds the configured maximum).
"""

from __future__ import annotations

from src.pipeline.briefs import (
    ClarifierBrief,
    ImplementationPlan,
    ResearchBrief,
    ReviewVerdict,
    TestResult,
)


async def validate_clarifier_gate(brief: ClarifierBrief) -> bool:
    """Return True only when the clarifier verdict is CLEAR.

    Research cannot start until this gate passes.
    """
    return brief.verdict == "CLEAR"


async def validate_research_gate(brief: ResearchBrief) -> bool:
    """Return True when the research brief contains a non-empty summary and at
    least one relevant file.

    Planner cannot start until this gate passes.
    """
    return bool(brief.summary.strip()) and bool(brief.relevant_files)


async def validate_plan_gate(brief: ImplementationPlan) -> bool:
    """Return True when the plan references an issue and contains at least one
    step.

    Programmer cannot start until this gate passes.
    """
    return bool(brief.issue.strip()) and bool(brief.steps)


async def validate_test_gate(results: list[TestResult]) -> bool:
    """Return True only when every test result in *results* passed.

    PR creation cannot start until this gate passes. An empty list is treated
    as a failure (no results means the stage did not complete).
    """
    if not results:
        return False
    return all(r.passed for r in results)


async def validate_review_gate(
    verdict: ReviewVerdict, cycle: int, max_cycles: int
) -> bool:
    """Return True when the reviewer approved the PR.

    Raises ValueError when *cycle* exceeds *max_cycles*, which indicates the
    orchestrator called this gate after the retry budget was already exhausted.
    """
    if cycle > max_cycles:
        raise ValueError(
            f"Review cycle {cycle} exceeds max_cycles {max_cycles}; "
            "pipeline should have halted before reaching this gate."
        )
    return verdict.verdict == "APPROVED"
