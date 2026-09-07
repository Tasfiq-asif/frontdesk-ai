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
