"""Validation tests for scaffold/bootstrap.sh."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
BOOTSTRAP_SCRIPT = REPO_ROOT / "scaffold" / "bootstrap.sh"


def run_bootstrap(tmpdir: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run bootstrap.sh in a temporary directory and return the result."""
    merged_env = {**os.environ, **(env or {})}
    # Remove LINEAR_API_KEY from env unless explicitly provided
    if env is None or "LINEAR_API_KEY" not in env:
        merged_env.pop("LINEAR_API_KEY", None)
    return subprocess.run(
        ["bash", str(BOOTSTRAP_SCRIPT)],
        cwd=tmpdir,
        capture_output=True,
        text=True,
        env=merged_env,
    )


def test_bootstrap_script_exists():
    assert BOOTSTRAP_SCRIPT.exists(), "scaffold/bootstrap.sh must exist"
    assert BOOTSTRAP_SCRIPT.stat().st_mode & 0o111, "bootstrap.sh should be executable"


def test_bootstrap_creates_agent_directory(tmp_path):
    result = run_bootstrap(tmp_path)
    assert result.returncode == 0, f"bootstrap.sh failed:\n{result.stderr}"
    assert (tmp_path / ".claude" / "agents").is_dir()


def test_bootstrap_creates_core_agent_stubs(tmp_path):
    run_bootstrap(tmp_path)
    agents_dir = tmp_path / ".claude" / "agents"
    for stub in ("coder.md", "verifier.md", "reviewer.md"):
        assert (agents_dir / stub).exists(), f".claude/agents/{stub} should be created"


def test_bootstrap_skips_linear_agent_without_api_key(tmp_path):
    run_bootstrap(tmp_path)
    linear_stub = tmp_path / ".claude" / "agents" / "linear.md"
    assert not linear_stub.exists(), (
        ".claude/agents/linear.md must NOT be created when LINEAR_API_KEY is not set"
    )


def test_bootstrap_creates_linear_agent_with_api_key(tmp_path):
    run_bootstrap(tmp_path, env={"LINEAR_API_KEY": "lin_test_key"})
    linear_stub = tmp_path / ".claude" / "agents" / "linear.md"
    assert linear_stub.exists(), (
        ".claude/agents/linear.md must be created when LINEAR_API_KEY is set"
    )


def test_bootstrap_linear_agent_has_valid_frontmatter(tmp_path):
    import re
    import yaml

    run_bootstrap(tmp_path, env={"LINEAR_API_KEY": "lin_test_key"})
    linear_stub = tmp_path / ".claude" / "agents" / "linear.md"
    text = linear_stub.read_text()
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    assert match, "linear.md must start with YAML frontmatter"
    fm = yaml.safe_load(match.group(1))
    assert fm.get("name") == "linear"
    assert fm.get("model")
    assert isinstance(fm.get("tools"), list) and fm["tools"]


def test_bootstrap_skips_agents_if_directory_nonempty(tmp_path):
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "custom.md").write_text("# custom agent\n")
    run_bootstrap(tmp_path)
    # Core stubs should NOT be created when agents/ already has files
    assert not (agents_dir / "coder.md").exists(), (
        "bootstrap.sh must not overwrite existing agent definitions"
    )


def test_bootstrap_skip_message_without_linear_key(tmp_path):
    result = run_bootstrap(tmp_path)
    assert "LINEAR_API_KEY not set" in result.stdout, (
        "bootstrap.sh should print a skip message when LINEAR_API_KEY is absent"
    )
