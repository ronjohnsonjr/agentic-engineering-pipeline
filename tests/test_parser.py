"""Unit tests for pipeline brief text parsers."""

import pytest

from src.pipeline.parser import (
    _ENRICHED_CONTEXT_FIELD_LABELS,
    parse_clarifier_brief,
    parse_enriched_context,
    parse_implementation_plan,
    parse_pipeline_result,
    parse_review_verdict,
    parse_test_result,
    parse_research_brief,
)


# ---------------------------------------------------------------------------
# parse_clarifier_brief
# ---------------------------------------------------------------------------

CLARIFIER_CLEAR = """\
## CLARIFIER BRIEF

Verdict: CLEAR

Questions:
- (none)
"""

CLARIFIER_NEEDS_CLARITY = """\
## CLARIFIER BRIEF

Verdict: NEEDS_CLARITY

Questions:
- What is the expected API response format?
- Should the endpoint require authentication?
"""


def test_parse_clarifier_clear():
    brief = parse_clarifier_brief(CLARIFIER_CLEAR)
    assert brief.verdict == "CLEAR"
    assert brief.questions == []


def test_parse_clarifier_needs_clarity():
    brief = parse_clarifier_brief(CLARIFIER_NEEDS_CLARITY)
    assert brief.verdict == "NEEDS_CLARITY"
    assert len(brief.questions) == 2
    assert "What is the expected API response format?" in brief.questions


def test_parse_clarifier_invalid_verdict():
    bad = "## CLARIFIER BRIEF\n\nVerdict: UNKNOWN\n"
    with pytest.raises(ValueError, match="Unrecognised clarifier verdict"):
        parse_clarifier_brief(bad)


def test_parse_clarifier_embedded_in_larger_output():
    text = """\
Agent output starts here.

## CLARIFIER BRIEF

Verdict: CLEAR

Questions:
- (none)

## Some Other Section

Other content.
"""
    brief = parse_clarifier_brief(text)
    assert brief.verdict == "CLEAR"


# ---------------------------------------------------------------------------
# parse_enriched_context
# ---------------------------------------------------------------------------

ENRICHED_CONTEXT_FULL = """\
## ENRICHED CONTEXT

Linear Issue ID: AGE-94
Issue Title: Receive enriched context payload
Issue Body: As a pipeline agent I need structured context.
Pipeline Stage: Clarifier (Stage 1)

Parsed Requirements:
- Context payload must include original issue content
- Payload formatted as structured JSON

Business Requirements:
- Enable downstream agents to consume structured JSON

Technical Acceptance Criteria:
- EnrichedContext serialises to JSON via to_context_payload()
- All AC fields present in the payload dict

Dependencies:
- AGE-87

Related Issues:
- AGE-87

Linked Documents:
- https://linear.app/example/issue/AGE-87

Relevant Code Paths:
- src/pipeline/briefs.py
- src/pipeline/parser.py

Architectural Constraints:
- Must not modify examples/consumer-workflows/

Assumptions:
- No breaking API changes required

Labels:
- local
- phase-1
"""


def test_parse_enriched_context_full():
    ctx = parse_enriched_context(ENRICHED_CONTEXT_FULL)
    assert ctx.linear_issue_id == "AGE-94"
    assert ctx.issue_title == "Receive enriched context payload"
    assert "structured context" in ctx.issue_body
    assert ctx.pipeline_stage == "Clarifier (Stage 1)"
    assert (
        "Context payload must include original issue content" in ctx.parsed_requirements
    )
    assert len(ctx.parsed_requirements) == 2
    assert ctx.business_requirements == [
        "Enable downstream agents to consume structured JSON"
    ]
    assert len(ctx.technical_acceptance_criteria) == 2
    assert ctx.dependencies == ["AGE-87"]
    assert ctx.related_issues == ["AGE-87"]
    assert len(ctx.linked_documents) == 1
    assert "src/pipeline/briefs.py" in ctx.relevant_code_paths
    assert "src/pipeline/parser.py" in ctx.relevant_code_paths
    assert ctx.architectural_constraints == [
        "Must not modify examples/consumer-workflows/"
    ]
    assert ctx.assumptions == ["No breaking API changes required"]
    assert "local" in ctx.labels
    assert "phase-1" in ctx.labels


