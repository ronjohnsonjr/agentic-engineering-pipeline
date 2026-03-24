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

# Built once from EnrichedContext.model_fields so that any new field added to
# the model is automatically included in the issue_body lookahead — no manual
# sync required. `k.replace("_", " ").title()` produces title-case labels;
# `_LABEL_OVERRIDES` corrects fields where .title() produces the wrong result
# (e.g. "Linear Issue Id" instead of "Linear Issue ID"). See
# parse_enriched_context for usage.
#
# IMPORTANT: if you ever add a field whose title-case label is a prefix
# of an existing label (e.g. "Related" would prefix "Related Issues"),
# place the longer label first in the alternation, or append it before
# the shorter one. Currently no label is a prefix of another, so order
# is not load-bearing.
_LABEL_OVERRIDES: dict[str, str] = {"linear_issue_id": "Linear Issue ID"}
_ENRICHED_CONTEXT_FIELD_LABELS = "|".join(
    re.escape(_LABEL_OVERRIDES.get(k, k.replace("_", " ").title()))
    for k in EnrichedContext.model_fields
    if k != "issue_body"
)

# Guard: ensure no escaped label is a regex-prefix of a later label in the
# alternation.  A prefix match would cause the shorter label to shadow the
# longer one, silently dropping any section whose header starts with the same
# words.  This converts that silent correctness regression into an immediate
# AssertionError on import.
_labels_raw = [
    re.escape(_LABEL_OVERRIDES.get(k, k.replace("_", " ").title()))
    for k in EnrichedContext.model_fields
    if k != "issue_body"
]
for _i, _a in enumerate(_labels_raw):
    for _b in _labels_raw[_i + 1 :]:
        assert not _b.startswith(_a), (
            f"{_a!r} is a regex-prefix of {_b!r} — "
            "reorder EnrichedContext fields so longer labels come first"
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
    """Extract bullet items from a block (lines starting with ``-`` or ``*``).

    Each bullet must be a single line.  Continuation lines (indented content
    following a bullet) are silently discarded.  Callers should ensure that
    agent prompts instruct the model to emit one logical item per line.
    """
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


def _sub_block(body: str, label: str) -> list[str]:
    """Extract bullet items from a labelled sub-section inside *body*.

    Handles an optional blank line between the label and the first bullet,
    and anchors the label to the start of a line to prevent false matches
    inside multi-line field values. Blank lines between individual bullets
    are also tolerated.

    Note: each bullet must be a single line.  The ``\\s*`` before ``[-*]``
    in the capture group can consume blank lines, but ``_bullet_list`` only
    picks lines that start with ``- `` or ``* ``; continuation lines are
    silently dropped.  Ensure agent prompts constrain output to one item
    per bullet line.

    Termination invariant: the capture group stops when it encounters a
    non-whitespace character that is not ``- `` or ``* ``.  If two labelled
    sections are separated by only a blank line and the second section's
    first content line is a bare bullet (no intervening label line), those
    bullets will be silently consumed by the first section.  Well-formed
    agent output always begins each section with a labelled header, so this
    edge case does not arise in practice.
    """
    match = re.search(
        rf"^{re.escape(label)}\s*:\s*\n(?:[ \t]*\n)*((?:\s*[-*].+\n?)*)",
        body,
        re.IGNORECASE | re.MULTILINE,
    )
    return _bullet_list(match.group(1)) if match else []


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
        # NOTE: a completely absent section and a present-but-empty section are
        # indistinguishable here — both return a default EnrichedContext().  This
        # is intentional: downstream agents receive a stable, typed object either
        # way.  If the pipeline ever needs to gate on "did the clarifier produce
        # context?", add an `Optional[EnrichedContext]` return type or a sentinel
        # field (e.g. `context_present: bool`) instead of adding heuristics here.
        return EnrichedContext()

    # Issue Body may span multiple lines; capture everything after "Issue Body:"
    # up to the next field or bullet section.
    # _ENRICHED_CONTEXT_FIELD_LABELS is a module-level constant built from
    # EnrichedContext.model_fields, so any new field is automatically included.
    # NOTE: `issue_title` is included in _ENRICHED_CONTEXT_FIELD_LABELS but
    # is an ineffective terminator in practice — in the canonical section format
    # `Issue Title:` always appears *before* `Issue Body:`, so it can never
    # terminate issue_body capture in valid input. It only fires if an agent
    # writes an out-of-order section, which is already an error condition.
    # NOTE: known limitation — the lookahead stops at any line that *starts with*
    # a known field label, even if that line is part of the issue body text
    # (e.g. an issue body that begins a line with "Linked Documents: …"). In
    # practice, structured context payloads do not embed field-like labels at the
    # start of a body line. If this becomes a real-world problem, replace the
    # programmatic alternation with an explicit `ClassVar[list[str]]` on
    # `EnrichedContext` that maps field keys to their canonical text labels.
    issue_body_match = re.search(
        rf"^Issue Body\s*:[ \t]*(.*?)(?=\n(?:{_ENRICHED_CONTEXT_FIELD_LABELS})\s*:|\Z)",
        body,
        re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )
    issue_body = issue_body_match.group(1).strip() if issue_body_match else ""

    return EnrichedContext(
        linear_issue_id=_field_value(body, "Linear Issue ID"),
        issue_title=_field_value(body, "Issue Title"),
        issue_body=issue_body,
        pipeline_stage=_field_value(body, "Pipeline Stage"),
        parsed_requirements=_sub_block(body, "Parsed Requirements"),
        business_requirements=_sub_block(body, "Business Requirements"),
        technical_acceptance_criteria=_sub_block(body, "Technical Acceptance Criteria"),
        dependencies=_sub_block(body, "Dependencies"),
        related_issues=_sub_block(body, "Related Issues"),
        linked_documents=_sub_block(body, "Linked Documents"),
        relevant_code_paths=_sub_block(body, "Relevant Code Paths"),
        architectural_constraints=_sub_block(body, "Architectural Constraints"),
        assumptions=_sub_block(body, "Assumptions"),
        labels=_sub_block(body, "Labels"),
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

    if "##" in body:
        questions_block = _extract_section(body, "Questions")
        raw_questions = _bullet_list(questions_block)
    else:
        # Use _sub_block for the flat-format fallback so blank lines between
        # "Questions:" and the first bullet are tolerated, and the label is
        # anchored to the start of a line (preventing false matches mid-text).
        raw_questions = _sub_block(body, "Questions")
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

        Affected Files:
        - src/foo.py:10-40 -- handles request routing

        Interfaces:
        - def handle_request(req: Request) -> Response

        Existing Tests:
        - tests/test_foo.py -- covers request routing

        Patterns to Follow:
        - Use dependency injection for all service objects (src/services.py:1-20)

        Risks:
        - Touching foo.py may break the bar integration.

        Open Questions for Planner:
        - Should the new endpoint require authentication?
    """
    body = _extract_section(text, "RESEARCH BRIEF")
    if not body:
        body = text

    summary = _field_value(body, "Summary")

    return ResearchBrief(
        summary=summary,
        conventions=_sub_block(body, "Conventions"),
        relevant_files=_sub_block(body, "Relevant Files"),
        affected_files=_sub_block(body, "Affected Files"),
        interfaces=_sub_block(body, "Interfaces"),
        existing_tests=_sub_block(body, "Existing Tests"),
        patterns=_sub_block(body, "Patterns to Follow"),
        risks=_sub_block(body, "Risks"),
        open_questions=_sub_block(body, "Open Questions for Planner"),
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

    return ImplementationPlan(
        issue=issue,
        steps=steps,
        out_of_scope=_sub_block(body, "Out of Scope"),
        risks=_sub_block(body, "Risks"),
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

    failures = _sub_block(body, "Failures")

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

    return ReviewVerdict(
        verdict=raw_verdict,  # type: ignore[arg-type]
        blocking=_sub_block(body, "Blocking"),
        suggestions=_sub_block(body, "Suggestions"),
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

    stages_completed = _sub_block(body, "Stages Completed")

    skipped: dict[str, str] = {}
    for item in _sub_block(body, "Skipped"):
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
