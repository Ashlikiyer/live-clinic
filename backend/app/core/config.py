from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def asyncpg_url(url: str) -> str:
    """Accept a Postgres URL as hosts give it (Supabase: `postgresql://...?sslmode=require`)
    and point it at the asyncpg driver this app uses. Pure."""
    for prefix in (
        "postgresql://",
        "postgres://",
        "postgresql+psycopg://",
        "postgresql+psycopg2://",
    ):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix) :]
            break
    # asyncpg spells libpq's sslmode as ssl.
    return url.replace("sslmode=", "ssl=")


class Settings(BaseSettings):
    """Backend settings, read from environment variables (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/clinic"
    groq_api_key: str = ""
    llm_model: str = ""
    # Groq "reasoning_effort" for reasoning models (e.g. "none" for Qwen 3); empty = not sent.
    llm_reasoning_effort: str = ""
    # Tried in order when LLM_MODEL is rate limited: "model:reasoning_effort,model:...".
    llm_fallback_models: str = ""
    stt_model: str = "whisper-large-v3-turbo"
    # Whisper language code ("en", "tl"); empty detects it per utterance (English or Tagalog).
    stt_language: str = ""
    # Mia's voice when the browser asks the server for speech (Groq Orpheus).
    tts_model: str = "canopylabs/orpheus-v1-english"
    tts_voice: str = "hannah"
    frontend_origin: str = "http://localhost:3000"
    session_secret: str = "dev-only-session-secret-change-me"
    cron_secret: str = "dev-only-cron-secret"
    max_call_seconds: int = 300
    calls_per_ip_per_day: int = 10
    sessions_per_ip_per_day: int = 30
    clinic_timezone: str = "Asia/Manila"
    provider: Literal["groq", "fake"] = "groq"

    @field_validator("database_url")
    @classmethod
    def _use_asyncpg(cls, value: str) -> str:
        return asyncpg_url(value.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
