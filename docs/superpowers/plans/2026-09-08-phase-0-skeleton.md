# Phase 0 — Walking Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an empty system that starts, reaches every dependency, builds as an image, and
passes CI — before a single feature exists.

**Architecture:** A FastAPI application with a `GET /health` endpoint that genuinely probes
PostgreSQL and Redis, backed by Docker Compose. Health-check logic lives in a pure module
taking injected dependencies, so the failure path is unit-testable without stopping containers.

**Tech Stack:** Python 3.12, uv, FastAPI, Pydantic v2, pydantic-settings, SQLAlchemy 2.0
(async, psycopg3), Alembic, redis-py, PostgreSQL 16 + pgvector, pytest, pytest-asyncio, httpx,
ruff, mypy, Docker Compose, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-07-frontdesk-voice-receptionist-design.md`
**Roadmap:** `docs/superpowers/plans/2026-09-08-frontdesk-phase-roadmap.md` (Phase 0 section)

## Global Constraints

- **Python 3.12**, pinned in `.python-version` and the Dockerfile so laptop, CI and VPS resolve
  identically. A conservative preference, not a requirement — see the roadmap's constraints.
- **`make check` runs ruff, mypy (strict on `app/`) and pytest.** CI runs the same plus a
  Docker build.
- **No ML dependencies in this phase.** Phase 1 adds `sentence-transformers` and friends;
  keeping them out now keeps the image small and the CI fast.
- **Commit at each task.** No `Co-Authored-By` lines.

## Exit criteria for the phase

- [ ] `docker compose up -d`, then `curl -s localhost:8000/health` returns 200 with
      `postgres: true` and `redis: true`
- [ ] `SELECT extname FROM pg_extension WHERE extname='vector'` returns one row
- [ ] `make check` is green
- [ ] CI is green on a pushed branch
- [ ] **Stopping Postgres makes `/health` report `degraded` with `postgres: false`** — proven by
      an automated test, not by hand

**The trap this phase exists to avoid:** a health check that returns 200 without touching
anything. It is indistinguishable from a working one until the day it matters. Task 7 is the
whole point of the phase.

## File structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Dependencies, ruff and mypy config, pytest config |
| `.python-version` | Pins 3.12 for uv |
| `Makefile` | `up`, `down`, `check`, `test`, `lint`, `typecheck`, `migrate` |
| `app/config.py` | `Settings` — every env var declared in one place |
| `app/main.py` | FastAPI app and the `/health` route |
| `app/health.py` | Dependency probes and the report model. Pure; takes injected deps. |
| `app/db.py` | Async engine, session factory, `get_session` |
| `app/redis.py` | Connection pool, `get_redis` |
| `alembic.ini`, `migrations/env.py` | Migration harness |
| `migrations/versions/0001_enable_pgvector.py` | `CREATE EXTENSION vector` |
| `docker-compose.yml` | postgres, redis, api |
| `Dockerfile` | Python 3.12 image |
| `.github/workflows/ci.yml` | lint, types, tests, docker build |
| `tests/` | One test module per app module |

---

## Task 1: Project scaffold and tooling

**Files:**
- Create: `pyproject.toml`, `.python-version`, `Makefile`, `app/__init__.py`, `tests/__init__.py`
- Test: `tests/test_scaffold.py`

**Interfaces:**
- Consumes: nothing
- Produces: `make check` (ruff + mypy + pytest), the `app` package, `app.__version__: str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scaffold.py
import app


def test_package_exposes_version() -> None:
    assert isinstance(app.__version__, str)
    assert app.__version__.count(".") == 2
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_scaffold.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Create the scaffold**

```toml
# pyproject.toml
[project]
name = "frontdesk"
version = "0.1.0"
requires-python = "==3.12.*"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "sqlalchemy[asyncio]>=2.0.36",
    "psycopg[binary]>=3.2",
    "alembic>=1.14",
    "redis>=5.2",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "httpx>=0.28",
    "ruff>=0.8",
    "mypy>=1.13",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "ASYNC"]

[tool.mypy]
python_version = "3.12"
files = ["app", "tests"]

[[tool.mypy.overrides]]
module = "app.*"
strict = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = ["integration: requires running postgres and redis"]
```

```python
# app/__init__.py
__version__ = "0.1.0"
```

