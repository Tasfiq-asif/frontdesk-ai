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
