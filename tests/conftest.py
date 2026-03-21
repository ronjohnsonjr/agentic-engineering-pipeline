"""Shared fixtures and helpers for workflow and agent validation tests."""

import yaml
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
AGENTS_DIR = REPO_ROOT / ".claude" / "agents"

REUSABLE_WORKFLOW_NAMES = [
    "ci-remediate",
    "dependabot-review",
    "issue-to-pr",
    "pr-describe",
    "pr-review",
    "quality-sweep",
    "stale-pr-nudge",
]

DOGFOOD_WORKFLOW_NAMES = [
    "dogfood-ci-remediate",
    "dogfood-issue-to-pr",
    "dogfood-pr-describe",
    "dogfood-pr-review",
    "dogfood-quality-sweep",
]


def load_workflow(name: str) -> dict:
    """Load and parse a workflow YAML file by name (without .yml extension)."""
    path = WORKFLOWS_DIR / f"{name}.yml"
    with open(path) as f:
        return yaml.safe_load(f)


def get_on(workflow: dict) -> dict:
    """Return the 'on' block of a workflow.

    PyYAML parses the bare YAML key ``on`` as the boolean ``True``.
    Fall back to the string key for any tooling that pre-processes the YAML.
    """
    return workflow.get(True, workflow.get("on", {}))


def find_prompt(workflow: dict) -> str:
    """Return the first ``prompt`` value found in any step's ``with`` block."""
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []) or []:
            if isinstance(step, dict) and isinstance(step.get("with"), dict):
                prompt = step["with"].get("prompt", "")
                if prompt:
                    return str(prompt)
    return ""


@pytest.fixture
def reusable_workflow_paths() -> list[Path]:
    return [WORKFLOWS_DIR / f"{name}.yml" for name in REUSABLE_WORKFLOW_NAMES]


@pytest.fixture
def dogfood_workflow_paths() -> list[Path]:
    return [WORKFLOWS_DIR / f"{name}.yml" for name in DOGFOOD_WORKFLOW_NAMES]


@pytest.fixture
def agent_definition_paths() -> list[Path]:
    return sorted(AGENTS_DIR.glob("*.md"))
