"""Orchestrator: spawn and monitor downstream pipeline agents.

Coordinates the deterministic stage sequence:
  Clarifier → Researcher → Planner → Programmer
  → [Unit, Backend, Frontend] in parallel (feedback loop: failures → Programmer)
  → PR Creator → AI Reviewer (feedback loop: changes required → Remediator → Reviewer)

Each stage runs under a configurable per-agent timeout. Full run state (stage,
status, output, error, attempt) is persisted in the ``stages`` list on
``PipelineRun`` so failures are observable and retryable at the gate level.
"""

from __future__ import annotations

import asyncio
import dataclasses
import re
from typing import Literal, Protocol, runtime_checkable

from src.pipeline.briefs import (
    ClarifierBrief,
    ImplementationPlan,
    PipelineResult,
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
from src.pipeline.parser import (
    parse_clarifier_brief,
    parse_implementation_plan,
    parse_research_brief,
    parse_review_verdict,
    parse_test_result,
)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT_SECONDS: float = 300.0  # 5 min per agent call
DEFAULT_MAX_VERIFY_ATTEMPTS: int = 3    # programmer fix-verify cycles
DEFAULT_MAX_REVIEW_CYCLES: int = 3      # reviewer-remediator cycles


# ---------------------------------------------------------------------------
# Agent interface
# ---------------------------------------------------------------------------


@runtime_checkable
class AgentRunner(Protocol):
    """Minimal interface every pipeline agent must satisfy."""

    async def run(self, prompt: str) -> str:  # noqa: D102
        ...


# ---------------------------------------------------------------------------
# Run-state persistence
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class AgentRunState:
    """Captures the full state of one agent invocation.

    This record is appended to :attr:`PipelineRun.stages` immediately when
    an agent is spawned and updated when it completes, fails, or times out.
    The field ``error`` always contains the raw error text so that the pipeline
    can surface it in HALTED comments without losing context.
    """

    stage: str
    status: Literal["running", "complete", "changes_required", "failed", "timeout", "skipped"]
    output: str = ""
    error: str = ""
    attempt: int = 1


@dataclasses.dataclass
class PipelineRun:
    """Accumulates state across all stages of a single pipeline execution."""

    issue: str
    stages: list[AgentRunState] = dataclasses.field(default_factory=list)
    completed_stages: list[str] = dataclasses.field(default_factory=list)
    skipped_stages: dict[str, str] = dataclasses.field(default_factory=dict)
    pr_url: str | None = None
    halt_stage: str | None = None
    halt_reason: str | None = None

    def record(self, state: AgentRunState) -> None:
        """Append *state* to :attr:`stages`."""
        self.stages.append(state)

    def complete(self, stage: str) -> None:
        """Mark *stage* as successfully completed."""
        self.completed_stages.append(stage)

    def skip(self, stage: str, reason: str) -> None:
        """Record that *stage* was intentionally skipped with *reason*."""
        self.skipped_stages[stage] = reason
        state = AgentRunState(stage=stage, status="skipped")
        self.stages.append(state)

    def halt(self, stage: str, reason: str) -> None:
        """Record a halting failure at *stage*."""
        self.halt_stage = stage
        self.halt_reason = reason

    def to_result(self) -> PipelineResult:
        """Convert to the serialisable :class:`~src.pipeline.briefs.PipelineResult`."""
        status = "HALTED" if self.halt_stage else "COMPLETE"
        notes = self.halt_reason or ""
        return PipelineResult(
            status=status,  # type: ignore[arg-type]
            issue=self.issue,
            stages_completed=list(self.completed_stages),
            skipped=dict(self.skipped_stages),
            pr_url=self.pr_url,
            notes=notes,
        )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class Orchestrator:
    """Coordinates pipeline agents in a deterministic, gated sequence.

    All agents are injected via the constructor so that the orchestrator is
    fully testable without spawning real subprocesses.

    Args:
        clarifier: Agent that returns a CLARIFIER BRIEF.
        researcher: Agent that returns a RESEARCH BRIEF.
        planner: Agent that returns an IMPLEMENTATION PLAN.
        programmer: Agent that implements the plan and runs the quality gate.
        unit_tester: Agent that runs unit tests.
        backend_tester: Agent that runs backend/integration tests.
        frontend_tester: Agent that runs frontend/e2e tests.
        pr_creator: Agent that creates the pull request.
        remediator: Agent that applies reviewer-requested fixes.
        reviewer: Agent that reviews the PR and returns a verdict.
        timeout_seconds: Per-agent call timeout in seconds.
        max_verify_attempts: Maximum programmer fix-verify cycles.
        max_review_cycles: Maximum reviewer-remediator cycles.
    """

    def __init__(
        self,
        *,
        clarifier: AgentRunner,
        researcher: AgentRunner,
        planner: AgentRunner,
        programmer: AgentRunner,
        unit_tester: AgentRunner,
        backend_tester: AgentRunner,
        frontend_tester: AgentRunner,
        pr_creator: AgentRunner,
        remediator: AgentRunner,
        reviewer: AgentRunner,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_verify_attempts: int = DEFAULT_MAX_VERIFY_ATTEMPTS,
        max_review_cycles: int = DEFAULT_MAX_REVIEW_CYCLES,
        run_backend_tester: bool = True,
        run_frontend_tester: bool = True,
    ) -> None:
        self._clarifier = clarifier
        self._researcher = researcher
        self._planner = planner
        self._programmer = programmer
        self._unit_tester = unit_tester
        self._backend_tester = backend_tester
        self._frontend_tester = frontend_tester
        self._pr_creator = pr_creator
        self._remediator = remediator
        self._reviewer = reviewer
        self._timeout = timeout_seconds
        self._max_verify = max_verify_attempts
        self._max_review = max_review_cycles
        self._run_backend = run_backend_tester
        self._run_frontend = run_frontend_tester

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self, issue_text: str) -> PipelineResult:
        """Run the full pipeline for *issue_text* and return a result.

        Stages run in deterministic order. Each stage output is gate-checked
        before the next stage begins. On any gate failure or unrecoverable
        error the pipeline halts and returns a ``HALTED`` result.
        """
        run = PipelineRun(issue=issue_text[:120] + ("..." if len(issue_text) > 120 else ""))

        # ------------------------------------------------------------------
        # Stage 1 — Clarify
        # ------------------------------------------------------------------
        clarifier_brief = await self._run_clarifier(run, issue_text)
        if clarifier_brief is None:
            return run.to_result()

        # ------------------------------------------------------------------
        # Stage 2 — Research
        # ------------------------------------------------------------------
        research_brief = await self._run_researcher(run, issue_text, clarifier_brief)
        if research_brief is None:
            return run.to_result()

        # ------------------------------------------------------------------
        # Stage 3 — Plan
        # ------------------------------------------------------------------
        plan = await self._run_planner(run, research_brief, clarifier_brief)
        if plan is None:
            return run.to_result()

        # ------------------------------------------------------------------
        # Stage 4 — Implement (with fix-verify feedback loop)
        # ------------------------------------------------------------------
        impl_ok = await self._run_programmer(run, plan, clarifier_brief)
        if not impl_ok:
            return run.to_result()

        # ------------------------------------------------------------------
        # Stage 5 — Test (parallel; failure → halt)
        # ------------------------------------------------------------------
        tests_ok = await self._run_test_team(run)
        if not tests_ok:
            return run.to_result()

        # ------------------------------------------------------------------
        # Stage 6 — Create PR
        # ------------------------------------------------------------------
        pr_ok = await self._run_pr_creator(run)
        if not pr_ok:
            return run.to_result()

        # ------------------------------------------------------------------
        # Stage 7 — Review (with remediator feedback loop)
        # ------------------------------------------------------------------
        await self._run_review_cycle(run)

        return run.to_result()

    # ------------------------------------------------------------------
    # Stage helpers
    # ------------------------------------------------------------------

    async def _call_agent(self, agent: AgentRunner, prompt: str) -> str:
        """Call *agent* with *prompt*, enforcing :attr:`_timeout`.

        Returns the agent output string.

        Raises:
            asyncio.TimeoutError: If the agent does not respond within the timeout.
        """
        return await asyncio.wait_for(agent.run(prompt), timeout=self._timeout)

    async def _run_clarifier(
        self, run: PipelineRun, issue_text: str
    ) -> ClarifierBrief | None:
        state = AgentRunState(stage="clarifier", status="running")
        run.record(state)
        try:
            output = await self._call_agent(self._clarifier, issue_text)
            state.output = output
            brief = parse_clarifier_brief(output)
            if not await validate_clarifier_gate(brief):
                state.status = "failed"
                state.error = f"NEEDS_CLARITY: {brief.questions}"
                run.halt("clarifier", f"Clarifier returned NEEDS_CLARITY: {brief.questions}")
                return None
            state.status = "complete"
            run.complete("clarifier")
            return brief
        except asyncio.TimeoutError:
            state.status = "timeout"
            state.error = "Agent timed out"
            run.halt("clarifier", "Clarifier timed out")
            return None
        except Exception as exc:  # noqa: BLE001
            state.status = "failed"
            state.error = str(exc)
            run.halt("clarifier", f"Clarifier error: {exc}")
            return None

    async def _run_researcher(
        self,
        run: PipelineRun,
        issue_text: str,
        clarifier_brief: ClarifierBrief,
    ) -> ResearchBrief | None:
        prompt = f"{issue_text}\n\nClarifier summary:\n{clarifier_brief.model_dump_json()}"
        state = AgentRunState(stage="researcher", status="running")
        run.record(state)
        try:
            output = await self._call_agent(self._researcher, prompt)
            state.output = output
            brief = parse_research_brief(output)
            if not await validate_research_gate(brief):
                state.status = "failed"
                state.error = "Research brief incomplete (missing summary or relevant files)"
                run.halt("researcher", state.error)
                return None
            state.status = "complete"
            run.complete("researcher")
            return brief
        except asyncio.TimeoutError:
            state.status = "timeout"
            state.error = "Agent timed out"
            run.halt("researcher", "Researcher timed out")
            return None
        except Exception as exc:  # noqa: BLE001
            state.status = "failed"
            state.error = str(exc)
            run.halt("researcher", f"Researcher error: {exc}")
            return None

    async def _run_planner(
        self,
        run: PipelineRun,
        research_brief: ResearchBrief,
        clarifier_brief: ClarifierBrief,
    ) -> ImplementationPlan | None:
        prompt = (
            f"Research brief:\n{research_brief.model_dump_json()}\n\n"
            f"Acceptance criteria:\n{clarifier_brief.model_dump_json()}"
        )
        state = AgentRunState(stage="planner", status="running")
        run.record(state)
        try:
            output = await self._call_agent(self._planner, prompt)
            state.output = output
            plan = parse_implementation_plan(output)
            if not await validate_plan_gate(plan):
                state.status = "failed"
                state.error = "Implementation plan incomplete (missing issue or steps)"
                run.halt("planner", state.error)
                return None
            state.status = "complete"
            run.complete("planner")
            return plan
        except asyncio.TimeoutError:
            state.status = "timeout"
            state.error = "Agent timed out"
            run.halt("planner", "Planner timed out")
            return None
        except Exception as exc:  # noqa: BLE001
            state.status = "failed"
            state.error = str(exc)
            run.halt("planner", f"Planner error: {exc}")
            return None

    async def _run_programmer(
        self,
        run: PipelineRun,
        plan: ImplementationPlan,
        clarifier_brief: ClarifierBrief,
    ) -> bool:
        """Run the programmer with up to ``max_verify_attempts`` fix-verify cycles."""
        prompt = (
            f"Implementation plan:\n{plan.model_dump_json()}\n\n"
            f"Issue summary:\n{clarifier_brief.model_dump_json()}"
        )
        for attempt in range(1, self._max_verify + 1):
            state = AgentRunState(stage="programmer", status="running", attempt=attempt)
            run.record(state)
            try:
                output = await self._call_agent(self._programmer, prompt)
                state.output = output
                if not output.strip():
                    state.status = "failed"
                    state.error = "Programmer returned empty output"
                    if attempt >= self._max_verify:
                        run.halt("programmer", "Programmer returned empty output after all attempts")
                        return False
                    prompt = f"{prompt}\n\nPrevious attempt returned empty output. Please provide implementation."
                    continue
                state.status = "complete"
                run.complete(f"programmer (attempt {attempt})")
                return True
            except asyncio.TimeoutError:
                state.status = "timeout"
                state.error = "Agent timed out"
                if attempt >= self._max_verify:
                    run.halt("programmer", f"Programmer timed out after {attempt} attempts")
                    return False
                # pass the timeout error as context for the next attempt
                prompt = f"{prompt}\n\nPrevious attempt timed out. Please retry."
            except Exception as exc:  # noqa: BLE001
                state.status = "failed"
                state.error = str(exc)
                if attempt >= self._max_verify:
                    run.halt(
                        "programmer",
                        f"Programmer exhausted {self._max_verify} attempts. "
                        f"Last error: {exc}",
                    )
                    return False
                # Carry the error context forward so the next attempt can fix it.
                # Wrap in a delimiter so the model treats it as plain error text.
                prompt = f"{prompt}\n\n<error>\n{str(exc)[:500]}\n</error>\nPlease fix the error above and retry."

    async def _run_test_team(self, run: PipelineRun) -> bool:
        """Run unit, backend, and frontend testers in parallel.

        Backend and frontend testers are skipped when configured out. All
        invoked agents must return a PASS; a single FAIL halts the pipeline.
        """
        tasks: dict[str, asyncio.Task[str]] = {}
        running_states: dict[str, AgentRunState] = {}

        # Always run unit tests — record state before creating the task so
        # run.stages always reflects the intent before any coroutine begins.
        unit_state = AgentRunState(stage="unit-tester", status="running")
        run.record(unit_state)
        running_states["unit-tester"] = unit_state
        tasks["unit-tester"] = asyncio.create_task(
            self._call_agent(self._unit_tester, "Run unit tests.")
        )

        if self._run_backend:
            backend_state = AgentRunState(stage="backend-tester", status="running")
            run.record(backend_state)
            running_states["backend-tester"] = backend_state
            tasks["backend-tester"] = asyncio.create_task(
                self._call_agent(self._backend_tester, "Run backend/integration tests.")
            )
        else:
            run.skip("backend-tester", "no API or database changes detected")

        if self._run_frontend:
            frontend_state = AgentRunState(stage="frontend-tester", status="running")
            run.record(frontend_state)
            running_states["frontend-tester"] = frontend_state
            tasks["frontend-tester"] = asyncio.create_task(
                self._call_agent(self._frontend_tester, "Run frontend/e2e tests.")
            )
        else:
            run.skip("frontend-tester", "no UI surface changes detected")

        # Collect results (order preserved by dict insertion)
        results: list[TestResult] = []
        all_passed = True
        failed_details: list[str] = []

        for name, task in tasks.items():
            state = running_states[name]
            try:
                output = await task
                state.output = output
                result = parse_test_result(output)
                results.append(result)
                if result.passed:
                    state.status = "complete"
                    run.complete(name)
                else:
                    state.status = "failed"
                    state.error = "; ".join(result.failures)
                    all_passed = False
                    failed_details.append(f"{name}: {state.error}")
            except asyncio.TimeoutError:
                state.status = "timeout"
                state.error = "Agent timed out"
                all_passed = False
                failed_details.append(f"{name}: timed out")
            except Exception as exc:  # noqa: BLE001
                state.status = "failed"
                state.error = str(exc)
                all_passed = False
                failed_details.append(f"{name}: {exc}")

        if not await validate_test_gate(results):
            if all_passed:
                # Gate failed for a structural reason (e.g. no results produced)
                # not already captured by the per-task loop — ensure the halt
                # message is informative rather than "Test failures: ".
                failed_details.append("test gate validation failed: no results produced")
            all_passed = False

        if not all_passed:
            run.halt("test-team", "Test failures: " + "; ".join(failed_details))

        return all_passed

    async def _run_pr_creator(self, run: PipelineRun) -> bool:
        state = AgentRunState(stage="pr-creator", status="running")
        run.record(state)
        try:
            output = await self._call_agent(self._pr_creator, "Create the pull request.")
            state.output = output
            # Extract PR URL from the output; regex handles plain URLs, markdown
            # links ([text](url)), angle-bracket wrapping, etc.
            match = re.search(r"https://github\.com[^\s\)\]>\"']+/pull/\d+", output)
            pr_url: str | None = match.group(0).rstrip(".,)") if match else None
            if pr_url is None:
                state.status = "failed"
                state.error = "No pull request URL found in output"
                run.halt("pr-creator", "PR creator did not produce a pull request URL")
                return False
            state.status = "complete"
            run.pr_url = pr_url
            run.complete("pr-creator")
            return True
        except asyncio.TimeoutError:
            state.status = "timeout"
            state.error = "Agent timed out"
            run.halt("pr-creator", "PR creator timed out")
            return False
        except Exception as exc:  # noqa: BLE001
            state.status = "failed"
            state.error = str(exc)
            run.halt("pr-creator", f"PR creator error: {exc}")
            return False

    async def _run_review_cycle(self, run: PipelineRun) -> None:
        """Run reviewer → remediator feedback loop up to ``max_review_cycles`` times."""
        for cycle in range(1, self._max_review + 1):
            reviewer_state = AgentRunState(
                stage="reviewer", status="running", attempt=cycle
            )
            run.record(reviewer_state)
            try:
                output = await self._call_agent(self._reviewer, "Review the pull request.")
                reviewer_state.output = output
                verdict = parse_review_verdict(output)
            except asyncio.TimeoutError:
                reviewer_state.status = "timeout"
                reviewer_state.error = "Agent timed out"
                run.halt("reviewer", f"Reviewer timed out on cycle {cycle}")
                return
            except Exception as exc:  # noqa: BLE001
                reviewer_state.status = "failed"
                reviewer_state.error = str(exc)
                run.halt("reviewer", f"Reviewer error on cycle {cycle}: {exc}")
                return

            try:
                approved = await validate_review_gate(verdict, cycle=cycle, max_cycles=self._max_review)
            except ValueError as exc:
                reviewer_state.status = "failed"
                reviewer_state.error = str(exc)
                run.halt("reviewer", str(exc))
                return

            if approved:
                reviewer_state.status = "complete"
                run.complete(f"reviewer (cycle {cycle})")
                return

            # Gate not passed — run remediator then loop back to reviewer
            reviewer_state.status = "changes_required"
            run.complete(f"reviewer (cycle {cycle})")

            rem_state = AgentRunState(
                stage="remediator", status="running", attempt=cycle
            )
            run.record(rem_state)
            blocking = "; ".join(verdict.blocking)
            try:
                rem_output = await self._call_agent(
                    self._remediator,
                    f"Blocking issues from reviewer (cycle {cycle}):\n{blocking}",
                )
                rem_state.output = rem_output
                rem_state.status = "complete"
                run.complete(f"remediator (cycle {cycle})")
            except asyncio.TimeoutError:
                rem_state.status = "timeout"
                rem_state.error = "Agent timed out"
                run.halt("remediator", f"Remediator timed out on cycle {cycle}")
                return
            except Exception as exc:  # noqa: BLE001
                rem_state.status = "failed"
                rem_state.error = str(exc)
                run.halt("remediator", f"Remediator error on cycle {cycle}: {exc}")
                return

        # Exhausted all cycles without approval
        run.halt(
            "reviewer",
            f"Review not approved after {self._max_review} cycles.",
        )