```python
# tests/__init__.py
```

```
# .python-version
3.12
```

```makefile
# Makefile
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
```

- [ ] **Step 4: Install and run the test**

Run: `uv sync && uv run pytest tests/test_scaffold.py -v`
Expected: PASS

- [ ] **Step 5: Verify the whole toolchain**

Run: `make check`
Expected: ruff clean, mypy clean, 1 test passed

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .python-version Makefile app tests
git commit -m "Add project scaffold and tooling"
```

---

## Task 2: Settings

**Files:**
- Create: `app/config.py`, `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: the `app` package from Task 1
- Produces:
  ```python
  class Settings(BaseSettings):
      database_url: str
      redis_url: str
      version: str = "0.1.0"
  get_settings() -> Settings   # lru_cached
  ```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings


def test_settings_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/frontdesk")
    monkeypatch.setenv("REDIS_URL", "redis://cache:6379/0")
    settings = Settings()
    assert settings.database_url == "postgresql+psycopg://u:p@db:5432/frontdesk"
    assert settings.redis_url == "redis://cache:6379/0"


def test_missing_required_setting_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/frontdesk")
    monkeypatch.setenv("REDIS_URL", "redis://cache:6379/0")
    get_settings.cache_clear()
    assert get_settings() is get_settings()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 3: Implement**

```python
# app/config.py
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every environment variable the application reads, declared in one place."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str
    version: str = "0.1.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

```
# .env.example
DATABASE_URL=postgresql+psycopg://frontdesk:frontdesk@localhost:5438/frontdesk
REDIS_URL=redis://localhost:6382/0
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_config.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/config.py .env.example tests/test_config.py
git commit -m "Add settings module"
```

---

## Task 3: FastAPI app with a static health endpoint

**Files:**
- Create: `app/main.py`
- Test: `tests/test_main.py`, `tests/conftest.py`

**Interfaces:**
- Consumes: `get_settings()` from Task 2
- Produces: `app.main.app` (FastAPI instance); `GET /health` returning
  `{"status": "ok", "postgres": true, "redis": true, "version": str}`

Note: the probes are hard-coded `True` here and replaced with real ones in Task 7. This task
exists to get the HTTP surface and its test harness in place.

- [ ] **Step 1: Write the failing test**

```python
# tests/conftest.py
import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://frontdesk:frontdesk@localhost:5438/frontdesk"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6382/0")


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

```python
# tests/test_main.py
from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["postgres"] is True
    assert body["redis"] is True
    assert body["version"] == "0.1.0"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Implement**

```python
# app/main.py
from fastapi import FastAPI
from pydantic import BaseModel

from app.config import get_settings

app = FastAPI(title="Frontdesk", version=get_settings().version)


class HealthReport(BaseModel):
    status: str
    postgres: bool
    redis: bool
    version: str


@app.get("/health")
async def health() -> HealthReport:
    settings = get_settings()
    return HealthReport(status="ok", postgres=True, redis=True, version=settings.version)
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/conftest.py tests/test_main.py
git commit -m "Add FastAPI app with health endpoint"
```

---

## Task 4: Docker Compose and Dockerfile

**Files:**
- Create: `docker-compose.yml`, `Dockerfile`, `.dockerignore`
- Test: manual verification (this task's deliverable is an environment, not a function)

**Interfaces:**
- Consumes: `app.main:app` from Task 3
- Produces: `postgres` on host port 5438, `redis` on host port 6382, `api` on 8000

Host ports are deliberately non-default so this project cannot collide with another Postgres
or Redis already running on the machine. As of 2026-09-08 this machine already had six
Postgres containers (5432 starlyn, 5433 step-smile, 5434 merch-mvp, 5435 merch-ai,
5436 splitbill, 5437 mountain-nest) and two Redis (6380 step-smile, 6381 splitbill), so
Frontdesk takes 5438 and 6382. **step-smile is live client work — never take a port from it.**

- [ ] **Step 1: Write the Dockerfile**

```dockerfile
# Dockerfile
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /srv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```
# .dockerignore
.git
.venv
__pycache__
.pytest_cache
.mypy_cache
.ruff_cache
node_modules
storage
models
```

- [ ] **Step 2: Write the Compose file**

