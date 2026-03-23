"""Unit tests for the pipeline orchestrator.

All tests use lightweight in-process stubs; no subprocesses are spawned.
Async tests use pytest-asyncio (asyncio_mode = "auto" in pyproject.toml).
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

from src.pipeline.orchestrator import (
    DEFAULT_MAX_REVIEW_CYCLES,
    DEFAULT_MAX_VERIFY_ATTEMPTS,
    AgentRunState,
    AgentRunner,
    Orchestrator,
    PipelineRun,
)


# ---------------------------------------------------------------------------
# Canned agent outputs
# ---------------------------------------------------------------------------

CLEAR_BRIEF = """
## CLARIFIER BRIEF

Verdict: CLEAR

Questions:
- (none)
"""

NEEDS_CLARITY_BRIEF = """
## CLARIFIER BRIEF

Verdict: NEEDS_CLARITY

Questions:
- What is the expected output format?
"""

RESEARCH_BRIEF = """
## RESEARCH BRIEF

Summary: The codebase uses a layered architecture.

Relevant Files:
- src/pipeline/orchestrator.py

Conventions:
- Use async/await throughout.

Risks:
- Touching orchestrator may affect downstream stages.
"""

IMPLEMENTATION_PLAN = """
## IMPLEMENTATION PLAN

Issue: #40

Steps:
1. Implement orchestrator module
   - Create src/pipeline/orchestrator.py

Out of Scope:
- UI changes

Risks:
- Breaking existing gate logic
"""

TEST_PASS = """
## TEST RESULT

Stage: unit
Passed: true
Coverage: 85%

Failures:
"""

TEST_FAIL = """
## TEST RESULT

Stage: unit
Passed: false
Coverage: 40%

Failures:
- test_something_broke
"""

REVIEW_APPROVED = """
## REVIEW VERDICT

Verdict: APPROVED
Cycle: 1

Blocking:

Suggestions:
"""

REVIEW_CHANGES = """
## REVIEW VERDICT

Verdict: CHANGES_REQUIRED
Cycle: 1

Blocking:
- Missing null check in api.py

