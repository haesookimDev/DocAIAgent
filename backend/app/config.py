"""Application configuration using pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # LLM API Keys
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # LLM Settings
    default_llm_provider: Literal["anthropic", "openai"] = "anthropic"
    anthropic_model: str = "claude-sonnet-4-20250514"
    openai_model: str = "gpt-4o"

    # Server Settings
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # Storage
    storage_path: str = "./storage"

    # Database (optional)
    database_url: str | None = None

    # Redis (optional)
    redis_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
