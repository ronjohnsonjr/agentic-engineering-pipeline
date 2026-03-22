import pytest

from src.integrations.linear.mapper import (
    PipelineResult,
    linear_issue_to_github_issue,
    map_pipeline_state_to_linear,
    pipeline_result_to_linear_comment,
)


def _make_linear_issue(**overrides) -> dict:
    base = {
        "id": "issue-1",
        "identifier": "ENG-10",
        "title": "Add feature X",
        "description": "We need feature X.\n\n## Acceptance Criteria\n- AC1\n- AC2",
        "labels": {"nodes": [{"id": "l1", "name": "backend"}]},
        "state": {"id": "s1", "name": "Todo"},
    }
    base.update(overrides)
    return base


class TestLinearIssueToGithubIssue:
    def test_extracts_title(self):
        result = linear_issue_to_github_issue(_make_linear_issue())
        assert result["title"] == "Add feature X"

    def test_body_includes_description(self):
        result = linear_issue_to_github_issue(_make_linear_issue())
        assert "We need feature X" in result["body"]

    def test_body_includes_linear_identifier(self):
        result = linear_issue_to_github_issue(_make_linear_issue())
        assert "ENG-10" in result["body"]

    def test_labels_extracted(self):
        result = linear_issue_to_github_issue(_make_linear_issue())
        assert "backend" in result["labels"]

    def test_acceptance_criteria_extracted(self):
        result = linear_issue_to_github_issue(_make_linear_issue())
        assert "AC1" in result["acceptance_criteria"]

    def test_no_description_handled(self):
        result = linear_issue_to_github_issue(
            _make_linear_issue(description=None, identifier="")
        )
        assert result["body"] == ""

    def test_no_labels_returns_empty_list(self):
        result = linear_issue_to_github_issue(
            _make_linear_issue(labels={"nodes": []})
        )
        assert result["labels"] == []


class TestPipelineResultToLinearComment:
    def test_success_includes_checkmark(self):
        result = PipelineResult(stage="implement", status="success", pr_url="https://github.com/org/repo/pull/42")
        comment = pipeline_result_to_linear_comment(result)
        assert "✅" in comment
        assert "implement" in comment
        assert "https://github.com/org/repo/pull/42" in comment

    def test_failure_includes_x(self):
        result = PipelineResult(stage="test", status="failure", errors=["assertion failed"])
        comment = pipeline_result_to_linear_comment(result)
        assert "❌" in comment
        assert "assertion failed" in comment

    def test_summary_included(self):
        result = PipelineResult(stage="review", status="success", summary="LGTM")
        comment = pipeline_result_to_linear_comment(result)
        assert "LGTM" in comment

    def test_in_progress_status(self):
        result = PipelineResult(stage="plan", status="in_progress")
        comment = pipeline_result_to_linear_comment(result)
        assert "🔄" in comment

    def test_unknown_status_uses_info(self):
        result = PipelineResult(stage="deploy", status="queued")
        comment = pipeline_result_to_linear_comment(result)
        assert "ℹ️" in comment


class TestMapPipelineStateToLinear:
    def test_implement_success_maps_to_in_review(self):
        assert map_pipeline_state_to_linear("implement", "success") == "In Review"

    def test_review_success_maps_to_done(self):
        assert map_pipeline_state_to_linear("review", "success") == "Done"

    def test_implement_failure_maps_to_in_progress(self):
        assert map_pipeline_state_to_linear("implement", "failure") == "In Progress"

    def test_unknown_stage_defaults_to_in_progress(self):
        assert map_pipeline_state_to_linear("unknown", "success") == "In Progress"

    def test_case_insensitive(self):
        assert map_pipeline_state_to_linear("REVIEW", "SUCCESS") == "Done"

    def test_clarify_success_maps_to_triage(self):
        assert map_pipeline_state_to_linear("clarify", "success") == "Triage"

    def test_clarify_failure_maps_to_blocked(self):
        assert map_pipeline_state_to_linear("clarify", "failure") == "Blocked"

    def test_research_success_maps_to_triage(self):
        assert map_pipeline_state_to_linear("research", "success") == "Triage"

    def test_plan_failure_maps_to_blocked(self):
        assert map_pipeline_state_to_linear("plan", "failure") == "Blocked"

    def test_pr_created_success_maps_to_in_review(self):
        assert map_pipeline_state_to_linear("pr-created", "success") == "In Review"

    def test_remediation_success_maps_to_in_progress(self):
        assert map_pipeline_state_to_linear("remediation", "success") == "In Progress"

    def test_remediation_failure_maps_to_blocked(self):
        assert map_pipeline_state_to_linear("remediation", "failure") == "Blocked"
