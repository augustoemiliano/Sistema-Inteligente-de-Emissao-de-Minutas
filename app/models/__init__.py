"""Re-export dos models — imports estáveis para Alembic e testes."""

from app.models.document import (
    DocumentTemplate,
    DocumentUpload,
    Minuta,
    MinutaStatus,
    MinutaVersion,
    PdfStatus,
    UploadStatus,
)
from app.models.user import AuditLog, RefreshToken, User, UserRole

__all__ = [
    "AuditLog",
    "DocumentTemplate",
    "DocumentUpload",
    "Minuta",
    "MinutaStatus",
    "MinutaVersion",
    "PdfStatus",
    "RefreshToken",
    "UploadStatus",
    "User",
    "UserRole",
]
