import pytest

from app.redis import redis_client

pytestmark = pytest.mark.integration


async def test_redis_round_trip() -> None:
    await redis_client.set("frontdesk:test", "value")
    assert await redis_client.get("frontdesk:test") == "value"
    await redis_client.delete("frontdesk:test")