def test_parse_enriched_context_multiline_issue_body():
    text = """\
## ENRICHED CONTEXT

Linear Issue ID: AGE-10
Issue Body: First line.
  Second line (continuation).
Pipeline Stage: Stage 1

Parsed Requirements:
- Req
"""
    ctx = parse_enriched_context(text)
    assert ctx.issue_body == "First line.\n  Second line (continuation)."
    assert "Pipeline Stage" not in ctx.issue_body  # must not bleed into next field
    assert ctx.pipeline_stage == "Stage 1"


def test_parse_enriched_context_missing_section_returns_empty():
    ctx = parse_enriched_context("## CLARIFIER BRIEF\n\nVerdict: CLEAR\n")
    assert ctx.linear_issue_id == ""
    assert ctx.parsed_requirements == []
    assert ctx.issue_title == ""


def test_parse_enriched_context_blank_line_before_bullets():
    """_sub_block must capture bullets even when a blank line follows the label."""
    text = """\
## ENRICHED CONTEXT

Linear Issue ID: AGE-20

Parsed Requirements:

- First req
- Second req

Labels:

- local
"""
    ctx = parse_enriched_context(text)
    assert ctx.parsed_requirements == ["First req", "Second req"]
    assert ctx.labels == ["local"]


def test_parse_enriched_context_sub_block_does_not_match_plain_prose_body():
    """_sub_block matches the real section when issue_body is plain prose."""
    text = """\
## ENRICHED CONTEXT

Issue Body: This ticket supersedes the old one.
Pipeline Stage: Stage 1

Parsed Requirements:
- Real requirement
"""
    ctx = parse_enriched_context(text)
    assert ctx.parsed_requirements == ["Real requirement"]
    assert "Pipeline Stage" not in ctx.issue_body


def test_parse_enriched_context_sub_block_does_not_match_label_like_issue_body():
    """_sub_block must not match a field-like label mid-line inside issue_body text.

    An issue body such as "See Parsed Requirements:\\n- old req" contains a
    string that looks like a section label followed by a bullet. The `_sub_block`
    helper must match only the *real* section (anchored to the start of a line),
    not the occurrence embedded in the issue body text.
    """
    text = """\
## ENRICHED CONTEXT

Issue Body: See Parsed Requirements:
- old req
Pipeline Stage: Stage 1

Parsed Requirements:
- Real requirement
"""
    ctx = parse_enriched_context(text)
    assert ctx.parsed_requirements == ["Real requirement"]
    assert ctx.pipeline_stage == "Stage 1"


def test_parse_enriched_context_issue_body_truncated_at_known_field_label():
    """Known limitation: issue_body is truncated when a line starts with a known field label.

    The lookahead stops at any line whose start matches a field label from
    EnrichedContext.model_fields, even if that line is part of the issue body
    text. Pin this behaviour so any future fix is visible.
    """
    text = """\
## ENRICHED CONTEXT

Issue Body: Background:
Linked Documents: http://prior-ticket
Pipeline Stage: Stage 1
"""
    ctx = parse_enriched_context(text)
    # The issue body is truncated before "Linked Documents:" because that label
    # appears at the start of a line and matches the lookahead alternation.
    # TODO: Fix by pre-stripping the issue body section before running
    # sub-block extraction, so embedded field-like labels can't escape.
    # Tracked: https://github.com/ronjohnsonjr/agentic-engineering-pipeline/issues/84
    assert ctx.issue_body == "Background:"
    assert ctx.pipeline_stage == "Stage 1"


def test_parse_enriched_context_empty_issue_body():
    """issue_body returns "" when Issue Body: is present but has no value."""
    text = "## ENRICHED CONTEXT\n\nIssue Body:\nPipeline Stage: Stage 1\n"
    ctx = parse_enriched_context(text)
    assert ctx.issue_body == ""
    assert ctx.pipeline_stage == "Stage 1"


def test_parse_enriched_context_partial_fields():
    text = """\
## ENRICHED CONTEXT

Linear Issue ID: AGE-10
Issue Title: Simple fix

Parsed Requirements:
- Fix the bug
"""
    ctx = parse_enriched_context(text)
    assert ctx.linear_issue_id == "AGE-10"
    assert ctx.issue_title == "Simple fix"
    assert ctx.parsed_requirements == ["Fix the bug"]
    assert ctx.dependencies == []
    assert ctx.related_issues == []


