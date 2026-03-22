"""Pydantic models for each pipeline stage output (typed briefs)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EnrichedContext(BaseModel):
    """Additional context extracted from a Linear issue and architectural docs."""

    linear_issue_id: str = ""
    labels: list[str] = Field(default_factory=list)
    pipeline_stage: str = ""
    linked_documents: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    architectural_constraints: list[str] = Field(default_factory=list)


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
