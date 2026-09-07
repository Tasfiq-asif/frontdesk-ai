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
