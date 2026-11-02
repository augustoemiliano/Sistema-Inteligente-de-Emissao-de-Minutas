"""Tasks de documentos: geração de PDF da minuta e extração de texto (OCR) de uploads."""

from __future__ import annotations

import time
from uuid import UUID

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.logger import get_logger
from app.db.session import get_sync_session_factory
from app.models.document import DocumentUpload, Minuta, MinutaVersion, PdfStatus, UploadStatus
from app.models.user import AuditLog
from app.services.ocr_service import extract_text
from app.services.pdf_service import html_to_pdf
from app.services.storage import safe_join, write_bytes_atomic
from app.services.template_engine import render_document_html

logger = get_logger(__name__)


def _uuid(value: str | None) -> UUID | None:
    return UUID(value) if value else None


@celery_app.task(name="documents.generate_minuta_pdf", acks_late=True)
def generate_minuta_pdf(version_id: str, user_id: str | None = None) -> dict:
    settings = get_settings()
    started = time.monotonic()
    with get_sync_session_factory()() as session:
        version = session.get(MinutaVersion, UUID(version_id))
        if version is None:
            logger.warning("Versão %s não encontrada para PDF", version_id)
            return {"status": "missing"}
        minuta = session.get(Minuta, version.minuta_id)
        assert minuta is not None

        try:
            html = render_document_html(
                title=minuta.title, body_html=version.rendered_content, version=version.version
            )
            pdf_bytes, engine = html_to_pdf(html, title=minuta.title, settings=settings)
            relative = f"{minuta.id}/v{version.version}.pdf"
            write_bytes_atomic(settings.generated_documents_dir, relative, pdf_bytes)
        except Exception as exc:
            logger.exception("Falha ao gerar PDF da versão %s", version_id)
            version.pdf_status = PdfStatus.FAILED
            version.pdf_error = str(exc)[:1000]
            session.add(
                AuditLog(
                    action="minuta.pdf_failed",
                    user_id=_uuid(user_id),
                    resource_type="minuta",
                    resource_id=minuta.id,
                    extra={"version": version.version, "error": str(exc)[:300]},
                )
            )
            session.commit()
            return {"status": PdfStatus.FAILED.value}

        version.pdf_status = PdfStatus.READY
        version.pdf_path = relative
        version.pdf_error = None
        session.add(
            AuditLog(
                action="minuta.pdf_generated",
                user_id=_uuid(user_id),
                resource_type="minuta",
                resource_id=minuta.id,
                extra={"version": version.version, "engine": engine, "bytes": len(pdf_bytes)},
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        )
        session.commit()
        return {"status": PdfStatus.READY.value, "path": relative, "engine": engine}


@celery_app.task(name="documents.process_upload", acks_late=True)
def process_upload(upload_id: str, user_id: str | None = None) -> dict:
    settings = get_settings()
    started = time.monotonic()
    with get_sync_session_factory()() as session:
        upload = session.get(DocumentUpload, UUID(upload_id))
        if upload is None:
            return {"status": "missing"}
        upload.status = UploadStatus.PROCESSING
        session.commit()

        extra: dict[str, object]
        try:
            path = safe_join(settings.upload_dir, upload.stored_filename)
            result = extract_text(path, upload.content_type, settings)
        except Exception as exc:
            logger.warning("Extração falhou para upload %s: %s", upload_id, exc)
            upload.status = UploadStatus.FAILED
            upload.error = str(exc)[:1000]
            action, extra = "upload.extraction_failed", {"error": str(exc)[:300]}
        else:
            upload.status = UploadStatus.DONE
            upload.extracted_text = result.text
            upload.extraction_method = result.method
            upload.error = None
            action, extra = "upload.extracted", {"method": result.method, "chars": len(result.text)}

        session.add(
            AuditLog(
                action=action,
                user_id=_uuid(user_id),
                resource_type="upload",
                resource_id=upload.id,
                extra=extra,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        )
        session.commit()
        return {"status": upload.status.value}