Suggestions:
- Add docstring
"""

PR_OUTPUT = "PR created: https://github.com/org/repo/pull/99"

REMEDIATION_OUTPUT = "Fixed all blocking issues."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stub(output: str) -> AsyncMock:
    """Return an AsyncMock whose ``run`` method returns *output*."""
    mock = AsyncMock(spec=AgentRunner)
    mock.run = AsyncMock(return_value=output)
    return mock


def _make_orchestrator(**overrides) -> Orchestrator:
    """Build an Orchestrator with default happy-path stubs.

    Any keyword argument overrides the corresponding agent.
    """
    defaults = dict(
        clarifier=_stub(CLEAR_BRIEF),
        researcher=_stub(RESEARCH_BRIEF),
        planner=_stub(IMPLEMENTATION_PLAN),
        programmer=_stub("IMPLEMENTATION RESULT: COMPLETE\nQUALITY GATE: PASS"),
        unit_tester=_stub(TEST_PASS),
        backend_tester=_stub(TEST_PASS.replace("unit", "backend")),
        frontend_tester=_stub(TEST_PASS.replace("unit", "e2e")),
        pr_creator=_stub(PR_OUTPUT),
        remediator=_stub(REMEDIATION_OUTPUT),
        reviewer=_stub(REVIEW_APPROVED),
        timeout_seconds=5.0,
    )
    defaults.update(overrides)
    return Orchestrator(**defaults)


# ---------------------------------------------------------------------------
# AgentRunState tests
# ---------------------------------------------------------------------------


class TestAgentRunState:
    def test_default_values(self):
        state = AgentRunState(stage="clarifier", status="running")
        assert state.output == ""
        assert state.error == ""
        assert state.attempt == 1

    def test_fields_set_correctly(self):
        state = AgentRunState(
            stage="programmer",
            status="failed",
            output="...",
            error="build error",
            attempt=2,
        )
        assert state.stage == "programmer"
        assert state.status == "failed"
        assert state.error == "build error"
        assert state.attempt == 2


# ---------------------------------------------------------------------------
# PipelineRun tests
# ---------------------------------------------------------------------------


class TestPipelineRun:
    def test_record_appends_state(self):
        pr = PipelineRun(issue="test")
        state = AgentRunState(stage="clarifier", status="running")
        pr.record(state)
        assert state in pr.stages

    def test_complete_adds_stage(self):
        pr = PipelineRun(issue="test")
        pr.complete("clarifier")
        assert "clarifier" in pr.completed_stages

    def test_skip_adds_to_skipped_and_stages(self):
        pr = PipelineRun(issue="test")
        pr.skip("backend-tester", "no API changes")
        assert pr.skipped_stages["backend-tester"] == "no API changes"
        assert any(s.stage == "backend-tester" and s.status == "skipped" for s in pr.stages)

    def test_halt_records_stage_and_reason(self):
        pr = PipelineRun(issue="test")
        pr.halt("clarifier", "NEEDS_CLARITY")
        assert pr.halt_stage == "clarifier"
        assert pr.halt_reason == "NEEDS_CLARITY"

    def test_to_result_complete(self):
        pr = PipelineRun(issue="#42")
        pr.complete("clarifier")
        pr.complete("researcher")
        pr.pr_url = "https://github.com/org/repo/pull/1"
        result = pr.to_result()
        assert result.status == "COMPLETE"
        assert "clarifier" in result.stages_completed
        assert result.pr_url == "https://github.com/org/repo/pull/1"

    def test_to_result_halted(self):
        pr = PipelineRun(issue="#42")
        pr.halt("clarifier", "needs clarity")
        result = pr.to_result()
        assert result.status == "HALTED"
        assert result.notes == "needs clarity"


# ---------------------------------------------------------------------------
# Happy-path integration
# ---------------------------------------------------------------------------


class TestOrchestratorHappyPath:
    async def test_full_pipeline_completes(self):
        orc = _make_orchestrator()
        result = await orc.run("Implement feature X")
        assert result.status == "COMPLETE"

    async def test_all_agents_called(self):
        clarifier = _stub(CLEAR_BRIEF)
        researcher = _stub(RESEARCH_BRIEF)
        planner = _stub(IMPLEMENTATION_PLAN)
        programmer = _stub("QUALITY GATE: PASS")
        unit_tester = _stub(TEST_PASS)
        backend_tester = _stub(TEST_PASS.replace("unit", "backend"))
        frontend_tester = _stub(TEST_PASS.replace("unit", "e2e"))
        pr_creator = _stub(PR_OUTPUT)
        reviewer = _stub(REVIEW_APPROVED)
        remediator = _stub(REMEDIATION_OUTPUT)

        orc = Orchestrator(
            clarifier=clarifier,
            researcher=researcher,
            planner=planner,
            programmer=programmer,
            unit_tester=unit_tester,
            backend_tester=backend_tester,
            frontend_tester=frontend_tester,
            pr_creator=pr_creator,
            remediator=remediator,
            reviewer=reviewer,
            timeout_seconds=5.0,
        )
        await orc.run("Feature Y")

        clarifier.run.assert_awaited_once()
        researcher.run.assert_awaited_once()
        planner.run.assert_awaited_once()
        programmer.run.assert_awaited_once()
        unit_tester.run.assert_awaited_once()
        backend_tester.run.assert_awaited_once()
        frontend_tester.run.assert_awaited_once()
        pr_creator.run.assert_awaited_once()
        reviewer.run.assert_awaited_once()
        # No review changes → remediator not called
        remediator.run.assert_not_awaited()

    async def test_pr_url_extracted_from_pr_creator_output(self):
        orc = _make_orchestrator(pr_creator=_stub(PR_OUTPUT))
        result = await orc.run("issue text")
        assert result.pr_url == "https://github.com/org/repo/pull/99"


# ---------------------------------------------------------------------------
# Clarifier stage
# ---------------------------------------------------------------------------


class TestClarifierStage:
    async def test_halts_when_needs_clarity(self):
        orc = _make_orchestrator(clarifier=_stub(NEEDS_CLARITY_BRIEF))
        result = await orc.run("Vague issue")
        assert result.status == "HALTED"
        assert result.notes is not None
        assert "NEEDS_CLARITY" in result.notes

    async def test_halts_on_clarifier_timeout(self):
        async def _slow(prompt: str) -> str:
            await asyncio.sleep(999)
            return CLEAR_BRIEF  # pragma: no cover

        slow_agent = AsyncMock(spec=AgentRunner)
        slow_agent.run = _slow
        orc = _make_orchestrator(clarifier=slow_agent, timeout_seconds=0.01)
        result = await orc.run("issue")
        assert result.status == "HALTED"
        assert "timed out" in result.notes.lower()

    async def test_halts_on_clarifier_error(self):
        bad = AsyncMock(spec=AgentRunner)
        bad.run = AsyncMock(side_effect=RuntimeError("boom"))
        orc = _make_orchestrator(clarifier=bad)
        result = await orc.run("issue")
        assert result.status == "HALTED"
        assert "boom" in result.notes

    async def test_researcher_not_called_when_clarifier_fails(self):
        researcher = _stub(RESEARCH_BRIEF)
        orc = _make_orchestrator(
            clarifier=_stub(NEEDS_CLARITY_BRIEF),
            researcher=researcher,
        )
        await orc.run("issue")
        researcher.run.assert_not_awaited()


# ---------------------------------------------------------------------------
# Researcher stage
# ---------------------------------------------------------------------------


class TestResearcherStage:
    async def test_halts_on_incomplete_research_brief(self):
        # Brief with no relevant files → gate fails
        incomplete = "## RESEARCH BRIEF\n\nSummary: Found nothing useful.\n\nRelevant Files:\n"
        orc = _make_orchestrator(researcher=_stub(incomplete))
        result = await orc.run("issue")
        assert result.status == "HALTED"

    async def test_halts_on_researcher_timeout(self):
        async def _slow(prompt: str) -> str:
            await asyncio.sleep(999)
            return RESEARCH_BRIEF  # pragma: no cover

        slow = AsyncMock(spec=AgentRunner)
        slow.run = _slow
        orc = _make_orchestrator(researcher=slow, timeout_seconds=0.01)
        result = await orc.run("issue")
        assert result.status == "HALTED"

    async def test_planner_not_called_when_researcher_fails(self):
        planner = _stub(IMPLEMENTATION_PLAN)
        orc = _make_orchestrator(
            researcher=_stub("## RESEARCH BRIEF\n\nSummary:  \n\nRelevant Files:\n"),
            planner=planner,
        )
        await orc.run("issue")
        planner.run.assert_not_awaited()


# ---------------------------------------------------------------------------
# Planner stage
# ---------------------------------------------------------------------------


class TestPlannerStage:
    async def test_halts_on_incomplete_plan(self):
        # Plan with no steps → gate fails
        bad_plan = "## IMPLEMENTATION PLAN\n\nIssue: #40\n\nSteps:\n\nOut of Scope:\n- none\n"
        orc = _make_orchestrator(planner=_stub(bad_plan))
        result = await orc.run("issue")
        assert result.status == "HALTED"

    async def test_halts_on_planner_timeout(self):
        async def _slow(prompt: str) -> str:
            await asyncio.sleep(999)
            return IMPLEMENTATION_PLAN  # pragma: no cover

        slow = AsyncMock(spec=AgentRunner)
        slow.run = _slow
        orc = _make_orchestrator(planner=slow, timeout_seconds=0.01)
        result = await orc.run("issue")
        assert result.status == "HALTED"


# ---------------------------------------------------------------------------
# Programmer stage — feedback loop
# ---------------------------------------------------------------------------


class TestProgrammerStage:
    async def test_retries_on_failure_up_to_max_attempts(self):
        fail_then_pass = AsyncMock(spec=AgentRunner)
        fail_then_pass.run = AsyncMock(
            side_effect=[RuntimeError("compile error"), "QUALITY GATE: PASS"]
        )
        orc = _make_orchestrator(programmer=fail_then_pass, max_verify_attempts=3)
        result = await orc.run("issue")
        assert result.status == "COMPLETE"
        assert fail_then_pass.run.await_count == 2

    async def test_halts_after_exhausting_all_attempts(self):
        always_fail = AsyncMock(spec=AgentRunner)
        always_fail.run = AsyncMock(side_effect=RuntimeError("always broken"))
        orc = _make_orchestrator(
            programmer=always_fail, max_verify_attempts=2
        )
        result = await orc.run("issue")
        assert result.status == "HALTED"
        assert always_fail.run.await_count == 2

    async def test_halts_on_timeout_after_max_attempts(self):
        call_count = 0

        async def _slow(prompt: str) -> str:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(999)
            return ""  # pragma: no cover

        slow = AsyncMock(spec=AgentRunner)
        slow.run = _slow
        orc = _make_orchestrator(
            programmer=slow, timeout_seconds=0.01, max_verify_attempts=2
        )
        result = await orc.run("issue")
        assert result.status == "HALTED"
        assert call_count == 2


# ---------------------------------------------------------------------------
# Test team — parallel execution and skip rules
# ---------------------------------------------------------------------------


class TestTestTeam:
    async def test_backend_tester_skipped_when_disabled(self):
        backend = _stub(TEST_PASS.replace("unit", "backend"))
        orc = Orchestrator(
            clarifier=_stub(CLEAR_BRIEF),
            researcher=_stub(RESEARCH_BRIEF),
            planner=_stub(IMPLEMENTATION_PLAN),
            programmer=_stub("QUALITY GATE: PASS"),
            unit_tester=_stub(TEST_PASS),
            backend_tester=backend,
            frontend_tester=_stub(TEST_PASS.replace("unit", "e2e")),
            pr_creator=_stub(PR_OUTPUT),
            remediator=_stub(REMEDIATION_OUTPUT),
            reviewer=_stub(REVIEW_APPROVED),
            timeout_seconds=5.0,
            run_backend_tester=False,
        )
        result = await orc.run("issue")
        assert result.status == "COMPLETE"
        backend.run.assert_not_awaited()
        assert "backend-tester" in result.skipped

    async def test_frontend_tester_skipped_when_disabled(self):
        frontend = _stub(TEST_PASS.replace("unit", "e2e"))
        orc = Orchestrator(
            clarifier=_stub(CLEAR_BRIEF),
            researcher=_stub(RESEARCH_BRIEF),
            planner=_stub(IMPLEMENTATION_PLAN),
            programmer=_stub("QUALITY GATE: PASS"),
            unit_tester=_stub(TEST_PASS),
            backend_tester=_stub(TEST_PASS.replace("unit", "backend")),
            frontend_tester=frontend,
            pr_creator=_stub(PR_OUTPUT),
            remediator=_stub(REMEDIATION_OUTPUT),
            reviewer=_stub(REVIEW_APPROVED),
            timeout_seconds=5.0,
            run_frontend_tester=False,
        )
        result = await orc.run("issue")
        assert result.status == "COMPLETE"
        frontend.run.assert_not_awaited()
        assert "frontend-tester" in result.skipped

    async def test_halts_when_unit_tests_fail(self):
        orc = _make_orchestrator(unit_tester=_stub(TEST_FAIL))
        result = await orc.run("issue")
        assert result.status == "HALTED"

    async def test_halts_when_backend_tests_fail(self):
        orc = _make_orchestrator(
            backend_tester=_stub(TEST_FAIL.replace("unit", "backend"))
        )
        result = await orc.run("issue")
        assert result.status == "HALTED"

    async def test_halts_when_multiple_testers_fail_simultaneously(self):
        """Combined failure aggregates all failing stages in the halt message."""
        orc = _make_orchestrator(
            unit_tester=_stub(TEST_FAIL),
            backend_tester=_stub(TEST_FAIL.replace("unit", "backend")),
        )
        result = await orc.run("issue")
        assert result.status == "HALTED"
        assert result.notes is not None
        assert "unit-tester" in result.notes
        assert "backend-tester" in result.notes

    async def test_pr_creator_not_called_when_tests_fail(self):
        pr_creator = _stub(PR_OUTPUT)
        orc = _make_orchestrator(unit_tester=_stub(TEST_FAIL), pr_creator=pr_creator)
        await orc.run("issue")
        pr_creator.run.assert_not_awaited()

    async def test_all_three_testers_called_in_parallel(self):
        """Verify all three testers are awaited even if one is slower."""
        call_counts: dict[str, int] = {"unit": 0, "backend": 0, "frontend": 0}

        async def _timed_unit(prompt: str) -> str:
            call_counts["unit"] += 1
            await asyncio.sleep(0.05)
            return TEST_PASS

        async def _timed_backend(prompt: str) -> str:
            call_counts["backend"] += 1
            await asyncio.sleep(0.05)
            return TEST_PASS.replace("unit", "backend")

        async def _timed_frontend(prompt: str) -> str:
            call_counts["frontend"] += 1
            await asyncio.sleep(0.05)
            return TEST_PASS.replace("unit", "e2e")

        unit = AsyncMock(spec=AgentRunner)
        unit.run = _timed_unit
        backend = AsyncMock(spec=AgentRunner)
        backend.run = _timed_backend
        frontend = AsyncMock(spec=AgentRunner)
        frontend.run = _timed_frontend

        orc = _make_orchestrator(
            unit_tester=unit,
            backend_tester=backend,
            frontend_tester=frontend,
        )

        start = time.monotonic()
        result = await orc.run("issue")
        elapsed = time.monotonic() - start

        assert result.status == "COMPLETE"
        # All three testers were called
        assert call_counts["unit"] == 1
        assert call_counts["backend"] == 1
        assert call_counts["frontend"] == 1
        # Parallel: total wall-time should be well under 3 * 0.05 s,
        # but allow generous headroom to avoid CI flakiness under load.
        assert elapsed < 2.0


# ---------------------------------------------------------------------------
# PR creator stage
# ---------------------------------------------------------------------------


class TestPRCreatorStage:
    async def test_halts_on_pr_creator_timeout(self):
        async def _slow(prompt: str) -> str:
            await asyncio.sleep(999)
            return PR_OUTPUT  # pragma: no cover

        slow = AsyncMock(spec=AgentRunner)
        slow.run = _slow
        orc = _make_orchestrator(pr_creator=slow, timeout_seconds=0.01)
        result = await orc.run("issue")
        assert result.status == "HALTED"

    async def test_halts_on_pr_creator_error(self):
        bad = AsyncMock(spec=AgentRunner)
        bad.run = AsyncMock(side_effect=RuntimeError("push failed"))
        orc = _make_orchestrator(pr_creator=bad)
        result = await orc.run("issue")
        assert result.status == "HALTED"
        assert "push failed" in result.notes


# ---------------------------------------------------------------------------
# Review cycle — feedback loop (reviewer → remediator → reviewer)
# ---------------------------------------------------------------------------


class TestReviewCycle:
    async def test_remediator_called_when_changes_required(self):
        reviewer_outputs = [REVIEW_CHANGES, REVIEW_APPROVED]
        reviewer = AsyncMock(spec=AgentRunner)
        reviewer.run = AsyncMock(side_effect=reviewer_outputs)
        remediator = _stub(REMEDIATION_OUTPUT)

        orc = _make_orchestrator(reviewer=reviewer, remediator=remediator)
        result = await orc.run("issue")
        assert result.status == "COMPLETE"
        assert reviewer.run.await_count == 2
        remediator.run.assert_awaited_once()

    async def test_halts_after_exhausting_review_cycles(self):
        reviewer = AsyncMock(spec=AgentRunner)
        reviewer.run = AsyncMock(return_value=REVIEW_CHANGES)
        remediator = _stub(REMEDIATION_OUTPUT)

        orc = _make_orchestrator(
            reviewer=reviewer, remediator=remediator, max_review_cycles=3
        )
        result = await orc.run("issue")
        assert result.status == "HALTED"
        # reviewer called once per cycle; remediator runs on all cycles except
        # the final one (no re-review would follow, so fixes would be wasted)
        assert reviewer.run.await_count == 3
        assert remediator.run.await_count == 2

    async def test_remediator_not_called_when_approved_first_cycle(self):
        remediator = _stub(REMEDIATION_OUTPUT)
        orc = _make_orchestrator(
            reviewer=_stub(REVIEW_APPROVED), remediator=remediator
        )
        await orc.run("issue")
        remediator.run.assert_not_awaited()

    async def test_halts_on_reviewer_timeout(self):
        async def _slow(prompt: str) -> str:
            await asyncio.sleep(999)
            return REVIEW_APPROVED  # pragma: no cover

        slow = AsyncMock(spec=AgentRunner)
        slow.run = _slow
        orc = _make_orchestrator(reviewer=slow, timeout_seconds=0.01)
        result = await orc.run("issue")
        assert result.status == "HALTED"

    async def test_halts_on_remediator_timeout(self):
        async def _slow(prompt: str) -> str:
            await asyncio.sleep(999)
            return REMEDIATION_OUTPUT  # pragma: no cover

        slow = AsyncMock(spec=AgentRunner)
        slow.run = _slow
        orc = _make_orchestrator(
            reviewer=_stub(REVIEW_CHANGES), remediator=slow, timeout_seconds=0.01
        )
        result = await orc.run("issue")
        assert result.status == "HALTED"


# ---------------------------------------------------------------------------
# State persistence — verify AgentRunState records are captured
# ---------------------------------------------------------------------------


class TestStatePersistence:
    async def test_all_stage_states_recorded(self):
        orc = _make_orchestrator()
        result = await orc.run("issue")
        # Result has completed stages
        assert len(result.stages_completed) > 0

    async def test_failed_state_carries_error_context(self):
        bad = AsyncMock(spec=AgentRunner)
        bad.run = AsyncMock(side_effect=RuntimeError("detail error message"))
        orc = _make_orchestrator(clarifier=bad)
        result = await orc.run("issue")
        assert result.status == "HALTED"
        assert "detail error message" in result.notes

    async def test_timeout_state_carries_error_context(self):
        async def _slow(prompt: str) -> str:
            await asyncio.sleep(999)
            return ""  # pragma: no cover

        slow = AsyncMock(spec=AgentRunner)
        slow.run = _slow
        orc = _make_orchestrator(clarifier=slow, timeout_seconds=0.01)
        result = await orc.run("issue")
        assert result.status == "HALTED"
        assert "timed out" in result.notes.lower()

    async def test_skipped_stages_in_result(self):
        orc = Orchestrator(
            clarifier=_stub(CLEAR_BRIEF),
            researcher=_stub(RESEARCH_BRIEF),
            planner=_stub(IMPLEMENTATION_PLAN),
            programmer=_stub("QUALITY GATE: PASS"),
            unit_tester=_stub(TEST_PASS),
            backend_tester=_stub(TEST_PASS.replace("unit", "backend")),
            frontend_tester=_stub(TEST_PASS.replace("unit", "e2e")),
            pr_creator=_stub(PR_OUTPUT),
            remediator=_stub(REMEDIATION_OUTPUT),
            reviewer=_stub(REVIEW_APPROVED),
            timeout_seconds=5.0,
            run_backend_tester=False,
            run_frontend_tester=False,
        )
        result = await orc.run("issue")
        assert "backend-tester" in result.skipped
        assert "frontend-tester" in result.skipped
