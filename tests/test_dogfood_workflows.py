"""Validation tests for all dogfood caller workflows (.github/workflows/dogfood-*.yml)."""

import yaml
import pytest
from tests.conftest import WORKFLOWS_DIR, DOGFOOD_WORKFLOW_NAMES


def load_dogfood(name: str) -> dict:
    path = WORKFLOWS_DIR / f"{name}.yml"
    with open(path) as f:
        return yaml.safe_load(f)


def _find_reusable_uses(workflow: dict) -> list[str]:
    """Collect all 'uses' values from jobs that delegate to a reusable workflow."""
    uses_values = []
    for job in workflow.get("jobs", {}).values():
        uses = job.get("uses")
        if uses:
            uses_values.append(uses)
    return uses_values


def _find_secrets_inherit(workflow: dict) -> bool:
    """Return True if any job declares ``secrets: inherit``."""
    for job in workflow.get("jobs", {}).values():
        if job.get("secrets") == "inherit":
            return True
    return False


@pytest.mark.parametrize("name", DOGFOOD_WORKFLOW_NAMES)
def test_references_local_reusable_workflow(name):
    """Each dogfood workflow must delegate to a workflow in this same repo."""
    workflow = load_dogfood(name)
    uses_values = _find_reusable_uses(workflow)
    assert uses_values, f"{name}: no 'uses' key found in any job"
    for uses in uses_values:
        assert uses.startswith("./.github/workflows/"), (
            f"{name}: job 'uses' must reference a local workflow "
            f"(./.github/workflows/*), got: {uses!r}"
        )


@pytest.mark.parametrize("name", DOGFOOD_WORKFLOW_NAMES)
def test_has_concurrency_group(name):
    """Each dogfood workflow must declare a concurrency group to prevent pile-ups."""
    workflow = load_dogfood(name)
    assert "concurrency" in workflow, (
        f"{name}: missing top-level 'concurrency' group"
    )


@pytest.mark.parametrize("name", DOGFOOD_WORKFLOW_NAMES)
def test_uses_secrets_inherit(name):
    """Each dogfood workflow must pass secrets to the reusable workflow via inherit."""
    workflow = load_dogfood(name)
    assert _find_secrets_inherit(workflow), (
        f"{name}: no job found with 'secrets: inherit'"
    )
