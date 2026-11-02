from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.document import MinutaStatus, PdfStatus, UploadStatus

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# ---------- Templates ----------


class TemplateCreate(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=100)
    content: str = Field(min_length=1, max_length=200_000)


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=100)
    content: str | None = Field(default=None, min_length=1, max_length=200_000)
    is_active: bool | None = None


class TemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    category: str | None
    content: str
    variables: list[str]
    version: int
    is_active: bool
    created_by_id: UUID | None
    created_at: datetime
    updated_at: datetime


class TemplatePreviewRequest(BaseModel):
    variables: dict[str, Any] = Field(default_factory=dict)


class TemplatePreviewResponse(BaseModel):
    html: str
    missing_variables: list[str]


# ---------- Minutas ----------


class MinutaCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    template_id: UUID
    variables: dict[str, Any] = Field(default_factory=dict)


class MinutaUpdate(BaseModel):
    """Gera uma NOVA versão; versões anteriores ficam imutáveis."""

    title: str | None = Field(default=None, min_length=3, max_length=255)
    variables: dict[str, Any]
    change_note: str | None = Field(default=None, max_length=500)


class MinutaStatusChange(BaseModel):
    status: MinutaStatus
    comment: str | None = Field(default=None, max_length=500)


class MinutaVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version: int
    template_version: int
    variables: dict[str, Any]
    rendered_content: str
    change_note: str | None
    pdf_status: PdfStatus
    pdf_error: str | None
    created_by_id: UUID | None
    created_at: datetime


class MinutaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    template_id: UUID
    status: MinutaStatus
    current_version: int
    created_by_id: UUID | None
    created_at: datetime
    updated_at: datetime


class MinutaDetailResponse(MinutaResponse):
    latest: MinutaVersionResponse


class PdfJobResponse(BaseModel):
    minuta_id: UUID
    version: int
    pdf_status: PdfStatus
    task_id: str | None = None
    download_url: str | None = None
    error: str | None = None


# ---------- Uploads ----------


class UploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    status: UploadStatus
    extraction_method: str | None
    extracted_text: str | None
    error: str | None
    created_by_id: UUID | None
    created_at: datetime


# ---------- Auditoria ----------


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID | None
    action: str
    resource_type: str | None
    resource_id: UUID | None
    ip_address: str | None
    user_agent: str | None
    extra: dict[str, Any] | None
    duration_ms: int | None
    created_at: datetime


# ---------- IA ----------


class ClauseSuggestionRequest(BaseModel):
    contract_type: str = Field(min_length=3, max_length=200)
    objective: str = Field(min_length=3, max_length=1000)
    context: str | None = Field(default=None, max_length=5000)


class ReviewRequest(BaseModel):
    """Informe exatamente uma fonte: minuta, upload (texto extraído) ou texto livre."""

    minuta_id: UUID | None = None
    upload_id: UUID | None = None
    text: str | None = Field(default=None, min_length=20, max_length=100_000)

    @model_validator(mode="after")
    def exactly_one_source(self) -> ReviewRequest:
        sources = [s for s in (self.minuta_id, self.upload_id, self.text) if s is not None]
        if len(sources) != 1:
            raise ValueError("Informe exatamente um entre minuta_id, upload_id e text")
        return self


class AIResponse(BaseModel):
    provider: str
    model: str
    content: str
