"""Gate validation functions for each pipeline stage.

Each gate returns True if the downstream stage may proceed, False if it is
blocked. Raising ValueError signals a configuration error (e.g. cycle count
exceeds the configured maximum).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.pipeline.briefs import (
    ClarifierBrief,
    ImplementationPlan,
    ResearchBrief,
    ReviewVerdict,
    TestResult,
)

if TYPE_CHECKING:
    from src.integrations.linear.progress import PipelineProgressReporter


async def validate_clarifier_gate(
    brief: ClarifierBrief,
    *,
    reporter: "PipelineProgressReporter | None" = None,
) -> bool:
    """Return True only when the clarifier verdict is CLEAR.

    Research cannot start until this gate passes.
    """
    passed = brief.verdict == "CLEAR"
    if reporter is not None:
        status = "success" if passed else "failure"
        if passed:
            await reporter.report_milestone("clarify", status)
        else:
            questions = getattr(brief, "questions", None) or []
            errors = questions if questions else None
            summary = "Clarification questions must be resolved before research can start."
            await reporter.report_milestone("clarify", status, summary=summary, errors=errors)
    return passed


async def validate_research_gate(
    brief: ResearchBrief,
    *,
    reporter: "PipelineProgressReporter | None" = None,
) -> bool:
    """Return True when the research brief contains a non-empty summary and at
    least one relevant file.

    Planner cannot start until this gate passes.
    """
    passed = bool(brief.summary.strip()) and bool(brief.relevant_files)
    if reporter is not None:
        status = "success" if passed else "failure"
        if passed:
            summary = brief.summary.strip() or f"{len(brief.relevant_files)} relevant files identified"
            await reporter.report_milestone("research", status, summary=summary)
        else:
            errors: list[str] = []
            if not brief.summary.strip():
                errors.append("Research summary is missing or blank")
            if not brief.relevant_files:
                errors.append("No relevant files were identified for research")
            await reporter.report_milestone("research", status, errors=errors)
    return passed


async def validate_plan_gate(
    brief: ImplementationPlan,
    *,
    reporter: "PipelineProgressReporter | None" = None,
) -> bool:
    """Return True when the plan references an issue and contains at least one
    step.

    Programmer cannot start until this gate passes.
    """
    passed = bool(brief.issue.strip()) and bool(brief.steps)
    if reporter is not None:
        status = "success" if passed else "failure"
        if passed:
            await reporter.report_milestone("plan", status, summary=f"{len(brief.steps)} steps defined")
        else:
            errors: list[str] = []
            if not brief.issue.strip():
                errors.append("Plan is missing an issue reference")
            if not brief.steps:
                errors.append("Plan contains no steps")
            summary = "Plan validation failed: " + "; ".join(errors) if errors else "Plan validation failed"
            await reporter.report_milestone("plan", status, summary=summary, errors=errors)
    return passed


async def validate_test_gate(
    results: list[TestResult],
    *,
    reporter: "PipelineProgressReporter | None" = None,
) -> bool:
    """Return True only when every test result in *results* passed.

    PR creation cannot start until this gate passes. An empty list is treated
    as a failure (no results means the stage did not complete).
    """
    if not results:
        if reporter is not None:
            await reporter.report_milestone(
                "test",
                "failure",
                errors=["No test results received"],
            )
        return False
    passed = all(r.passed for r in results)
    if reporter is not None:
        if passed:
            passing = sum(1 for r in results if r.passed)
            await reporter.report_milestone(
                "test",
                "success",
                summary=f"{passing}/{len(results)} test suite(s) passed",
            )
        else:
            errors = [f for r in results for f in r.failures]
            await reporter.report_milestone("test", "failure", errors=errors)
    return passed


async def validate_review_gate(
    verdict: ReviewVerdict,
    cycle: int,
    max_cycles: int,
    *,
    reporter: "PipelineProgressReporter | None" = None,
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
    passed = verdict.verdict == "APPROVED"
    if reporter is not None:
        status = "success" if passed else "failure"
        await reporter.report_milestone("review", status)
    return passed
