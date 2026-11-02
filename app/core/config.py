"""Configuração centralizada — única fonte de verdade para ambiente e segredos."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Valores de exemplo que nunca devem chegar a produção.
_INSECURE_SECRET_KEYS = {
    "change-me-use-openssl-rand-hex-32",
    "dev-secret-key-must-be-at-least-32-characters-long!!",
}


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
    bcrypt_rounds: int = Field(default=12, ge=4, le=16, alias="BCRYPT_ROUNDS")
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    database_url: str = Field(..., alias="DATABASE_URL")
    database_url_sync: str = Field(..., alias="DATABASE_URL_SYNC")
    # Sem pool de conexões (testes: cada TestClient tem seu próprio event loop)
    database_nullpool: bool = Field(default=False, alias="DATABASE_NULLPOOL")

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    celery_broker_url: str = Field(default="redis://localhost:6379/0", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(
        default="redis://localhost:6379/0",
        alias="CELERY_RESULT_BACKEND",
    )
    # true = tasks executam no próprio processo da API (dev sem Redis / testes).
    celery_task_always_eager: bool = Field(default=False, alias="CELERY_TASK_ALWAYS_EAGER")

    # NoDecode: pydantic-settings não pode json.loads() URL simples em list[str]
    # (quebra o container). Formato esperado: lista separada por vírgulas.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # IA: "auto" usa OpenAI se houver chave e cai para o provider fake (offline) caso contrário.
    ai_provider: Literal["auto", "openai", "fake"] = Field(default="auto", alias="AI_PROVIDER")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_timeout_seconds: float = Field(default=30.0, alias="OPENAI_TIMEOUT_SECONDS")
    ai_max_input_chars: int = Field(default=20_000, alias="AI_MAX_INPUT_CHARS")

    upload_dir: Path = Field(default=Path("uploads"), alias="UPLOAD_DIR")
    max_upload_size_mb: int = Field(default=10, alias="MAX_UPLOAD_SIZE_MB")
    generated_documents_dir: Path = Field(
        default=Path("generated_documents"),
        alias="GENERATED_DOCUMENTS_DIR",
    )
    log_dir: Path = Field(default=Path("logs"), alias="LOG_DIR")

    # PDF: "auto" usa wkhtmltopdf se o binário existir; senão gera com ReportLab (puro Python).
    pdf_engine: Literal["auto", "wkhtmltopdf", "reportlab"] = Field(
        default="auto", alias="PDF_ENGINE"
    )
    wkhtmltopdf_path: str | None = Field(default=None, alias="WKHTMLTOPDF_PATH")

    # OCR (Tesseract): opcional — PDFs com texto embutido não precisam dele.
    tesseract_cmd: str | None = Field(default=None, alias="TESSERACT_CMD")
    ocr_language: str = Field(default="por", alias="OCR_LANGUAGE")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v

    @field_validator("wkhtmltopdf_path", "tesseract_cmd", "openai_api_key", mode="before")
    @classmethod
    def empty_as_none(cls, v: str | None) -> str | None:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @model_validator(mode="after")
    def reject_insecure_secret_in_production(self) -> Settings:
        if self.is_production and self.secret_key in _INSECURE_SECRET_KEYS:
            raise ValueError("SECRET_KEY de exemplo não pode ser usada em produção")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Cache evita re-parsear .env a cada request — padrão comum em serviços stateless
    return Settings()  # type: ignore[call-arg]  # valores vêm do ambiente/.env