```yaml
# docker-compose.yml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: frontdesk
      POSTGRES_PASSWORD: frontdesk
      POSTGRES_DB: frontdesk
    ports:
      - "5438:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U frontdesk"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: redis:7-alpine
    ports:
      - "6382:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  api:
    build: .
    environment:
      DATABASE_URL: postgresql+psycopg://frontdesk:frontdesk@postgres:5432/frontdesk
      REDIS_URL: redis://redis:6379/0
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

volumes:
  pgdata:
```

- [ ] **Step 3: Bring it up and verify**

Run:
```bash
docker compose up -d --build
sleep 5
curl -s localhost:8000/health
```
Expected: `{"status":"ok","postgres":true,"redis":true,"version":"0.1.0"}`

- [ ] **Step 4: Verify the pgvector image really has the extension available**

Run:
```bash
docker compose exec postgres psql -U frontdesk -d frontdesk \
  -c "SELECT name FROM pg_available_extensions WHERE name='vector'"
```
Expected: one row, `vector`

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore docker-compose.yml
git commit -m "Add Docker Compose stack"
```

---

## Task 5: Database layer and the pgvector migration

**Files:**
- Create: `app/db.py`, `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`,
  `migrations/versions/0001_enable_pgvector.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `get_settings()` from Task 2
- Produces:
  ```python
  engine: AsyncEngine
  session_factory: async_sessionmaker[AsyncSession]
  get_session() -> AsyncIterator[AsyncSession]   # FastAPI dependency
  ```

- [ ] **Step 1: Write the failing integration test**

```python
# tests/test_db.py
import pytest
from sqlalchemy import text

from app.db import session_factory

pytestmark = pytest.mark.integration


async def test_pgvector_extension_is_enabled() -> None:
    async with session_factory() as session:
        result = await session.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        )
        assert result.scalar_one() == "vector"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_db.py -v -m integration`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.db'`

- [ ] **Step 3: Implement the database layer**

```python
# app/db.py
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
```

- [ ] **Step 4: Set up Alembic**

Run: `uv run alembic init -t async migrations`

Then edit `alembic.ini` — remove the hard-coded URL line so it comes from settings:

```ini
# alembic.ini — replace the sqlalchemy.url line with an empty value
sqlalchemy.url =
```

Replace the top of `migrations/env.py` config section:

```python
# migrations/env.py — add after the existing imports
from app.config import get_settings

config.set_main_option("sqlalchemy.url", get_settings().database_url)
```

- [ ] **Step 5: Write the migration**

```python
# migrations/versions/0001_enable_pgvector.py
"""Enable the pgvector extension.

Revision ID: 0001
Revises:
Create Date: 2026-09-08
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
```

- [ ] **Step 6: Apply it and run the test**

Run:
```bash
docker compose up -d --build
docker compose exec api uv run alembic upgrade head
uv run pytest tests/test_db.py -v -m integration
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/db.py alembic.ini migrations tests/test_db.py
git commit -m "Add database layer and pgvector migration"
```

---

## Task 6: Redis layer

**Files:**
- Create: `app/redis.py`
- Test: `tests/test_redis.py`

**Interfaces:**
- Consumes: `get_settings()` from Task 2
- Produces:
  ```python
  redis_client: Redis
  get_redis() -> Redis   # FastAPI dependency
  ```

- [ ] **Step 1: Write the failing integration test**

```python
# tests/test_redis.py
import pytest

from app.redis import redis_client

pytestmark = pytest.mark.integration


async def test_redis_round_trip() -> None:
    await redis_client.set("frontdesk:test", "value")
    assert await redis_client.get("frontdesk:test") == "value"
    await redis_client.delete("frontdesk:test")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_redis.py -v -m integration`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.redis'`

- [ ] **Step 3: Implement**

