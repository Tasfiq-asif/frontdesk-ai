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
    assert report.postgres is False
    assert report.redis is False


@pytest.mark.integration
async def test_health_endpoint_is_ok_against_real_services(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["postgres"] is True
    assert body["redis"] is True
