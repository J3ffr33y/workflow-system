# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
ARG GIT_SHA=unknown
ENV FLOW_GIT_SHA=$GIT_SHA PATH="/app/.venv/bin:$PATH"

RUN useradd --system --uid 1001 app && chown -R app /app
USER app
EXPOSE 8000
# API by default; the worker uses the same image with `python -m app.worker`.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
