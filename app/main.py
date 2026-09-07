from fastapi import FastAPI

from app.config import get_settings
from app.db import session_factory
from app.health import HealthReport, build_report
from app.redis import redis_client

app = FastAPI(title="Frontdesk", version=get_settings().version)


@app.get("/health")
async def health() -> HealthReport:
    return await build_report(session_factory, redis_client, get_settings().version)