```python
# app/redis.py
from redis.asyncio import Redis

from app.config import get_settings

redis_client: Redis = Redis.from_url(get_settings().redis_url, decode_responses=True)


def get_redis() -> Redis:
    return redis_client
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/test_redis.py -v -m integration`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/redis.py tests/test_redis.py
git commit -m "Add Redis layer"
```

---

## Task 7: A health check that can go red

**This is the task the phase exists for.** Everything before it was scaffolding.

**Files:**
- Create: `app/health.py`
- Modify: `app/main.py` (replace the hard-coded probes)
- Test: `tests/test_health.py`

**Interfaces:**
- Consumes: `session_factory` (Task 5), `redis_client` (Task 6), `get_settings()` (Task 2)
- Produces:
  ```python
  class HealthReport(BaseModel):
      status: Literal["ok", "degraded"]
      postgres: bool
      redis: bool
      version: str

  async def check_postgres(factory: async_sessionmaker[AsyncSession]) -> bool
  async def check_redis(client: Redis) -> bool
  async def build_report(factory, client, version: str) -> HealthReport
  ```

`build_report` takes its dependencies as arguments rather than importing them. That is the
whole design: it makes the failure path testable without stopping a container.

- [ ] **Step 1: Write the failing tests — including the failure paths**

```python
# tests/test_health.py
from typing import Any

import pytest
from httpx import AsyncClient

from app.health import build_report, check_postgres, check_redis


class _FailingSessionFactory:
    def __call__(self) -> Any:
        raise ConnectionError("postgres is down")


class _FailingRedis:
    async def ping(self) -> bool:
        raise ConnectionError("redis is down")


class _WorkingRedis:
    async def ping(self) -> bool:
        return True


async def test_check_redis_true_when_reachable() -> None:
    assert await check_redis(_WorkingRedis()) is True  # type: ignore[arg-type]


async def test_check_redis_false_when_unreachable() -> None:
    assert await check_redis(_FailingRedis()) is False  # type: ignore[arg-type]


async def test_check_postgres_false_when_unreachable() -> None:
    assert await check_postgres(_FailingSessionFactory()) is False  # type: ignore[arg-type]


async def test_report_is_degraded_when_postgres_is_down() -> None:
    report = await build_report(
        _FailingSessionFactory(),  # type: ignore[arg-type]
        _WorkingRedis(),  # type: ignore[arg-type]
        version="0.1.0",
    )
    assert report.status == "degraded"
    assert report.postgres is False
    assert report.redis is True


async def test_report_is_degraded_when_redis_is_down() -> None:
    report = await build_report(
        _FailingSessionFactory(),  # type: ignore[arg-type]
        _FailingRedis(),  # type: ignore[arg-type]
        version="0.1.0",
    )
    assert report.status == "degraded"


