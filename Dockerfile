# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Install git (required for mlcroissant git dependency) and procps (for healthcheck)
RUN apt-get update && \
    apt-get install -y --no-install-recommends git procps && \
    rm -rf /var/lib/apt/lists/*

# Copy uv from official image
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /usr/local/bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_PREFERENCE=only-system \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Install the locked production environment and package once.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# Unprivileged runtime user
RUN groupadd --system app && \
    useradd --system --no-create-home --gid app --home-dir /app --shell /usr/sbin/nologin app

COPY docker-healthcheck.sh /usr/local/bin/docker-healthcheck.sh
RUN chmod 755 /usr/local/bin/docker-healthcheck.sh

USER app

EXPOSE 8000

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD ["docker-healthcheck.sh"]

ENTRYPOINT ["geocr-mcp-server"]
