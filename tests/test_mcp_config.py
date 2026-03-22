"""Tests for .mcp.json configuration and .claude/settings.json MCP tool namespaces."""

import json

from tests.conftest import REPO_ROOT


def load_mcp_config() -> dict:
    with open(REPO_ROOT / ".mcp.json") as f:
        return json.load(f)


def load_settings() -> dict:
    with open(REPO_ROOT / ".claude" / "settings.json") as f:
        return json.load(f)


def test_mcp_config_exists():
    assert (REPO_ROOT / ".mcp.json").exists()


def test_mcp_config_is_valid_json():
    config = load_mcp_config()
    assert isinstance(config, dict)


def test_mcp_config_has_mcp_servers_key():
    config = load_mcp_config()
    assert "mcpServers" in config
    assert isinstance(config["mcpServers"], dict)


def test_linear_server_configured():
    config = load_mcp_config()
    servers = config["mcpServers"]
    assert "linear" in servers
    linear = servers["linear"]
    assert linear["type"] == "http"
    assert linear["url"] == "https://mcp.linear.app/mcp"
    headers = linear.get("headers", {})
    assert "Authorization" in headers
    assert "LINEAR_API_KEY" in headers["Authorization"]


def test_github_server_configured():
    config = load_mcp_config()
    servers = config["mcpServers"]
    assert "github" in servers
    github = servers["github"]
    assert github["type"] == "stdio"
    assert github["command"] == "docker"
    assert any(arg.startswith("ghcr.io/github/github-mcp-server") for arg in github["args"])
    env = github.get("env", {})
    assert "GITHUB_TOKEN" in env
    assert env["GITHUB_TOKEN"] == "${GITHUB_TOKEN}"


def test_settings_json_linear_tools_correct_namespace():
    settings = load_settings()
    mcp_tools = [t for t in settings.get("allowedTools", []) if t.startswith("mcp__")]
    assert not any(t.startswith("mcp__claude_ai_Linear__") for t in mcp_tools)
    assert any(t.startswith("mcp__linear__") for t in mcp_tools)


# Minimum required GitHub MCP tools that must be present in .claude/settings.json.
# Use issubset so adding new tools in the future does not break this test.
_REQUIRED_GITHUB_MCP_TOOLS = {
    "mcp__github__create_pull_request",
    "mcp__github__get_file_contents",
    "mcp__github__get_pull_request",
    "mcp__github__list_pull_requests",
    "mcp__github__create_issue",
    "mcp__github__list_issues",
    "mcp__github__get_issue",
}


def test_settings_json_github_tools_present():
    settings = load_settings()
    github_tools = {t for t in settings.get("allowedTools", []) if t.startswith("mcp__github__")}
    assert _REQUIRED_GITHUB_MCP_TOOLS.issubset(github_tools), (
        f"Missing required GitHub MCP tools: {_REQUIRED_GITHUB_MCP_TOOLS - github_tools}"
    )
