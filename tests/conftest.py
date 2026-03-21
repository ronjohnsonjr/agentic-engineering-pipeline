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
    "local-ci-remediate",
    "local-issue-to-pr",
    "local-pr-describe",
    "local-pr-review",
    "local-quality-sweep",
]


def load_workflow(name: str) -> dict:
    """Load and parse a workflow YAML file by name (without .yml extension)."""
    path = WORKFLOWS_DIR / f"{name}.yml"
    with open(path) as f:
        return yaml.safe_load(f)
