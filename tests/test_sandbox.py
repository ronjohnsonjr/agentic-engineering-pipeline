"""Validation tests for the sandbox/ agent execution environment.

These tests inspect the static configuration files (Dockerfile and
docker-compose.yml) rather than building or running containers, so they
run cheaply in CI without Docker.
"""

import functools
import re
import yaml
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
SANDBOX_DIR = REPO_ROOT / "sandbox"
DOCKERFILE = SANDBOX_DIR / "Dockerfile"
COMPOSE_FILE = SANDBOX_DIR / "docker-compose.yml"


# ── Existence ─────────────────────────────────────────────────────────────────


def test_dockerfile_exists():
    assert DOCKERFILE.exists(), "sandbox/Dockerfile must exist"


def test_compose_file_exists():
    assert COMPOSE_FILE.exists(), "sandbox/docker-compose.yml must exist"


# ── Dockerfile: shell access ──────────────────────────────────────────────────


@functools.lru_cache(maxsize=None)
def _dockerfile_text() -> str:
    return DOCKERFILE.read_text()


def test_dockerfile_installs_bash():
    assert "bash" in _dockerfile_text(), (
        "Dockerfile must install bash to satisfy AC: bash/zsh shell access"
    )


def test_dockerfile_installs_zsh():
    assert "zsh" in _dockerfile_text(), (
        "Dockerfile must install zsh to satisfy AC: bash/zsh shell access"
    )


# ── Dockerfile: git + GH CLI ──────────────────────────────────────────────────


def test_dockerfile_installs_git():
    assert re.search(r"\bgit\b", _dockerfile_text()), (
        "Dockerfile must install git for authenticated git operations"
    )


def test_dockerfile_installs_gh_cli():
    # GH CLI enables 'gh auth' which drives authenticated git operations.
    text = _dockerfile_text()
    assert "gh" in text and "cli.github.com" in text, (
        "Dockerfile must install the GitHub CLI (gh) for git auth"
    )


# ── Dockerfile: package managers ─────────────────────────────────────────────


def test_dockerfile_installs_npm():
    text = _dockerfile_text()
    assert "nodejs" in text or "npm" in text, (
        "Dockerfile must install Node.js/npm (AC: package managers)"
    )


def test_dockerfile_installs_pip():
    text = _dockerfile_text()
    assert "python3-pip" in text or "pip" in text, (
        "Dockerfile must install pip (AC: package managers)"
    )


def test_dockerfile_installs_cargo():
    text = _dockerfile_text()
    assert "cargo" in text or "rustup" in text or "rustup.rs" in text, (
        "Dockerfile must install cargo via rustup (AC: package managers)"
    )


# ── Dockerfile: Docker CLI for DinD ──────────────────────────────────────────


def test_dockerfile_installs_docker_cli():
    text = _dockerfile_text()
    assert "docker-ce-cli" in text or "docker.com" in text, (
        "Dockerfile must install the Docker CLI (AC: Docker-in-Docker)"
    )


# ── Dockerfile: non-root user ─────────────────────────────────────────────────


def test_dockerfile_creates_non_root_user():
    assert "useradd" in _dockerfile_text(), (
        "Dockerfile must create a non-root user to limit blast radius"
    )


def test_dockerfile_switches_to_non_root_user():
    # The final USER directive must not be root.
    user_directives = re.findall(r"^USER\s+(.+)$", _dockerfile_text(), re.MULTILINE)
    assert user_directives, "Dockerfile must have at least one USER directive"
    final_user = user_directives[-1].strip()
    assert final_user != "root", (
        f"Dockerfile final USER must not be 'root', got: {final_user!r}"
    )


# ── Dockerfile: no hard-coded secrets ────────────────────────────────────────


_SECRET_PATTERNS = [
    r"(?i)password\s*=\s*\S+",
    r"(?i)secret\s*=\s*\S+",
    r"(?i)api_key\s*=\s*\S+",
    r"(?i)token\s*=\s*['\"]?[A-Za-z0-9+/]{20,}",
]


def test_dockerfile_contains_no_hard_coded_secrets():
    text = _dockerfile_text()
    for pattern in _SECRET_PATTERNS:
        match = re.search(pattern, text)
        assert not match, (
            f"Dockerfile must not contain hard-coded secrets. "
            f"Found pattern match: {match.group()!r}"
        )


# ── docker-compose.yml: DinD service ─────────────────────────────────────────


@functools.lru_cache(maxsize=None)
def _compose() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text())


def test_compose_is_valid_yaml():
    compose = _compose()
    assert isinstance(compose, dict), "docker-compose.yml must parse as a YAML mapping"


def test_compose_has_dind_service():
    services = _compose().get("services", {})
    assert "dind" in services, (
        "docker-compose.yml must define a 'dind' service for Docker-in-Docker"
    )


def test_compose_dind_is_privileged():
    dind = _compose()["services"]["dind"]
    assert dind.get("privileged") is True, (
        "'dind' service must run privileged (required for Docker daemon)"
    )


def test_compose_dind_uses_official_image():
    dind_image = _compose()["services"]["dind"].get("image", "")
    assert dind_image.startswith("docker:"), (
        f"'dind' service should use an official docker image, got: {dind_image!r}"
    )


# ── docker-compose.yml: agent service ────────────────────────────────────────


def test_compose_has_agent_service():
    services = _compose().get("services", {})
    assert "agent" in services, (
        "docker-compose.yml must define an 'agent' service"
    )


def test_compose_agent_points_docker_host_at_dind():
    agent = _compose()["services"]["agent"]
    env = agent.get("environment", {})
    docker_host = env.get("DOCKER_HOST", "")
    assert "dind" in docker_host, (
        "agent DOCKER_HOST must point at the dind service (AC: Docker-in-Docker)"
    )


def test_compose_agent_injects_gh_token_from_environment():
    agent = _compose()["services"]["agent"]
    env = agent.get("environment", {})
    # Value must reference an env-var, not be hard-coded.
    gh_token_value = str(env.get("GH_TOKEN", "") or env.get("GITHUB_TOKEN", ""))
    assert "${" in gh_token_value or gh_token_value == "", (
        "GH_TOKEN/GITHUB_TOKEN must be injected from the host environment, not hard-coded"
    )


# ── docker-compose.yml: network isolation ────────────────────────────────────


def test_compose_defines_isolated_network():
    networks = _compose().get("networks", {})
    assert networks, (
        "docker-compose.yml must define at least one named network for isolation"
    )


def test_compose_network_uses_bridge_driver():
    networks = _compose().get("networks", {})
    for name, cfg in networks.items():
        if isinstance(cfg, dict):
            assert cfg.get("driver") == "bridge", (
                f"Network '{name}' must explicitly declare driver: bridge, got: {cfg.get('driver')!r}"
            )


def test_compose_agent_is_not_privileged():
    agent = _compose()["services"]["agent"]
    assert agent.get("privileged") is not True, (
        "agent service must not run privileged — only the dind sidecar needs that"
    )
