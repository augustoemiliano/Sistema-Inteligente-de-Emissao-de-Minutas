"""Templates Jinja2, minutas versionadas e uploads (pipeline de documentos)."""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import GUID, JSONType


class MinutaStatus(str, enum.Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    ARCHIVED = "archived"


class PdfStatus(str, enum.Enum):
    NONE = "none"
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class UploadStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


def _enum(enum_cls: type[enum.Enum], name: str) -> SAEnum:
    # native_enum=False: VARCHAR + CHECK lógico no app — migrations mais simples
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )


class DocumentTemplate(Base):
    __tablename__ = "document_templates"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100), index=True)
    # Corpo em HTML + Jinja2 (renderizado em sandbox, com autoescape)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_id: Mapped[UUID | None] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Minuta(Base):
    __tablename__ = "minutas"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    template_id: Mapped[UUID] = mapped_column(
        GUID, ForeignKey("document_templates.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[MinutaStatus] = mapped_column(
        _enum(MinutaStatus, "minuta_status"),
        nullable=False,
        default=MinutaStatus.DRAFT,
        index=True,
    )
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_id: Mapped[UUID | None] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    versions: Mapped[list[MinutaVersion]] = relationship(
        back_populates="minuta",
        cascade="all, delete-orphan",
        order_by="MinutaVersion.version",
    )


class MinutaVersion(Base):
    """Snapshot imutável: variáveis + conteúdo renderizado + PDF daquela versão."""

    __tablename__ = "minuta_versions"
    __table_args__ = (UniqueConstraint("minuta_id", "version", name="uq_minuta_version"),)

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    minuta_id: Mapped[UUID] = mapped_column(
        GUID, ForeignKey("minutas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)
    variables: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    rendered_content: Mapped[str] = mapped_column(Text, nullable=False)
    change_note: Mapped[str | None] = mapped_column(String(500))
    pdf_status: Mapped[PdfStatus] = mapped_column(
        _enum(PdfStatus, "pdf_status"), nullable=False, default=PdfStatus.NONE
    )
    # Caminho RELATIVO a GENERATED_DOCUMENTS_DIR — nunca absoluto
    pdf_path: Mapped[str | None] = mapped_column(String(500))
    pdf_error: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[UUID | None] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    minuta: Mapped[Minuta] = relationship(back_populates="versions")


class DocumentUpload(Base):
    __tablename__ = "document_uploads"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # Nome gerado pelo servidor (uuid + extensão whitelisted) — relativo a UPLOAD_DIR
    stored_filename: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[UploadStatus] = mapped_column(
        _enum(UploadStatus, "upload_status"), nullable=False, default=UploadStatus.PENDING
    )
    extraction_method: Mapped[str | None] = mapped_column(String(32))
    extracted_text: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[UUID | None] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
