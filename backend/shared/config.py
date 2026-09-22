"""공통 설정: 환경변수 로드·검증."""
import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    openrouter_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"

    # DB
    database_url: str = "postgresql+asyncpg://app:app@db:5432/app"

    # 앱
    allowed_origins: str = "http://localhost:3000"
    environment: str = "development"

    # MCP
    mcp_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()