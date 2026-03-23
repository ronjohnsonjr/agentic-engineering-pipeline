"""Parse agent output text into typed brief models.

Agents emit structured text with ``##`` section headers. This module extracts
those sections with regex and constructs the corresponding Pydantic models.

Expected text formats are documented next to each parse function.
"""

from __future__ import annotations

import re

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
# Helpers
# ---------------------------------------------------------------------------


def _extract_section(text: str, header: str) -> str:
    """Return the content that follows *header* up to the next ``##`` header."""
    pattern = rf"##\s+{re.escape(header)}\s*\n(.*?)(?=\n##\s|\Z)"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _bullet_list(block: str) -> list[str]:
    """Extract bullet items from a block (lines starting with ``-`` or ``*``)."""
    items: list[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")):
            items.append(stripped[2:].strip())
    return items


def _field_value(block: str, field: str) -> str:
    """Extract a single-line field value like ``Field: value``."""
    match = re.search(
        rf"^{re.escape(field)}\s*:\s*(.+)$", block, re.MULTILINE | re.IGNORECASE
    )
    return match.group(1).strip() if match else ""


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def parse_enriched_context(text: str) -> EnrichedContext:
    """Parse an ENRICHED CONTEXT section.

    Expected format::

        ## ENRICHED CONTEXT

        Linear Issue ID: AGE-94
        Issue Title: Receive enriched context payload
        Issue Body: <original issue text>
        Pipeline Stage: Clarifier (Stage 1)

        Parsed Requirements:
        - Context payload must include original issue content

        Business Requirements:
        - Enable downstream agents to consume a structured JSON payload

        Technical Acceptance Criteria:
        - EnrichedContext serialises to JSON via to_context_payload()

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
    body = _extract_section(text, "ENRICHED CONTEXT")
    if not body:
        return EnrichedContext()

    def _sub_block(label: str) -> list[str]:
        # Use `^` (with re.MULTILINE) to anchor the label to the start of a
        # line. This prevents false matches when `issue_body` text contains a
        # mid-line occurrence of a field-like label (e.g. a body that reads
        # "See Parsed Requirements:\n- old req" would previously match before
        # the real "Parsed Requirements:" section).
        match = re.search(
            rf"^{re.escape(label)}\s*:\s*\n(?:\s*\n)*((?:\s*[-*].+\n?)*)",
            body,
            re.IGNORECASE | re.MULTILINE,
        )
        return _bullet_list(match.group(1)) if match else []

    # Issue Body may span multiple lines; capture everything after "Issue Body:"
    # up to the next field or bullet section.
    # The lookahead alternation is built from EnrichedContext.model_fields so that
    # any new field added to the model is automatically included here — keeping the
    # two in sync without a manual update.
    # NOTE: field names are converted via `k.replace("_", " ").title()`, which
    # produces title-case labels (e.g. "linear_issue_id" → "Linear Issue Id").
    # The `re.IGNORECASE` flag compensates for any case discrepancies between
    # the generated label and the actual text (e.g. "Linear Issue ID" is still
    # matched). If a future field name does not map cleanly to its text label via
    # title-case (e.g. requiring "Issue ID" not "Issue Id"), `re.IGNORECASE` will
    # still match but a developer reading the generated regex may find it
    # confusing. If that becomes a maintenance pain point, consider replacing this
    # with an explicit `FIELD_LABELS: ClassVar[list[str]]` on `EnrichedContext`.
    _other_field_labels = "|".join(
        re.escape(k.replace("_", " ").title())
        for k in EnrichedContext.model_fields
        if k != "issue_body"
    )
    issue_body_match = re.search(
        rf"Issue Body\s*:\s*(.+?)(?=\n(?:{_other_field_labels})\s*:|\Z)",
        body,
        re.IGNORECASE | re.DOTALL,
    )
    issue_body = issue_body_match.group(1).strip() if issue_body_match else ""

    return EnrichedContext(
        linear_issue_id=_field_value(body, "Linear Issue ID"),
        issue_title=_field_value(body, "Issue Title"),
        issue_body=issue_body,
        pipeline_stage=_field_value(body, "Pipeline Stage"),
        parsed_requirements=_sub_block("Parsed Requirements"),
        business_requirements=_sub_block("Business Requirements"),
        technical_acceptance_criteria=_sub_block("Technical Acceptance Criteria"),
        dependencies=_sub_block("Dependencies"),
        related_issues=_sub_block("Related Issues"),
        linked_documents=_sub_block("Linked Documents"),
        relevant_code_paths=_sub_block("Relevant Code Paths"),
        architectural_constraints=_sub_block("Architectural Constraints"),
        assumptions=_sub_block("Assumptions"),
        labels=_sub_block("Labels"),
    )


def parse_clarifier_brief(text: str) -> ClarifierBrief:
    """Parse a CLARIFIER BRIEF section, including an optional ENRICHED CONTEXT.

    Expected format::

        ## CLARIFIER BRIEF

        Verdict: CLEAR

        Questions:
        - (none)

    or::

        ## CLARIFIER BRIEF

        Verdict: NEEDS_CLARITY

        Questions:
        - What is the expected API response format?
        - Should the endpoint require authentication?

    Optionally followed by::

        ## ENRICHED CONTEXT

        Linear Issue ID: AGE-94
        ...
    """
    body = _extract_section(text, "CLARIFIER BRIEF")
    if not body:
        body = text

    raw_verdict = _field_value(body, "Verdict").upper().replace(" ", "_")
    if raw_verdict not in ("CLEAR", "NEEDS_CLARITY"):
        raise ValueError(f"Unrecognised clarifier verdict: {raw_verdict!r}")

    questions_block = _extract_section(body, "Questions") if "##" in body else ""
    # Fall back to scanning for a Questions: label in the flat body
    if not questions_block:
        q_match = re.search(
            r"Questions\s*:\s*\n((?:\s*[-*].+\n?)*)", body, re.IGNORECASE
        )
        questions_block = q_match.group(1) if q_match else ""

    raw_questions = _bullet_list(questions_block)
    questions = [q for q in raw_questions if q.lower() not in ("none", "(none)")]

    enriched_context = parse_enriched_context(text)

    return ClarifierBrief(  # type: ignore[arg-type]
        verdict=raw_verdict,
        questions=questions,
        enriched_context=enriched_context,
    )


def parse_research_brief(text: str) -> ResearchBrief:
    """Parse a RESEARCH BRIEF section.

    Expected format::

        ## RESEARCH BRIEF

        Summary: One-paragraph description of findings.

        Conventions:
        - Use snake_case for all identifiers.

        Relevant Files:
        - src/foo.py
        - src/bar.py

        Risks:
        - Touching foo.py may break the bar integration.
    """
    body = _extract_section(text, "RESEARCH BRIEF")
    if not body:
        body = text

    summary = _field_value(body, "Summary")

    def _sub_block(label: str) -> list[str]:
        match = re.search(
            rf"{re.escape(label)}\s*:\s*\n(?:\s*\n)*((?:\s*[-*].+\n?)*)",
            body,
            re.IGNORECASE,
        )
        return _bullet_list(match.group(1)) if match else []

    return ResearchBrief(
        summary=summary,
        conventions=_sub_block("Conventions"),
        relevant_files=_sub_block("Relevant Files"),
        risks=_sub_block("Risks"),
    )


def parse_implementation_plan(text: str) -> ImplementationPlan:
    """Parse an IMPLEMENTATION PLAN section.

    Expected format::

        ## IMPLEMENTATION PLAN

        Issue: #42

        Steps:
        1. Create the data model
           - Add Pydantic model in src/models.py
        2. Add the API endpoint
           - Register route in src/api.py

        Out of Scope:
        - Migrations for legacy tables

        Risks:
        - Changing the model may affect serialisation.
    """
    body = _extract_section(text, "IMPLEMENTATION PLAN")
    if not body:
        body = text

    issue = _field_value(body, "Issue")

    # Extract numbered steps block
    steps_match = re.search(
        r"Steps\s*:\s*\n((?:.|\n)*?)(?=\nOut of Scope|\nRisks|\Z)",
        body,
        re.IGNORECASE,
    )
    steps: list[PlanStep] = []
    if steps_match:
        steps_block = steps_match.group(1)
        current_desc: str | None = None
        current_details: list[str] = []
        for line in steps_block.splitlines():
            numbered = re.match(r"^\s*\d+\.\s+(.+)$", line)
            bullet = re.match(r"^\s+[-*]\s+(.+)$", line)
            if numbered:
                if current_desc is not None:
                    steps.append(
                        PlanStep(description=current_desc, details=current_details)
                    )
                current_desc = numbered.group(1).strip()
                current_details = []
            elif bullet and current_desc is not None:
                current_details.append(bullet.group(1).strip())
        if current_desc is not None:
            steps.append(PlanStep(description=current_desc, details=current_details))

    def _sub_block(label: str) -> list[str]:
        match = re.search(
            rf"{re.escape(label)}\s*:\s*\n(?:\s*\n)*((?:\s*[-*].+\n?)*)",
            body,
            re.IGNORECASE,
        )
        return _bullet_list(match.group(1)) if match else []

    return ImplementationPlan(
        issue=issue,
        steps=steps,
        out_of_scope=_sub_block("Out of Scope"),
        risks=_sub_block("Risks"),
    )


def parse_test_result(text: str) -> TestResult:
    """Parse a TEST RESULT section.

    Expected format::

        ## TEST RESULT

        Stage: unit
        Passed: true
        Coverage: 87.5%

        Failures:
        - test_foo_raises_on_invalid_input
    """
    body = _extract_section(text, "TEST RESULT")
    if not body:
        body = text

    stage = _field_value(body, "Stage")
    passed_raw = _field_value(body, "Passed").lower()
    passed = passed_raw in ("true", "yes", "1", "pass", "passed")

    coverage_raw = _field_value(body, "Coverage")
    coverage_pct: float | None = None
    if coverage_raw:
        cov_match = re.search(r"[\d.]+", coverage_raw)
        if cov_match:
            coverage_pct = float(cov_match.group())

    failures_match = re.search(
        r"Failures\s*:\s*\n((?:\s*[-*].+\n?)*)", body, re.IGNORECASE
    )
    failures = _bullet_list(failures_match.group(1)) if failures_match else []

    return TestResult(
        stage=stage,
        passed=passed,
        coverage_pct=coverage_pct,
        failures=failures,
    )


def parse_review_verdict(text: str) -> ReviewVerdict:
    """Parse a REVIEW VERDICT section.

    Expected format::

        ## REVIEW VERDICT

        Verdict: CHANGES_REQUIRED
        Cycle: 2

        Blocking:
        - Missing null check in src/api.py line 42

        Suggestions:
        - Consider adding a docstring to the new function
    """
    body = _extract_section(text, "REVIEW VERDICT")
    if not body:
        body = text

    raw_verdict = _field_value(body, "Verdict").upper().replace(" ", "_")
    if raw_verdict not in ("APPROVED", "CHANGES_REQUIRED"):
        raise ValueError(f"Unrecognised review verdict: {raw_verdict!r}")

    cycle_raw = _field_value(body, "Cycle")
    cycle = int(cycle_raw) if cycle_raw.isdigit() else 1

    def _sub_block(label: str) -> list[str]:
        match = re.search(
            rf"{re.escape(label)}\s*:\s*\n(?:\s*\n)*((?:\s*[-*].+\n?)*)",
            body,
            re.IGNORECASE,
        )
        return _bullet_list(match.group(1)) if match else []

    return ReviewVerdict(
        verdict=raw_verdict,  # type: ignore[arg-type]
        blocking=_sub_block("Blocking"),
        suggestions=_sub_block("Suggestions"),
        cycle=cycle,
    )


def parse_pipeline_result(text: str) -> PipelineResult:
    """Parse a PIPELINE RESULT section.

    Expected format::

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
    body = _extract_section(text, "PIPELINE RESULT")
    if not body:
        body = text

    raw_status = _field_value(body, "Status").upper()
    if raw_status not in ("COMPLETE", "HALTED"):
        raise ValueError(f"Unrecognised pipeline status: {raw_status!r}")

    issue = _field_value(body, "Issue")
    pr_url_raw = _field_value(body, "PR")
    pr_url = pr_url_raw if pr_url_raw.startswith("http") else None

    stages_match = re.search(
        r"Stages Completed\s*:\s*\n((?:\s*[-*].+\n?)*)", body, re.IGNORECASE
    )
    stages_completed = _bullet_list(stages_match.group(1)) if stages_match else []

    skipped: dict[str, str] = {}
    skipped_match = re.search(
        r"Skipped\s*:\s*\n((?:\s*[-*].+\n?)*)", body, re.IGNORECASE
    )
    if skipped_match:
        for item in _bullet_list(skipped_match.group(1)):
            if ":" in item:
                stage, reason = item.split(":", 1)
                skipped[stage.strip()] = reason.strip()
            else:
                skipped[item] = ""

    notes = _field_value(body, "Notes")

    return PipelineResult(
        status=raw_status,  # type: ignore[arg-type]
        issue=issue,
        stages_completed=stages_completed,
        skipped=skipped,
        pr_url=pr_url,
        notes=notes,
    )
