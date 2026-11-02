"""Tipos portáveis: nativos no PostgreSQL (UUID/JSONB), genéricos em SQLite (testes)."""

from __future__ import annotations

from sqlalchemy import JSON, Uuid
from sqlalchemy.dialects.postgresql import JSONB

GUID = Uuid(as_uuid=True)
JSONType = JSON().with_variant(JSONB(), "postgresql")