@pytest.mark.integration
async def test_health_endpoint_is_ok_against_real_services(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["postgres"] is True
    assert body["redis"] is True
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.health'`

- [ ] **Step 3: Implement**

```python
# app/health.py
import asyncio
from typing import Literal

from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

PROBE_TIMEOUT_SECONDS = 2.0


class HealthReport(BaseModel):
    status: Literal["ok", "degraded"]
    postgres: bool
    redis: bool
    version: str


async def check_postgres(factory: async_sessionmaker[AsyncSession]) -> bool:
    """Return True only if a real query round-trips."""
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            async with factory() as session:
                result = await session.execute(text("SELECT 1"))
                return result.scalar_one() == 1
    except Exception:
        return False


async def check_redis(client: Redis) -> bool:
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            return bool(await client.ping())
    except Exception:
        return False


async def build_report(
    factory: async_sessionmaker[AsyncSession],
    client: Redis,
    version: str,
) -> HealthReport:
    postgres_ok, redis_ok = await asyncio.gather(
        check_postgres(factory),
        check_redis(client),
    )
    return HealthReport(
        status="ok" if postgres_ok and redis_ok else "degraded",
        postgres=postgres_ok,
        redis=redis_ok,
        version=version,
    )
```

- [ ] **Step 4: Wire it into the app**

Replace the whole of `app/main.py`:

```python
# app/main.py
from fastapi import FastAPI

from app.config import get_settings
from app.db import session_factory
from app.health import HealthReport, build_report
from app.redis import redis_client

app = FastAPI(title="Frontdesk", version=get_settings().version)


@app.get("/health")
async def health() -> HealthReport:
    return await build_report(session_factory, redis_client, get_settings().version)
```

- [ ] **Step 5: Delete the now-wrong test from Task 3**

`tests/test_main.py::test_health_returns_ok` asserted against the hard-coded response and
would now require running services. Delete `tests/test_main.py` — its replacement is
`tests/test_health.py::test_health_endpoint_is_ok_against_real_services`.

```bash
git rm tests/test_main.py
```

- [ ] **Step 6: Run the unit tests without any services running**

Run:
```bash
docker compose down
uv run pytest tests/test_health.py -v -m "not integration"
```
Expected: 5 passed. **This is the proof the check can go red** — the degraded paths are
exercised with no containers running at all.

- [ ] **Step 7: Run the integration test with services up**

Run:
```bash
docker compose up -d --build
docker compose exec api uv run alembic upgrade head
uv run pytest tests/test_health.py -v -m integration
```
Expected: PASS

- [ ] **Step 8: Verify the red path end to end, by hand, once**

Run:
```bash
docker compose stop postgres
curl -s localhost:8000/health
docker compose start postgres
```
Expected: `{"status":"degraded","postgres":false,"redis":true,"version":"0.1.0"}`

- [ ] **Step 9: Commit**

```bash
git add app/health.py app/main.py tests/test_health.py
git commit -m "Add health check that probes real dependencies"
```

---

## Task 8: Continuous integration

**Files:**
- Create: `.github/workflows/ci.yml`
- Test: a green CI run on a pushed branch

**Interfaces:**
- Consumes: `make check` from Task 1, the Compose services from Task 4
- Produces: CI on every push and pull request

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: ["**"]
  pull_request:

jobs:
  check:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: frontdesk
          POSTGRES_PASSWORD: frontdesk
          POSTGRES_DB: frontdesk
        ports: ["5438:5432"]
        options: >-
          --health-cmd "pg_isready -U frontdesk"
          --health-interval 5s --health-timeout 3s --health-retries 10
      redis:
        image: redis:7-alpine
        ports: ["6382:6379"]
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 5s --health-timeout 3s --health-retries 10

    env:
      DATABASE_URL: postgresql+psycopg://frontdesk:frontdesk@localhost:5438/frontdesk
      REDIS_URL: redis://localhost:6382/0

    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - name: Install dependencies
        run: uv sync --frozen

      - name: Apply migrations
        run: uv run alembic upgrade head

      - name: Lint
        run: uv run ruff check . && uv run ruff format --check .

      - name: Type check
        run: uv run mypy

      - name: Test
        run: uv run pytest -v

  docker:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build image
        run: docker build -t frontdesk:ci .
```

- [ ] **Step 2: Push and watch it**

```bash
git add .github/workflows/ci.yml
git commit -m "Add CI workflow"
git push -u origin HEAD
gh run watch
```
Expected: both jobs green.

- [ ] **Step 3: If CI is red, fix forward**

The most likely failure is the migration step: `alembic upgrade head` needs `app.config` to
import cleanly, which needs both env vars set. They are set at job level above. The second most
likely is `ruff format --check` failing on files never formatted — run `uv run ruff format .`
locally, commit, and push again.

- [ ] **Step 4: Commit any fixes and confirm green**

Run: `gh run list --limit 1`
Expected: `completed  success`

---

## Self-review

**Spec coverage.** Phase 0's roadmap section lists eleven files; all eleven appear in the File
Structure table and are created by a task. The five phase exit criteria map to: Task 4 Step 3
(compose + curl), Task 5 Step 6 (pgvector), Task 1 Step 5 (`make check`), Task 8 Step 2 (CI),
and Task 7 Steps 6 and 8 (the red path, tested and hand-verified).

**Placeholder scan.** No TBDs. Every code step contains the real content. Task 4 is the only
task without an automated test, because its deliverable is an environment rather than a
function — its verification is two explicit commands with expected output.

**Type consistency.** `HealthReport` is defined once, in `app/health.py`, and imported by
`app/main.py` — Task 3 defines a temporary copy in `main.py` which Task 7 Step 4 replaces
wholesale rather than leaving duplicated. `session_factory` and `redis_client` are the exact
names produced by Tasks 5 and 6 and consumed by Task 7. `get_settings()` is used by Tasks 3,
5, 6 and 7 under that one name.

**One deliberate rework.** Task 3 builds a health endpoint with hard-coded probes and Task 7
replaces it, deleting Task 3's test. That is not waste: it gets the HTTP surface and its async
test harness working before the dependency wiring exists, so a failure in Task 7 is
unambiguously about the probes rather than about FastAPI or httpx setup.