def test_parse_clarifier_brief_with_enriched_context():
    text = """\
## CLARIFIER BRIEF

Verdict: CLEAR

Questions:
- (none)

## ENRICHED CONTEXT

Linear Issue ID: AGE-94
Issue Title: Receive enriched context payload

Parsed Requirements:
- Context payload must include original issue content

Dependencies:
- AGE-87

Relevant Code Paths:
- src/pipeline/briefs.py
"""
    brief = parse_clarifier_brief(text)
    assert brief.verdict == "CLEAR"
    assert brief.questions == []
    assert brief.enriched_context.linear_issue_id == "AGE-94"
    assert brief.enriched_context.issue_title == "Receive enriched context payload"
    assert brief.enriched_context.parsed_requirements == [
        "Context payload must include original issue content"
    ]
    assert brief.enriched_context.dependencies == ["AGE-87"]
    assert "src/pipeline/briefs.py" in brief.enriched_context.relevant_code_paths


def test_parse_clarifier_brief_needs_clarity_with_enriched_context():
    text = """\
## CLARIFIER BRIEF

Verdict: NEEDS_CLARITY

Questions:
- What is the expected output format?

## ENRICHED CONTEXT

Linear Issue ID: AGE-55
Issue Title: Ambiguous feature

Parsed Requirements:
- Some requirement
"""
    brief = parse_clarifier_brief(text)
    assert brief.verdict == "NEEDS_CLARITY"
    assert "What is the expected output format?" in brief.questions
    assert brief.enriched_context.linear_issue_id == "AGE-55"


def test_parse_clarifier_brief_enriched_context_payload_is_dict():
    text = """\
## CLARIFIER BRIEF

Verdict: CLEAR

Questions:
- (none)

## ENRICHED CONTEXT

Linear Issue ID: AGE-94
Issue Title: Test

Parsed Requirements:
- Req 1
"""
    brief = parse_clarifier_brief(text)
    payload = brief.enriched_context.to_context_payload()
    assert isinstance(payload, dict)
    assert payload["linear_issue_id"] == "AGE-94"
    assert payload["parsed_requirements"] == ["Req 1"]


def test_parse_clarifier_brief_no_enriched_context_returns_default():
    """parse_clarifier_brief propagates a default EnrichedContext when no ENRICHED CONTEXT block is present."""
    text = """\
## CLARIFIER BRIEF

Verdict: CLEAR

Questions:
- (none)
"""
    brief = parse_clarifier_brief(text)
    assert brief.verdict == "CLEAR"
    assert brief.enriched_context.linear_issue_id == ""
    assert brief.enriched_context.parsed_requirements == []
    assert brief.enriched_context.issue_title == ""


def test_enriched_context_field_labels_contains_known_labels():
    """_ENRICHED_CONTEXT_FIELD_LABELS must include known canonical label strings.

    The constant stores re.escape()-d labels joined with ``|``, so we compare
    against the escaped form of each expected label.
    """
    import re as _re

    for expected in ("Parsed Requirements", "Linear Issue ID", "Technical Acceptance Criteria"):
        escaped = _re.escape(expected)
        assert escaped in _ENRICHED_CONTEXT_FIELD_LABELS, (
            f"Expected escaped label {escaped!r} to appear in _ENRICHED_CONTEXT_FIELD_LABELS"
        )


# ---------------------------------------------------------------------------
# parse_research_brief
# ---------------------------------------------------------------------------

RESEARCH_BRIEF = """\
## RESEARCH BRIEF

Summary: The codebase uses a layered architecture with FastAPI on top.

Conventions:
- Use snake_case for all module-level names
- Tests live next to the module they test

Relevant Files:
- src/api.py
- src/models.py
- tests/test_api.py

Affected Files:
- src/api.py:10-40 -- handles request routing

Interfaces:
- def handle_request(req: Request) -> Response -- main entry point

Existing Tests:
- tests/test_api.py -- covers request routing end-to-end

Patterns to Follow:
- Use dependency injection for all service objects (src/services.py:1-20)

Risks:
- Changing models.py may break downstream serialisation

Open Questions for Planner:
- Should the new endpoint require authentication?
"""


def test_parse_research_brief_full():
    brief = parse_research_brief(RESEARCH_BRIEF)
    assert "layered architecture" in brief.summary
    assert "Use snake_case for all module-level names" in brief.conventions
    assert "src/api.py" in brief.relevant_files
    assert "tests/test_api.py" in brief.relevant_files
    assert len(brief.risks) == 1


