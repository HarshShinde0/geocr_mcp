# syntax=docker/dockerfile:1
FROM python:3.11-slim

# procps provides pgrep for the container healthcheck.
RUN apt-get update && \
    apt-get install -y --no-install-recommends procps && \
    rm -rf /var/lib/apt/lists/*

# uv from the official image - no pip/ensurepip bootstrap needed.
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /usr/local/bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_PREFERENCE=only-system \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Install third-party dependencies only, from the lockfile (mlcroissant comes
# from the GeoCroissant fork, pinned by commit in uv.lock). Source is added
# later so this layer stays cached across code-only changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --python /usr/local/bin/python3.11

# README.md is required by hatchling (pyproject.toml sets readme = "README.md").
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --python /usr/local/bin/python3.11

# Unprivileged runtime user.
RUN groupadd --system app && \
    useradd --system --no-create-home --gid app --home-dir /app --shell /usr/sbin/nologin app

COPY docker-healthcheck.sh /usr/local/bin/docker-healthcheck.sh
RUN chmod 755 /usr/local/bin/docker-healthcheck.sh

USER app

HEALTHCHECK --interval=60s --timeout=10s --start-period=15s --retries=3 \
    CMD ["docker-healthcheck.sh"]

# stdio by default; pass `--transport streamable-http` for hosted deployments.
ENTRYPOINT ["geocr-mcp-server"]
