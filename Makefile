# Everyday commands. Run `make help`.
.PHONY: help install db dev-api dev-worker dev-web test lint fmt typecheck check migration openapi

BACK=cd backend &&
FRONT=cd frontend &&

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

install: ## install backend and frontend dependencies
	$(BACK) uv sync --all-groups
	$(FRONT) pnpm install

db: ## create tables / apply migrations and seed the reference setup
	$(BACK) uv run alembic upgrade head && uv run python -m app.cli bootstrap

dev-api: ## run the API with reload on :8000
	$(BACK) uv run uvicorn app.main:app --reload --port 8000

dev-worker: ## run the background worker
	$(BACK) uv run python -m app.worker

dev-web: ## run the frontend on :5173 (proxies /api to :8000)
	$(FRONT) pnpm dev

test: ## run all tests
	$(BACK) uv run pytest
	$(FRONT) pnpm test

lint: ## lint and format checks
	$(BACK) uv run ruff check . && uv run ruff format --check . && uv run lint-imports
	$(FRONT) pnpm lint && pnpm format:check

typecheck: ## static types
	$(BACK) uv run mypy app
	$(FRONT) pnpm typecheck

fmt: ## auto-format everything
	$(BACK) uv run ruff format . && uv run ruff check --fix .
	$(FRONT) pnpm format

check: lint typecheck test ## everything CI runs

migration: ## new Alembic migration: make migration m="add x"
	$(BACK) uv run alembic revision --autogenerate -m "$(m)"

openapi: ## regenerate frontend API types from the running API
	$(FRONT) pnpm gen:api
