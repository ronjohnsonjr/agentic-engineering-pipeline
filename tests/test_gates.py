"""Unit tests for pipeline gate validation functions."""

import pytest

from src.pipeline.briefs import (
    ClarifierBrief,
    ImplementationPlan,
    PlanStep,
    ResearchBrief,
    ReviewVerdict,
    TestResult,
)
from src.pipeline.gates import (
    validate_clarifier_gate,
    validate_plan_gate,
    validate_research_gate,
    validate_review_gate,
    validate_test_gate,
)


# ---------------------------------------------------------------------------
# validate_clarifier_gate
# ---------------------------------------------------------------------------


async def test_clarifier_gate_passes_when_clear():
    brief = ClarifierBrief(verdict="CLEAR")
    assert await validate_clarifier_gate(brief) is True


async def test_clarifier_gate_fails_when_needs_clarity():
    brief = ClarifierBrief(verdict="NEEDS_CLARITY", questions=["What scope?"])
    assert await validate_clarifier_gate(brief) is False


async def test_clarifier_gate_fails_needs_clarity_no_questions():
    # Verdict alone determines the gate; empty questions list doesn't override
    brief = ClarifierBrief(verdict="NEEDS_CLARITY")
    assert await validate_clarifier_gate(brief) is False


# ---------------------------------------------------------------------------
# validate_research_gate
# ---------------------------------------------------------------------------


async def test_research_gate_passes_with_summary_and_files():
    brief = ResearchBrief(
        summary="Codebase uses layered architecture.",
        relevant_files=["src/api.py"],
    )
    assert await validate_research_gate(brief) is True


async def test_research_gate_fails_empty_summary():
    brief = ResearchBrief(summary="", relevant_files=["src/api.py"])
    assert await validate_research_gate(brief) is False


async def test_research_gate_fails_no_relevant_files():
    brief = ResearchBrief(summary="Some summary", relevant_files=[])
    assert await validate_research_gate(brief) is False


async def test_research_gate_fails_whitespace_only_summary():
    brief = ResearchBrief(summary="   ", relevant_files=["src/foo.py"])
    assert await validate_research_gate(brief) is False


# ---------------------------------------------------------------------------
# validate_plan_gate
# ---------------------------------------------------------------------------


async def test_plan_gate_passes_with_issue_and_steps():
    plan = ImplementationPlan(
        issue="#42",
        steps=[PlanStep(description="Implement feature")],
    )
    assert await validate_plan_gate(plan) is True


async def test_plan_gate_fails_empty_issue():
    plan = ImplementationPlan(issue="", steps=[PlanStep(description="step")])
    assert await validate_plan_gate(plan) is False


async def test_plan_gate_fails_no_steps():
    plan = ImplementationPlan(issue="#10", steps=[])
    assert await validate_plan_gate(plan) is False


async def test_plan_gate_fails_whitespace_issue():
    plan = ImplementationPlan(issue="   ", steps=[PlanStep(description="step")])
    assert await validate_plan_gate(plan) is False


# ---------------------------------------------------------------------------
# validate_test_gate
# ---------------------------------------------------------------------------


async def test_test_gate_passes_all_passing():
    results = [
        TestResult(stage="unit", passed=True),
        TestResult(stage="integration", passed=True),
        TestResult(stage="e2e", passed=True),
    ]
    assert await validate_test_gate(results) is True


async def test_test_gate_fails_one_failing():
    results = [
        TestResult(stage="unit", passed=True),
        TestResult(stage="integration", passed=False, failures=["test_db"]),
        TestResult(stage="e2e", passed=True),
    ]
    assert await validate_test_gate(results) is False


async def test_test_gate_fails_all_failing():
    results = [
        TestResult(stage="unit", passed=False),
        TestResult(stage="integration", passed=False),
    ]
    assert await validate_test_gate(results) is False


async def test_test_gate_fails_empty_list():
    assert await validate_test_gate([]) is False


async def test_test_gate_passes_single_result():
    assert await validate_test_gate([TestResult(stage="unit", passed=True)]) is True


# ---------------------------------------------------------------------------
# validate_review_gate
# ---------------------------------------------------------------------------


async def test_review_gate_passes_when_approved():
    verdict = ReviewVerdict(verdict="APPROVED", cycle=1)
    assert await validate_review_gate(verdict, cycle=1, max_cycles=3) is True


async def test_review_gate_fails_when_changes_required():
    verdict = ReviewVerdict(verdict="CHANGES_REQUIRED", blocking=["Missing test"])
    assert await validate_review_gate(verdict, cycle=1, max_cycles=3) is False


async def test_review_gate_fails_at_max_cycle():
    verdict = ReviewVerdict(verdict="CHANGES_REQUIRED", cycle=3)
    assert await validate_review_gate(verdict, cycle=3, max_cycles=3) is False


async def test_review_gate_approved_at_last_cycle():
    verdict = ReviewVerdict(verdict="APPROVED", cycle=3)
    assert await validate_review_gate(verdict, cycle=3, max_cycles=3) is True


async def test_review_gate_raises_when_cycle_exceeds_max():
    verdict = ReviewVerdict(verdict="CHANGES_REQUIRED", cycle=4)
    with pytest.raises(ValueError, match="exceeds max_cycles"):
        await validate_review_gate(verdict, cycle=4, max_cycles=3)
