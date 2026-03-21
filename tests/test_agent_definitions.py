"""Validation tests for .claude/agents/*.md agent definition files."""

import re
import pytest
from pathlib import Path
from tests.conftest import AGENTS_DIR

REQUIRED_FRONTMATTER_FIELDS = ["name", "description", "model", "tools"]

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def parse_frontmatter(path: Path) -> dict:
    """Extract YAML frontmatter from a markdown file."""
    import yaml

    text = path.read_text()
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    return yaml.safe_load(match.group(1)) or {}


def all_agent_paths() -> list[Path]:
    return sorted(AGENTS_DIR.glob("*.md"))


@pytest.mark.parametrize("agent_path", all_agent_paths(), ids=lambda p: p.stem)
def test_frontmatter_is_present(agent_path):
    text = agent_path.read_text()
    assert FRONTMATTER_RE.match(text), (
        f"{agent_path.name}: file must start with YAML frontmatter (--- ... ---)"
    )


@pytest.mark.parametrize("agent_path", all_agent_paths(), ids=lambda p: p.stem)
def test_frontmatter_has_required_fields(agent_path):
    fm = parse_frontmatter(agent_path)
    assert fm, f"{agent_path.name}: frontmatter is empty or unparseable"
    for field in REQUIRED_FRONTMATTER_FIELDS:
        assert field in fm, (
            f"{agent_path.name}: frontmatter is missing required field '{field}'"
        )


@pytest.mark.parametrize("agent_path", all_agent_paths(), ids=lambda p: p.stem)
def test_name_matches_filename(agent_path):
    fm = parse_frontmatter(agent_path)
    expected_name = agent_path.stem
    assert fm.get("name") == expected_name, (
        f"{agent_path.name}: 'name' field ({fm.get('name')!r}) "
        f"must match filename stem ({expected_name!r})"
    )


@pytest.mark.parametrize("agent_path", all_agent_paths(), ids=lambda p: p.stem)
def test_description_is_non_empty_string(agent_path):
    fm = parse_frontmatter(agent_path)
    desc = fm.get("description", "")
    assert isinstance(desc, str) and desc.strip(), (
        f"{agent_path.name}: 'description' must be a non-empty string"
    )


@pytest.mark.parametrize("agent_path", all_agent_paths(), ids=lambda p: p.stem)
def test_model_is_non_empty_string(agent_path):
    fm = parse_frontmatter(agent_path)
    model = fm.get("model", "")
    assert isinstance(model, str) and model.strip(), (
        f"{agent_path.name}: 'model' must be a non-empty string"
    )


@pytest.mark.parametrize("agent_path", all_agent_paths(), ids=lambda p: p.stem)
def test_tools_is_non_empty_list(agent_path):
    fm = parse_frontmatter(agent_path)
    tools = fm.get("tools")
    assert isinstance(tools, list) and len(tools) > 0, (
        f"{agent_path.name}: 'tools' must be a non-empty list"
    )
