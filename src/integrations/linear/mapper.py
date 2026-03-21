from dataclasses import dataclass


@dataclass
class PipelineResult:
    stage: str
    status: str
    pr_url: str = ""
    summary: str = ""
    errors: list[str] | None = None


def linear_issue_to_github_issue(linear_issue: dict) -> dict:
    """Extract GitHub issue fields from a Linear issue payload."""
    title = linear_issue.get("title", "")
    description = linear_issue.get("description") or ""

    # Extract acceptance criteria if embedded in description under a known header
    acceptance_criteria = ""
    for line in description.splitlines():
        if line.strip().lower().startswith("## acceptance criteria"):
            idx = description.lower().find("## acceptance criteria")
            acceptance_criteria = description[idx:]
            break

    labels = [
        node["name"]
        for node in (linear_issue.get("labels") or {}).get("nodes", [])
    ]

    body_parts = [description]
    if acceptance_criteria:
        # already included in description; no duplicate needed
        pass
    identifier = linear_issue.get("identifier", "")
    if identifier:
        body_parts.append(f"\n---\n_Linear issue: {identifier}_")

    return {
        "title": title,
        "body": "\n".join(body_parts).strip(),
        "labels": labels,
        "acceptance_criteria": acceptance_criteria,
    }


def pipeline_result_to_linear_comment(result: PipelineResult) -> str:
    """Format a PipelineResult as a Linear comment."""
    status_emoji = {
        "success": "✅",
        "failure": "❌",
        "in_progress": "🔄",
        "skipped": "⏭️",
    }.get(result.status.lower(), "ℹ️")

    lines = [
        f"{status_emoji} **Pipeline {result.stage}** — `{result.status}`",
    ]
    if result.pr_url:
        lines.append(f"\n**Pull Request:** {result.pr_url}")
    if result.summary:
        lines.append(f"\n{result.summary}")
    if result.errors:
        lines.append("\n**Errors:**")
        for err in result.errors:
            lines.append(f"- {err}")

    return "\n".join(lines)


# Maps (pipeline_stage, status) -> Linear workflow state name
_PIPELINE_STATE_MAP: dict[tuple[str, str], str] = {
    ("plan", "success"): "In Progress",
    ("implement", "success"): "In Review",
    ("implement", "failure"): "In Progress",
    ("review", "success"): "Done",
    ("review", "failure"): "In Progress",
    ("test", "failure"): "In Progress",
    ("test", "success"): "In Review",
}


def map_pipeline_state_to_linear(stage: str, status: str) -> str:
    """Map a pipeline stage + status to a Linear workflow state name."""
    return _PIPELINE_STATE_MAP.get((stage.lower(), status.lower()), "In Progress")
