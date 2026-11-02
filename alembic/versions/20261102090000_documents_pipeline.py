"""templates, minutas versionadas e uploads

Revision ID: 20261102090000
Revises: 20260509120000
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Tipos portáveis: UUID/JSONB nativos no PostgreSQL, equivalentes genéricos no SQLite
JSONB = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

revision: str = "20261102090000"
down_revision: str | Sequence[str] | None = "20260509120000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "document_templates",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("variables", JSONB, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        op.f("ix_document_templates_category"), "document_templates", ["category"], unique=False
    )

    op.create_table(
        "minutas",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("template_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["template_id"], ["document_templates.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_minutas_status"), "minutas", ["status"], unique=False)
    op.create_index(op.f("ix_minutas_template_id"), "minutas", ["template_id"], unique=False)

    op.create_table(
        "minuta_versions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("minuta_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("variables", JSONB, nullable=False),
        sa.Column("rendered_content", sa.Text(), nullable=False),
        sa.Column("change_note", sa.String(length=500), nullable=True),
        sa.Column("pdf_status", sa.String(length=32), nullable=False),
        sa.Column("pdf_path", sa.String(length=500), nullable=True),
        sa.Column("pdf_error", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), nullable=True),
        _ts("created_at"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["minuta_id"], ["minutas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("minuta_id", "version", name="uq_minuta_version"),
    )
    op.create_index(
        op.f("ix_minuta_versions_minuta_id"), "minuta_versions", ["minuta_id"], unique=False
    )

    op.create_table(
        "document_uploads",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=100), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("extraction_method", sa.String(length=32), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stored_filename"),
    )
    op.create_index(
        op.f("ix_document_uploads_sha256"), "document_uploads", ["sha256"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_document_uploads_sha256"), table_name="document_uploads")
    op.drop_table("document_uploads")
    op.drop_index(op.f("ix_minuta_versions_minuta_id"), table_name="minuta_versions")
    op.drop_table("minuta_versions")
    op.drop_index(op.f("ix_minutas_template_id"), table_name="minutas")
    op.drop_index(op.f("ix_minutas_status"), table_name="minutas")
    op.drop_table("minutas")
    op.drop_index(op.f("ix_document_templates_category"), table_name="document_templates")
    op.drop_table("document_templates")
