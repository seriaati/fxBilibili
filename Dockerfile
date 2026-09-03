# syntax=docker/dockerfile:1

# ---- builder: resolve and install dependencies into /app/.venv ----
FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim AS builder

# Compile .pyc at install time (faster startup), copy instead of hardlink
# across the cache mount, skip dev deps, and use the image's Python.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install dependencies in their own layer so it is only rebuilt when the
# lockfile or pyproject changes, not on every source edit.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# ---- runtime: slim image without uv ----
FROM python:3.12-slim-trixie

RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot

# /app must stay writable: the default SQLite cache is written to ./cache.db
COPY --from=builder --chown=nonroot:nonroot /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER nonroot
WORKDIR /app

EXPOSE 9823

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9823"]
