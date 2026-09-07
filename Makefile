.PHONY: install up down check lint typecheck test migrate

install:
	uv sync

up:
	docker compose up -d --build

down:
	docker compose down

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy

test:
	uv run pytest -v

check: lint typecheck test

migrate:
	docker compose exec api uv run alembic upgrade head
