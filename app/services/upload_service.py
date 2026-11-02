"""Recebimento seguro de arquivos para extração de texto/OCR.

- Tipo validado pelos *magic bytes* (não confiamos em extensão nem em Content-Type do cliente);
- Tamanho limitado durante a leitura (não carrega arquivos gigantes em memória);
- Nome físico gerado pelo servidor (uuid + extensão fixa) — o nome original é só metadado.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import PureWindowsPath
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.context import RequestMeta
from app.core.config import get_settings
from app.core.exceptions import AppError, NotFoundError
from app.core.logger import get_logger
from app.models.document import DocumentUpload, UploadStatus
from app.models.user import User
from app.repositories.audit_repository import AuditRepository
from app.repositories.document_repository import UploadRepository
from app.services.storage import write_bytes_atomic

logger = get_logger(__name__)

_SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"II*\x00", "image/tiff", ".tiff"),
    (b"MM\x00*", "image/tiff", ".tiff"),
]
_CHUNK = 1024 * 1024


def detect_type(head: bytes) -> tuple[str, str] | None:
    for magic, content_type, ext in _SIGNATURES:
        if head.startswith(magic):
            return content_type, ext
    return None


def sanitize_filename(name: str | None) -> str:
    # PureWindowsPath trata "/" e "\" — remove qualquer diretório enviado pelo cliente
    base = PureWindowsPath(name or "").name
    base = unicodedata.normalize("NFKC", base)
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip(" .")
    return (base or "arquivo")[:255]


class UploadService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = UploadRepository(session)
        self._audit = AuditRepository(session)

    async def get(self, upload_id: UUID) -> DocumentUpload:
        upload = await self._repo.get(upload_id)
        if upload is None:
            raise NotFoundError("Upload não encontrado")
        return upload

    async def paginate(self, **filters):
        return await self._repo.paginate(**filters)

    async def create(self, file: UploadFile, user: User, meta: RequestMeta) -> DocumentUpload:
        settings = get_settings()
        limit = settings.max_upload_size_bytes

        chunks: list[bytes] = []
        size = 0
        digest = hashlib.sha256()
        while chunk := await file.read(_CHUNK):
            size += len(chunk)
            if size > limit:
                raise AppError(
                    f"Arquivo excede o limite de {settings.max_upload_size_mb} MB",
                    status_code=413,
                )
            digest.update(chunk)
            chunks.append(chunk)
        data = b"".join(chunks)
        if not data:
            raise AppError("Arquivo vazio", status_code=422)

        detected = detect_type(data[:16])
        if detected is None:
            raise AppError(
                "Tipo de arquivo não suportado (aceitos: PDF, PNG, JPEG, TIFF)", status_code=415
            )
        content_type, ext = detected

        upload_id = uuid4()
        stored = f"{upload_id.hex}{ext}"
        write_bytes_atomic(settings.upload_dir, stored, data)

        upload = await self._repo.add(
            DocumentUpload(
                id=upload_id,
                original_filename=sanitize_filename(file.filename),
                stored_filename=stored,
                content_type=content_type,
                size_bytes=size,
                sha256=digest.hexdigest(),
                status=UploadStatus.PENDING,
                created_by_id=user.id,
            )
        )
        await self._audit.log_action(
            action="upload.create",
            user_id=user.id,
            resource_type="upload",
            resource_id=upload.id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            extra={"content_type": content_type, "size_bytes": size},
        )
        await self._session.commit()

        from app.tasks.documents import process_upload

        try:
            process_upload.delay(str(upload.id), str(user.id))
        except Exception:
            # Arquivo já está salvo; pode ser reprocessado quando a fila voltar
            logger.exception("Falha ao enfileirar OCR do upload %s", upload.id)
            upload.status = UploadStatus.FAILED
            upload.error = "Fila de processamento indisponível"
            await self._session.commit()

        await self._session.refresh(upload)
        return upload