def test_parse_research_brief_affected_files():
    brief = parse_research_brief(RESEARCH_BRIEF)
    assert len(brief.affected_files) == 1
    assert "src/api.py:10-40 -- handles request routing" in brief.affected_files


def test_parse_research_brief_interfaces():
    brief = parse_research_brief(RESEARCH_BRIEF)
    assert len(brief.interfaces) == 1
    assert "def handle_request(req: Request) -> Response -- main entry point" in brief.interfaces


def test_parse_research_brief_existing_tests():
    brief = parse_research_brief(RESEARCH_BRIEF)
    assert len(brief.existing_tests) == 1
    assert "tests/test_api.py -- covers request routing end-to-end" in brief.existing_tests


def test_parse_research_brief_patterns():
    brief = parse_research_brief(RESEARCH_BRIEF)
    assert len(brief.patterns) == 1
    assert "Use dependency injection for all service objects (src/services.py:1-20)" in brief.patterns


def test_parse_research_brief_open_questions():
    brief = parse_research_brief(RESEARCH_BRIEF)
    assert len(brief.open_questions) == 1
    assert "Should the new endpoint require authentication?" in brief.open_questions


def test_parse_research_brief_no_conventions():
    text = """\
## RESEARCH BRIEF

Summary: Minimal codebase.

Relevant Files:
- src/main.py

Risks:
"""
    brief = parse_research_brief(text)
    assert brief.summary == "Minimal codebase."
    assert brief.conventions == []
    assert brief.relevant_files == ["src/main.py"]
    assert brief.risks == []
    assert brief.affected_files == []
    assert brief.interfaces == []
    assert brief.existing_tests == []
    assert brief.patterns == []
    assert brief.open_questions == []


def test_parse_research_brief_new_fields_absent():
    text = """\
## RESEARCH BRIEF

Summary: Legacy format without new sections.

Conventions:
- snake_case

Relevant Files:
- src/legacy.py

Risks:
- May affect existing consumers
"""
    brief = parse_research_brief(text)
    assert brief.summary == "Legacy format without new sections."
    assert brief.affected_files == []
    assert brief.interfaces == []
    assert brief.existing_tests == []
    assert brief.patterns == []
    assert brief.open_questions == []


# ---------------------------------------------------------------------------
# parse_implementation_plan
# ---------------------------------------------------------------------------

IMPL_PLAN = """\
## IMPLEMENTATION PLAN

Issue: #42

Steps:
1. Create the Pydantic model
   - Add to src/models.py
   - Follow existing naming convention
2. Add the API endpoint
   - Register in src/api.py
3. Write unit tests

Out of Scope:
- Database migrations
- Frontend changes

Risks:
- Changing model may affect serialisation
"""


def test_parse_implementation_plan_full():
    plan = parse_implementation_plan(IMPL_PLAN)
    assert plan.issue == "#42"
    assert len(plan.steps) == 3
    assert plan.steps[0].description == "Create the Pydantic model"
    assert "Add to src/models.py" in plan.steps[0].details
    assert "Database migrations" in plan.out_of_scope
    assert len(plan.risks) == 1


def test_parse_implementation_plan_no_details():
    text = """\
## IMPLEMENTATION PLAN

Issue: #7

Steps:
1. Do the thing
2. Write tests

Out of Scope:

Risks:
"""
    plan = parse_implementation_plan(text)
    assert len(plan.steps) == 2
    assert plan.steps[0].details == []
    assert plan.out_of_scope == []


# ---------------------------------------------------------------------------
# parse_test_result
# ---------------------------------------------------------------------------

TEST_RESULT_PASS = """\
## TEST RESULT

Stage: unit
Passed: true
Coverage: 87.5%

Failures:
"""

TEST_RESULT_FAIL = """\
## TEST RESULT

Stage: integration
Passed: false
Coverage: 62.0%

Failures:
- test_create_user_returns_201
- test_delete_user_cascade
"""


def test_parse_test_result_passing():
    result = parse_test_result(TEST_RESULT_PASS)
    assert result.stage == "unit"
    assert result.passed is True
    assert result.coverage_pct == 87.5
    assert result.failures == []


