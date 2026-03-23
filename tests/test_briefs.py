"""Unit tests for pipeline brief Pydantic models."""

import pytest
from pydantic import ValidationError

from src.pipeline.briefs import (
    ClarifierBrief,
    EnrichedContext,
    ImplementationPlan,
    PipelineResult,
    PlanStep,
    ResearchBrief,
    ReviewVerdict,
    TestResult,
)


# ---------------------------------------------------------------------------
# ClarifierBrief
# ---------------------------------------------------------------------------


def test_clarifier_brief_clear():
    brief = ClarifierBrief(verdict="CLEAR")
    assert brief.verdict == "CLEAR"
    assert brief.questions == []


def test_clarifier_brief_needs_clarity_with_questions():
    brief = ClarifierBrief(
        verdict="NEEDS_CLARITY",
        questions=["What is the scope?", "Which API version?"],
    )
    assert brief.verdict == "NEEDS_CLARITY"
    assert len(brief.questions) == 2


def test_clarifier_brief_invalid_verdict():
    with pytest.raises(ValidationError):
        ClarifierBrief(verdict="MAYBE")


def test_clarifier_brief_questions_default_empty():
    brief = ClarifierBrief(verdict="CLEAR")
    assert brief.questions == []


def test_clarifier_brief_confidence_score_default():
    brief = ClarifierBrief(verdict="CLEAR")
    assert brief.confidence_score == 1.0


def test_clarifier_brief_confidence_score_explicit():
    brief = ClarifierBrief(verdict="CLEAR", confidence_score=0.92)
    assert brief.confidence_score == 0.92


def test_clarifier_brief_confidence_score_needs_clarity():
    brief = ClarifierBrief(
        verdict="NEEDS_CLARITY",
        questions=["What is the scope?"],
        confidence_score=0.70,
    )
    assert brief.confidence_score == 0.70


def test_clarifier_brief_confidence_score_out_of_range_high():
    with pytest.raises(ValidationError):
        ClarifierBrief(verdict="CLEAR", confidence_score=1.5)


def test_clarifier_brief_confidence_score_out_of_range_low():
    with pytest.raises(ValidationError):
        ClarifierBrief(verdict="CLEAR", confidence_score=-0.1)


def test_clarifier_brief_confidence_score_boundary_pass_threshold():
    # 0.85 is the agent-level pass threshold (see agent prompt); the Pydantic model
    # only validates the 0.0–1.0 range, not verdict/score consistency
    brief = ClarifierBrief(verdict="CLEAR", confidence_score=0.85)
    assert brief.confidence_score == 0.85


def test_clarifier_brief_enriched_context_default():
    brief = ClarifierBrief(verdict="CLEAR")
    ctx = brief.enriched_context
    assert ctx.linear_issue_id == ""
    assert ctx.labels == []
    assert ctx.pipeline_stage == ""
    assert ctx.linked_documents == []
    assert ctx.assumptions == []
    assert ctx.architectural_constraints == []
    # New fields default to empty
    assert ctx.issue_title == ""
    assert ctx.issue_body == ""
    assert ctx.parsed_requirements == []
    assert ctx.business_requirements == []
    assert ctx.technical_acceptance_criteria == []
    assert ctx.dependencies == []
    assert ctx.related_issues == []
    assert ctx.relevant_code_paths == []


def test_clarifier_brief_enriched_context_populated():
    ctx = EnrichedContext(
        linear_issue_id="AGE-87",
        labels=["phase-1", "foundation"],
        pipeline_stage="Clarifier (Stage 2)",
        linked_documents=["https://linear.app/example/issue/AGE-87"],
        assumptions=["No breaking API changes required"],
        architectural_constraints=["Must not modify examples/consumer-workflows/"],
    )
    brief = ClarifierBrief(verdict="CLEAR", confidence_score=0.90, enriched_context=ctx)
    assert brief.enriched_context.linear_issue_id == "AGE-87"
    assert brief.enriched_context.labels == ["phase-1", "foundation"]
    assert brief.enriched_context.pipeline_stage == "Clarifier (Stage 2)"
    assert len(brief.enriched_context.linked_documents) == 1
    assert len(brief.enriched_context.assumptions) == 1
    assert len(brief.enriched_context.architectural_constraints) == 1


