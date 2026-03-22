# Sandbox image for agentic pipeline agent execution.
#
# Provides full shell access within a boundary:
#   - bash and zsh shells
#   - git with GH CLI for authenticated operations
#   - npm (Node.js), pip (Python 3), cargo (Rust)
#   - Docker CLI (Docker-in-Docker via compose; daemon not started here)
#   - Network access to public package registries and documentation sites
#   - No embedded production secrets, database credentials, or internal endpoints
#
# Build:
#   docker build -t agentic-sandbox sandbox/
#
# Run with DinD:
#   docker compose -f sandbox/docker-compose.yml up

FROM ubuntu:24.04

SHELL ["/bin/bash", "-euo", "pipefail", "-c"]

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# ── Core utilities ────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    zsh \
    curl \
    wget \
    ca-certificates \
    gnupg \
    lsb-release \
    git \
    unzip \
    jq \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# ── GitHub CLI (git auth) ─────────────────────────────────────────────────────
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] \
        https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# ── Node.js 20 LTS + npm ──────────────────────────────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# ── Python 3 + pip ───────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/local/bin/python

# ── Rust + cargo ─────────────────────────────────────────────────────────────
ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:$PATH
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --no-modify-path --default-toolchain stable \
    && chmod -R a+w /usr/local/rustup /usr/local/cargo

# ── Docker CLI (daemon provided via DinD sidecar in docker-compose.yml) ──────
RUN curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] \
        https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# ── Non-root user ─────────────────────────────────────────────────────────────
RUN useradd -m -s /bin/bash agent \
    && usermod -aG docker agent 2>/dev/null || true

# ── Git safe-directory config (avoids dubious ownership errors) ──────────────
RUN git config --system safe.directory '*'

# ── Default workspace ─────────────────────────────────────────────────────────
WORKDIR /workspace
RUN chown agent:agent /workspace

USER agent

CMD ["/bin/bash"]
