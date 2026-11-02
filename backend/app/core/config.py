from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Backend settings, read from environment variables (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/clinic"
    groq_api_key: str = ""
    llm_model: str = ""
    stt_model: str = "whisper-large-v3-turbo"
    frontend_origin: str = "http://localhost:3000"
    session_secret: str = "dev-only-session-secret-change-me"
    cron_secret: str = "dev-only-cron-secret"
    max_call_seconds: int = 300
    calls_per_ip_per_day: int = 10
    clinic_timezone: str = "Asia/Manila"
    provider: Literal["groq", "fake"] = "groq"


@lru_cache
def get_settings() -> Settings:
    return Settings()
