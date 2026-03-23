"""Pydantic models for each pipeline stage output (typed briefs)."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field


class EnrichedContext(BaseModel):
    """Full context payload produced by the clarifier for downstream agents.

    Serialises deterministically to JSON via :meth:`to_context_payload` so any
    downstream agent or orchestrator can consume a stable, programmatic
    representation of the issue without re-parsing raw text.
    """

    # Issue provenance
    linear_issue_id: str = ""
    issue_title: str = ""
    issue_body: str = ""

    # Derived artefacts
    parsed_requirements: list[str] = Field(default_factory=list)
    business_requirements: list[str] = Field(default_factory=list)
    technical_acceptance_criteria: list[str] = Field(default_factory=list)

    # Relationships and navigation
    dependencies: list[str] = Field(default_factory=list)
    related_issues: list[str] = Field(default_factory=list)
    linked_documents: list[str] = Field(default_factory=list)
    relevant_code_paths: list[str] = Field(default_factory=list)

    # Constraints and metadata
    architectural_constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    pipeline_stage: str = ""

    def to_context_payload(self) -> dict:
        """Return a JSON-serialisable dict of the full context payload.

        This is the canonical form passed between pipeline agents.  The output
        is deterministic: the same :class:`EnrichedContext` always produces the
        same dict, with keys in alphabetical order (matching
        :meth:`to_context_payload_json`).  For a hashable, cache-key-safe
        representation use :meth:`to_context_payload_json`.
        """
        return dict(sorted(self.model_dump(mode="json").items()))

    def to_context_payload_json(self) -> str:
        """Return the context payload as a compact JSON string."""
        return json.dumps(self.to_context_payload(), sort_keys=True, separators=(",", ":"))


class ClarifierBrief(BaseModel):
    verdict: Literal["CLEAR", "NEEDS_CLARITY"]
    questions: list[str] = Field(default_factory=list)
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    enriched_context: EnrichedContext = Field(default_factory=EnrichedContext)


class ResearchBrief(BaseModel):
    summary: str
    conventions: list[str] = Field(default_factory=list)
    relevant_files: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class PlanStep(BaseModel):
    description: str
    details: list[str] = Field(default_factory=list)


class ImplementationPlan(BaseModel):
    issue: str
    steps: list[PlanStep]
    out_of_scope: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class TestResult(BaseModel):
    stage: str
    passed: bool
    coverage_pct: float | None = None
    failures: list[str] = Field(default_factory=list)


class ReviewVerdict(BaseModel):
    verdict: Literal["APPROVED", "CHANGES_REQUIRED"]
    blocking: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    cycle: int = 1


class PipelineResult(BaseModel):
    status: Literal["COMPLETE", "HALTED"]
    issue: str
    stages_completed: list[str] = Field(default_factory=list)
    skipped: dict[str, str] = Field(default_factory=dict)
    pr_url: str | None = None
    notes: str = ""
