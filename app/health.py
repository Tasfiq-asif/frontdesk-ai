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
    """Return True only if a real query round-trips.

    Dependencies are injected rather than imported so the failure path is testable
    without stopping a container. A health check that cannot go red is worse than none.
    """
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS), factory() as session:
            result = await session.execute(text("SELECT 1"))
            return bool(result.scalar_one() == 1)
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
