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


@pytest.fixture(autouse=True)
async def _reset_redis_pool() -> AsyncIterator[None]:
    """Drop the Redis connection pool after every test.

    ``app.redis.redis_client`` is a module-level singleton, which is correct in production
    (one process, one event loop) but wrong under pytest-asyncio, which gives every test its
    own loop. A connection opened on one test's loop is torn down under the next test's loop
    and raises "Event loop is closed". The symptom is a test that passes alone and fails in
    the suite, so it looks like test pollution rather than a lifecycle bug.
    """
    yield
    from app.redis import redis_client

    await redis_client.aclose()
