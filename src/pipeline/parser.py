"""Parse agent output text into typed brief models.

Agents emit structured text with ``##`` section headers. This module extracts
those sections with regex and constructs the corresponding Pydantic models.

Expected text formats are documented next to each parse function.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

from src.pipeline.briefs import (
    ClarifierBrief,
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


def parse_clarifier_brief(text: str) -> ClarifierBrief:
    """Parse a CLARIFIER BRIEF section.

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

    confidence_raw = _field_value(body, "Confidence")
    confidence_score: float = 1.0
    if confidence_raw:
        try:
            confidence_score = max(0.0, min(1.0, float(confidence_raw)))
        except ValueError:
            stripped = confidence_raw.strip()
            if stripped.endswith("%"):
                try:
                    confidence_score = max(0.0, min(1.0, float(stripped[:-1]) / 100))
                except ValueError:
                    logger.warning("Unparseable confidence value %r; defaulting to 1.0", confidence_raw)
            else:
                logger.warning("Unparseable confidence value %r; defaulting to 1.0", confidence_raw)

    return ClarifierBrief(verdict=raw_verdict, questions=questions, confidence_score=confidence_score)  # type: ignore[arg-type]


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

        Affected Files:
        - src/foo.py:10-40 -- handles request routing

        Interfaces:
        - def handle_request(req: Request) -> Response

        Existing Tests:
        - tests/test_foo.py -- covers request routing

        Patterns:
        - Use dependency injection for all service objects (src/services.py:1-20)

        Risks:
        - Touching foo.py may break the bar integration.

        Open Questions:
        - Should the new endpoint require authentication?
    """
    body = _extract_section(text, "RESEARCH BRIEF")
    if not body:
        body = text

    summary = _field_value(body, "Summary")

    def _sub_block(label: str) -> list[str]:
        match = re.search(
            rf"{re.escape(label)}\s*:\s*\n((?:\s*[-*].+\n?)*)", body, re.IGNORECASE
        )
        return _bullet_list(match.group(1)) if match else []

    return ResearchBrief(
        summary=summary,
        conventions=_sub_block("Conventions"),
        relevant_files=_sub_block("Relevant Files"),
        affected_files=_sub_block("Affected Files"),
        interfaces=_sub_block("Interfaces"),
        existing_tests=_sub_block("Existing Tests"),
        patterns=_sub_block("Patterns to Follow"),
        risks=_sub_block("Risks"),
        open_questions=_sub_block("Open Questions for Planner"),
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
                    steps.append(PlanStep(description=current_desc, details=current_details))
                current_desc = numbered.group(1).strip()
                current_details = []
            elif bullet and current_desc is not None:
                current_details.append(bullet.group(1).strip())
        if current_desc is not None:
            steps.append(PlanStep(description=current_desc, details=current_details))

    def _sub_block(label: str) -> list[str]:
        match = re.search(
            rf"{re.escape(label)}\s*:\s*\n((?:\s*[-*].+\n?)*)", body, re.IGNORECASE
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
            rf"{re.escape(label)}\s*:\s*\n((?:\s*[-*].+\n?)*)", body, re.IGNORECASE
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