def test_enriched_context_standalone():
    ctx = EnrichedContext(linear_issue_id="AGE-42", labels=["local"])
    assert ctx.linear_issue_id == "AGE-42"
    assert ctx.labels == ["local"]
    assert ctx.pipeline_stage == ""


def test_enriched_context_full_payload_fields():
    ctx = EnrichedContext(
        linear_issue_id="AGE-94",
        issue_title="Receive enriched context payload",
        issue_body="As a pipeline agent I need structured context...",
        parsed_requirements=["Context payload must include original issue content"],
        business_requirements=["Enable downstream agents to consume structured JSON"],
        technical_acceptance_criteria=["EnrichedContext serialises to JSON"],
        dependencies=["AGE-87"],
        related_issues=["AGE-87"],
        linked_documents=["https://linear.app/example/issue/AGE-87"],
        relevant_code_paths=["src/pipeline/briefs.py"],
        architectural_constraints=["Must not modify examples/consumer-workflows/"],
        assumptions=["No breaking API changes required"],
        labels=["local", "phase-1"],
        pipeline_stage="Clarifier (Stage 1)",
    )
    assert ctx.issue_title == "Receive enriched context payload"
    assert ctx.issue_body == "As a pipeline agent I need structured context..."
    assert ctx.parsed_requirements == [
        "Context payload must include original issue content"
    ]
    assert ctx.business_requirements == [
        "Enable downstream agents to consume structured JSON"
    ]
    assert ctx.technical_acceptance_criteria == ["EnrichedContext serialises to JSON"]
    assert ctx.dependencies == ["AGE-87"]
    assert ctx.related_issues == ["AGE-87"]
    assert ctx.relevant_code_paths == ["src/pipeline/briefs.py"]


def test_enriched_context_to_context_payload_returns_dict():
    ctx = EnrichedContext(
        linear_issue_id="AGE-94",
        issue_title="Test issue",
        parsed_requirements=["Req 1", "Req 2"],
    )
    payload = ctx.to_context_payload()
    assert isinstance(payload, dict)
    assert payload["linear_issue_id"] == "AGE-94"
    assert payload["issue_title"] == "Test issue"
    assert payload["parsed_requirements"] == ["Req 1", "Req 2"]


def test_enriched_context_to_context_payload_is_deterministic():
    ctx = EnrichedContext(
        linear_issue_id="AGE-94",
        dependencies=["AGE-87"],
        labels=["local"],
    )
    assert ctx.to_context_payload() == ctx.to_context_payload()


def test_enriched_context_to_context_payload_json_is_string():
    import json

    ctx = EnrichedContext(linear_issue_id="AGE-94", issue_title="Test")
    json_str = ctx.to_context_payload_json()
    assert isinstance(json_str, str)
    parsed = json.loads(json_str)
    assert parsed["linear_issue_id"] == "AGE-94"


def test_enriched_context_to_context_payload_json_is_sorted():
    import json

    ctx = EnrichedContext(linear_issue_id="AGE-94")
    json_str = ctx.to_context_payload_json()
    # sort_keys=True means the JSON is stable across Python dict ordering
    parsed_keys = list(json.loads(json_str).keys())
    assert parsed_keys == sorted(parsed_keys)


def test_enriched_context_payload_contains_all_ac_fields():
    """Context payload must expose all Acceptance Criteria fields."""
    ctx = EnrichedContext()
    payload = ctx.to_context_payload()
    required_keys = {
        "issue_body",  # original issue content
        "parsed_requirements",  # parsed requirements
        "dependencies",  # identified dependencies
        "relevant_code_paths",  # relevant code paths
        "architectural_constraints",  # constraints
        "business_requirements",  # extracted business requirements
        "technical_acceptance_criteria",  # technical AC
        "related_issues",  # related issues
        "linked_documents",  # linked documents
    }
    assert required_keys.issubset(payload.keys())


# ---------------------------------------------------------------------------
# ResearchBrief
# ---------------------------------------------------------------------------


def test_research_brief_minimal():
    brief = ResearchBrief(summary="Found relevant files.")
    assert brief.summary == "Found relevant files."
    assert brief.conventions == []
    assert brief.relevant_files == []
    assert brief.risks == []


def test_research_brief_full():
    brief = ResearchBrief(
        summary="The codebase uses layered architecture.",
        conventions=["snake_case", "no global state"],
        relevant_files=["src/api.py", "src/models.py"],
        risks=["Changing models may break serialisation"],
    )
    assert len(brief.conventions) == 2
    assert len(brief.relevant_files) == 2
    assert len(brief.risks) == 1


