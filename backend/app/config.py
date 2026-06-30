"""Application settings, loaded from environment / .env via pydantic-settings."""

from functools import lru_cache
import os

from pydantic_settings import BaseSettings, SettingsConfigDict

# Cognee skips best-effort telemetry in dev/test. Default the hackathon app to
# local-dev mode unless the deployment environment explicitly says otherwise.
os.environ.setdefault("ENV", "dev")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM / embeddings (consumed by Cognee)
    llm_api_key: str = ""
    openai_api_key: str = ""
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"

    # Tools
    tavily_api_key: str = ""

    # App DB (thin coordination tables — Cognee owns graph/vector/relational memory)
    app_database_url: str = "sqlite+aiosqlite:///./agentos.db"

    # Demo auth
    demo_user: str = "demo"
    demo_token: str = "dev-token"


@lru_cache
def get_settings() -> Settings:
    return Settings()
