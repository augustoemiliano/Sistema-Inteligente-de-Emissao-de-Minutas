"""Configuração centralizada — única fonte de verdade para ambiente e segredos."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "staging", "production"] = "development"
    project_name: str = Field(default="Sistema Inteligente de Emissão de Minutas com IA")
    api_v1_prefix: str = "/api/v1"

    secret_key: str = Field(..., min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    database_url: str = Field(..., alias="DATABASE_URL")
    database_url_sync: str = Field(..., alias="DATABASE_URL_SYNC")

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    celery_broker_url: str = Field(default="redis://localhost:6379/0", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(
        default="redis://localhost:6379/0",
        alias="CELERY_RESULT_BACKEND",
    )

    # NoDecode: pydantic-settings não pode json.loads() URL simples em list[str] (quebra o container).
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    upload_dir: Path = Field(default=Path("uploads"), alias="UPLOAD_DIR")
    generated_documents_dir: Path = Field(
        default=Path("generated_documents"),
        alias="GENERATED_DOCUMENTS_DIR",
    )
    log_dir: Path = Field(default=Path("logs"), alias="LOG_DIR")
    wkhtmltopdf_path: str | None = Field(default=None, alias="WKHTMLTOPDF_PATH")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Cache evita re-parsear .env a cada request — padrão comum em serviços stateless
    return Settings()
