# syntax=docker/dockerfile:1

# --- Build stage: resolve dependencies and install the app into a virtualenv ---
FROM ghcr.io/astral-sh/uv:0.13.1-python3.13-trixie-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Dependencies first (cached layer as long as the lock file does not change).
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# Then the application itself.
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

# --- Runtime stage: only Python and the virtualenv, no uv, no build tools ---
FROM python:3.13-slim-trixie

# Links the ghcr.io package to its GitHub repository.
LABEL org.opencontainers.image.source="https://github.com/SamuelPoirier-Dev/lifelog-mcp"

RUN useradd --system --uid 10001 --no-create-home app

COPY --from=builder --chown=app:app /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER app
EXPOSE 8000

# No access log: URLs carry OAuth codes (/auth/callback?code=...) (D71).
CMD ["uvicorn", "lifelog.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--no-access-log"]
