from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import LLMProvider, LLMProviderError, get_llm_provider
from app.ai.services.assistant import MinutaAssistant, html_to_plain
from app.api.dependencies.auth import require_roles
from app.api.dependencies.context import RequestMeta, get_request_meta
from app.api.dependencies.db import get_db
from app.core.exceptions import AppError, ForbiddenError
from app.models.document import UploadStatus
from app.models.user import User, UserRole
from app.repositories.audit_repository import AuditRepository
from app.schemas.documents import AIResponse, ClauseSuggestionRequest, ReviewRequest
from app.services.minuta_service import MinutaService
from app.services.upload_service import UploadService

router = APIRouter(prefix="/ai", tags=["ia"])
editor_or_admin = require_roles(UserRole.EDITOR, UserRole.ADMIN)


def get_provider() -> LLMProvider:
    # Dependência isolada para facilitar override em testes
    return get_llm_provider()


async def _audit(session, *, action, user, meta, started, extra) -> None:
    await AuditRepository(session).log_action(
        action=action,
        user_id=user.id,
        resource_type="ai",
        ip_address=meta.ip_address,
        user_agent=meta.user_agent,
        extra=extra,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    await session.commit()


@router.post("/clauses/suggest", response_model=AIResponse, summary="Sugere uma cláusula")
async def suggest_clause(
    payload: ClauseSuggestionRequest,
    user: User = Depends(editor_or_admin),
    meta: RequestMeta = Depends(get_request_meta),
    provider: LLMProvider = Depends(get_provider),
    session: AsyncSession = Depends(get_db),
):
    started = time.monotonic()
    try:
        result = await MinutaAssistant(provider).suggest_clause(
            contract_type=payload.contract_type,
            objective=payload.objective,
            context=payload.context,
        )
    except LLMProviderError as exc:
        raise AppError(str(exc), status_code=503) from exc
    await _audit(
        session,
        action="ai.clause_suggest",
        user=user,
        meta=meta,
        started=started,
        extra={"provider": result.provider, "model": result.model},
    )
    return AIResponse(provider=result.provider, model=result.model, content=result.content)


@router.post("/review", response_model=AIResponse, summary="Resumo e pontos de atenção")
async def review(
    payload: ReviewRequest,
    user: User = Depends(editor_or_admin),
    meta: RequestMeta = Depends(get_request_meta),
    provider: LLMProvider = Depends(get_provider),
    session: AsyncSession = Depends(get_db),
):
    started = time.monotonic()
    source: dict[str, str]
    if payload.minuta_id:
        service = MinutaService(session)
        minuta = await service.get(payload.minuta_id)
        text = html_to_plain((await service.latest_version(minuta)).rendered_content)
        source = {"minuta_id": str(minuta.id)}
    elif payload.upload_id:
        upload = await UploadService(session).get(payload.upload_id)
        if user.role != UserRole.ADMIN and upload.created_by_id != user.id:
            raise ForbiddenError("Upload pertence a outro usuário")
        if upload.status != UploadStatus.DONE or not upload.extracted_text:
            raise AppError("Upload ainda não possui texto extraído", status_code=409)
        text = upload.extracted_text
        source = {"upload_id": str(upload.id)}
    else:
        text = payload.text or ""
        source = {"text_chars": str(len(text))}

    try:
        result = await MinutaAssistant(provider).review_text(text=text)
    except LLMProviderError as exc:
        raise AppError(str(exc), status_code=503) from exc
    await _audit(
        session,
        action="ai.review",
        user=user,
        meta=meta,
        started=started,
        extra={"provider": result.provider, "model": result.model, **source},
    )
    return AIResponse(provider=result.provider, model=result.model, content=result.content)