def test_parse_test_result_failing():
    result = parse_test_result(TEST_RESULT_FAIL)
    assert result.stage == "integration"
    assert result.passed is False
    assert result.coverage_pct == 62.0
    assert "test_create_user_returns_201" in result.failures
    assert len(result.failures) == 2


def test_parse_test_result_no_coverage():
    text = """\
## TEST RESULT

Stage: e2e
Passed: true

Failures:
"""
    result = parse_test_result(text)
    assert result.coverage_pct is None
    assert result.passed is True


def test_parse_test_result_passed_variants():
    for value in ("true", "yes", "pass", "passed", "True", "YES"):
        text = f"## TEST RESULT\n\nStage: unit\nPassed: {value}\n"
        result = parse_test_result(text)
        assert result.passed is True, f"Expected True for Passed: {value}"


def test_parse_test_result_failed_variants():
    for value in ("false", "no", "fail", "failed", "False"):
        text = f"## TEST RESULT\n\nStage: unit\nPassed: {value}\n"
        result = parse_test_result(text)
        assert result.passed is False, f"Expected False for Passed: {value}"


# ---------------------------------------------------------------------------
# parse_review_verdict
# ---------------------------------------------------------------------------

REVIEW_APPROVED = """\
## REVIEW VERDICT

Verdict: APPROVED
Cycle: 1

Blocking:

Suggestions:
- Consider extracting the helper to a utility module
"""

REVIEW_CHANGES = """\
## REVIEW VERDICT

Verdict: CHANGES_REQUIRED
Cycle: 2

Blocking:
- Missing null check in src/api.py line 42
- Unhandled exception in delete handler

Suggestions:
- Add docstring to the new function
"""


def test_parse_review_verdict_approved():
    verdict = parse_review_verdict(REVIEW_APPROVED)
    assert verdict.verdict == "APPROVED"
    assert verdict.cycle == 1
    assert verdict.blocking == []
    assert len(verdict.suggestions) == 1


def test_parse_review_verdict_changes_required():
    verdict = parse_review_verdict(REVIEW_CHANGES)
    assert verdict.verdict == "CHANGES_REQUIRED"
    assert verdict.cycle == 2
    assert len(verdict.blocking) == 2
    assert "Missing null check in src/api.py line 42" in verdict.blocking


def test_parse_review_verdict_invalid():
    text = "## REVIEW VERDICT\n\nVerdict: REJECTED\nCycle: 1\n"
    with pytest.raises(ValueError, match="Unrecognised review verdict"):
        parse_review_verdict(text)


# ---------------------------------------------------------------------------
# parse_pipeline_result
# ---------------------------------------------------------------------------

PIPELINE_COMPLETE = """\
## PIPELINE RESULT

Status: COMPLETE
Issue: #42
PR: https://github.com/org/repo/pull/7

Stages Completed:
- clarifier
- research
- planner
- coder
- unit-test
- reviewer

Skipped:
- backend-test: no API changes detected
- frontend-test: no UI surface affected

Notes: All stages completed within budget.
"""

PIPELINE_HALTED = """\
## PIPELINE RESULT

Status: HALTED
Issue: #15
PR: none

Stages Completed:
- clarifier

Skipped:

Notes: Clarifier returned NEEDS_CLARITY; awaiting author response.
"""


def test_parse_pipeline_result_complete():
    result = parse_pipeline_result(PIPELINE_COMPLETE)
    assert result.status == "COMPLETE"
    assert result.issue == "#42"
    assert result.pr_url == "https://github.com/org/repo/pull/7"
    assert "clarifier" in result.stages_completed
    assert len(result.stages_completed) == 6
    assert result.skipped["backend-test"] == "no API changes detected"
    assert result.skipped["frontend-test"] == "no UI surface affected"
    assert "within budget" in result.notes


def test_parse_pipeline_result_halted():
    result = parse_pipeline_result(PIPELINE_HALTED)
    assert result.status == "HALTED"
    assert result.issue == "#15"
    assert result.pr_url is None
    assert result.stages_completed == ["clarifier"]
    assert result.skipped == {}


def test_parse_pipeline_result_invalid_status():
    text = "## PIPELINE RESULT\n\nStatus: RUNNING\nIssue: #1\n"
    with pytest.raises(ValueError, match="Unrecognised pipeline status"):
        parse_pipeline_result(text)
