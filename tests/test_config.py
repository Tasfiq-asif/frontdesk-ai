from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings


def test_settings_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/frontdesk")
    monkeypatch.setenv("REDIS_URL", "redis://cache:6379/0")
    settings = Settings()
    assert settings.database_url == "postgresql+psycopg://u:p@db:5432/frontdesk"
    assert settings.redis_url == "redis://cache:6379/0"


def test_missing_required_setting_fails_loudly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # chdir somewhere with no .env, so the constructor really has nothing to read.
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings()


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/frontdesk")
    monkeypatch.setenv("REDIS_URL", "redis://cache:6379/0")
    get_settings.cache_clear()
    assert get_settings() is get_settings()
