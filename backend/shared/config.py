"""공통 설정: 환경변수 로드·검증."""
import os
import warnings
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

    # DB (필수, 기본값 없음 — Neon PostgreSQL 사용)
    database_url: str

    # 앱
    allowed_origins: str = "http://localhost:3000"
    environment: str = "development"

    # MCP (기본 비활성화 — 실제 도구 준비 후 true로 변경)
    mcp_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    # SQLite 사용 시 경고 (운영 환경 부적합)
    if s.database_url.startswith("sqlite"):
        warnings.warn(
            "SQLite는 운영 환경용이 아닙니다. Neon PostgreSQL(postgresql+asyncpg://) 사용 권장.",
            RuntimeWarning,
            stacklevel=2,
        )
    return s