def test_research_brief_empty_summary_is_valid():
    # Pydantic allows empty strings; gate validation enforces non-empty
    brief = ResearchBrief(summary="")
    assert brief.summary == ""


# ---------------------------------------------------------------------------
# PlanStep
# ---------------------------------------------------------------------------


def test_plan_step_description_only():
    step = PlanStep(description="Add the endpoint")
    assert step.description == "Add the endpoint"
    assert step.details == []


def test_plan_step_with_details():
    step = PlanStep(
        description="Refactor auth", details=["Move to middleware", "Add tests"]
    )
    assert len(step.details) == 2


def test_plan_step_requires_description():
    with pytest.raises(ValidationError):
        PlanStep()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ImplementationPlan
# ---------------------------------------------------------------------------


def test_implementation_plan_minimal():
    plan = ImplementationPlan(
        issue="#42",
        steps=[PlanStep(description="Do the thing")],
    )
    assert plan.issue == "#42"
    assert len(plan.steps) == 1
    assert plan.out_of_scope == []
    assert plan.risks == []


def test_implementation_plan_full():
    plan = ImplementationPlan(
        issue="#99",
        steps=[
            PlanStep(description="Step 1", details=["detail a"]),
            PlanStep(description="Step 2"),
        ],
        out_of_scope=["Legacy migration"],
        risks=["May affect performance"],
    )
    assert len(plan.steps) == 2
    assert plan.steps[0].details == ["detail a"]


def test_implementation_plan_requires_issue_and_steps():
    with pytest.raises(ValidationError):
        ImplementationPlan(steps=[PlanStep(description="x")])  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        ImplementationPlan(issue="#1")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# TestResult
# ---------------------------------------------------------------------------


def test_test_result_passing():
    result = TestResult(stage="unit", passed=True, coverage_pct=91.5)
    assert result.passed is True
    assert result.coverage_pct == 91.5
    assert result.failures == []


def test_test_result_failing():
    result = TestResult(stage="integration", passed=False, failures=["test_foo"])
    assert result.passed is False
    assert result.failures == ["test_foo"]


def test_test_result_coverage_optional():
    result = TestResult(stage="e2e", passed=True)
    assert result.coverage_pct is None


def test_test_result_requires_stage_and_passed():
    with pytest.raises(ValidationError):
        TestResult(passed=True)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ReviewVerdict
# ---------------------------------------------------------------------------


def test_review_verdict_approved():
    verdict = ReviewVerdict(verdict="APPROVED", cycle=1)
    assert verdict.verdict == "APPROVED"
    assert verdict.blocking == []
    assert verdict.suggestions == []


def test_review_verdict_changes_required():
    verdict = ReviewVerdict(
        verdict="CHANGES_REQUIRED",
        blocking=["Missing null check"],
        suggestions=["Add docstring"],
        cycle=2,
    )
    assert verdict.verdict == "CHANGES_REQUIRED"
    assert len(verdict.blocking) == 1
    assert verdict.cycle == 2


def test_review_verdict_invalid():
    with pytest.raises(ValidationError):
        ReviewVerdict(verdict="REJECTED")


def test_review_verdict_cycle_defaults_to_one():
    verdict = ReviewVerdict(verdict="APPROVED")
    assert verdict.cycle == 1


# ---------------------------------------------------------------------------
# PipelineResult
# ---------------------------------------------------------------------------


def test_pipeline_result_complete():
    result = PipelineResult(
        status="COMPLETE",
        issue="#10",
        stages_completed=["clarifier", "research"],
        pr_url="https://github.com/org/repo/pull/5",
    )
    assert result.status == "COMPLETE"
    assert result.pr_url == "https://github.com/org/repo/pull/5"


def test_pipeline_result_halted():
    result = PipelineResult(
        status="HALTED",
        issue="#10",
        notes="Clarifier returned NEEDS_CLARITY.",
    )
    assert result.status == "HALTED"
    assert result.pr_url is None


def test_pipeline_result_skipped():
    result = PipelineResult(
        status="COMPLETE",
        issue="#11",
        skipped={"backend-test": "no API changes", "frontend-test": "no UI changes"},
    )
    assert "backend-test" in result.skipped


def test_pipeline_result_invalid_status():
    with pytest.raises(ValidationError):
        PipelineResult(status="RUNNING", issue="#1")
