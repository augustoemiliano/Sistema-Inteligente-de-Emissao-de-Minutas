from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user, require_roles
from app.api.dependencies.context import Pagination, RequestMeta, get_pagination, get_request_meta
from app.api.dependencies.db import get_db
from app.core.config import get_settings
from app.core.exceptions import AppError, NotFoundError
from app.models.document import MinutaStatus, PdfStatus
from app.models.user import User, UserRole
from app.repositories.audit_repository import AuditRepository
from app.schemas.documents import (
    MinutaCreate,
    MinutaDetailResponse,
    MinutaResponse,
    MinutaStatusChange,
    MinutaUpdate,
    MinutaVersionResponse,
    Page,
    PdfJobResponse,
)
from app.services.minuta_service import MinutaService
from app.services.storage import safe_join

router = APIRouter(prefix="/minutas", tags=["minutas"])

editor_or_admin = require_roles(UserRole.EDITOR, UserRole.ADMIN)


async def _detail(service: MinutaService, minuta) -> MinutaDetailResponse:
    latest = await service.latest_version(minuta)
    return MinutaDetailResponse.model_validate(
        {**MinutaResponse.model_validate(minuta).model_dump(), "latest": latest},
    )


def _download_url(minuta_id: UUID, version: int) -> str:
    prefix = get_settings().api_v1_prefix
    return f"{prefix}/minutas/{minuta_id}/versions/{version}/pdf"


@router.get("", response_model=Page[MinutaResponse])
async def list_minutas(
    status_filter: MinutaStatus | None = Query(default=None, alias="status"),
    template_id: UUID | None = None,
    mine: bool = False,
    page: Pagination = Depends(get_pagination),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    items, total = await MinutaService(session).paginate(
        status=status_filter,
        template_id=template_id,
        created_by_id=user.id if mine else None,
        limit=page.limit,
        offset=page.offset,
    )
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.post("", response_model=MinutaDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_minuta(
    payload: MinutaCreate,
    user: User = Depends(editor_or_admin),
    meta: RequestMeta = Depends(get_request_meta),
    session: AsyncSession = Depends(get_db),
):
    service = MinutaService(session)
    minuta = await service.create(payload, user, meta)
    return await _detail(service, minuta)


@router.get("/{minuta_id}", response_model=MinutaDetailResponse)
async def get_minuta(
    minuta_id: UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = MinutaService(session)
    return await _detail(service, await service.get(minuta_id))


@router.put("/{minuta_id}", response_model=MinutaDetailResponse)
async def update_minuta(
    minuta_id: UUID,
    payload: MinutaUpdate,
    user: User = Depends(editor_or_admin),
    meta: RequestMeta = Depends(get_request_meta),
    session: AsyncSession = Depends(get_db),
):
    service = MinutaService(session)
    minuta = await service.update(minuta_id, payload, user, meta)
    return await _detail(service, minuta)


@router.post("/{minuta_id}/status", response_model=MinutaResponse)
async def change_status(
    minuta_id: UUID,
    payload: MinutaStatusChange,
    user: User = Depends(editor_or_admin),
    meta: RequestMeta = Depends(get_request_meta),
    session: AsyncSession = Depends(get_db),
):
    return await MinutaService(session).change_status(minuta_id, payload, user, meta)


@router.get("/{minuta_id}/versions", response_model=list[MinutaVersionResponse])
async def list_versions(
    minuta_id: UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await MinutaService(session).list_versions(minuta_id)


@router.get("/{minuta_id}/versions/{version}", response_model=MinutaVersionResponse)
async def get_version(
    minuta_id: UUID,
    version: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await MinutaService(session).get_version(minuta_id, version)


@router.post(
    "/{minuta_id}/pdf",
    response_model=PdfJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enfileira a geração do PDF (versão atual ou ?version=N)",
)
async def request_pdf(
    minuta_id: UUID,
    version: int | None = Query(default=None, ge=1),
    user: User = Depends(editor_or_admin),
    meta: RequestMeta = Depends(get_request_meta),
    session: AsyncSession = Depends(get_db),
):
    row, task_id = await MinutaService(session).request_pdf(minuta_id, version, user, meta)
    body = PdfJobResponse(
        minuta_id=minuta_id,
        version=row.version,
        pdf_status=row.pdf_status,
        task_id=task_id,
        download_url=(
            _download_url(minuta_id, row.version) if row.pdf_status == PdfStatus.READY else None
        ),
        error=row.pdf_error,
    )
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=body.model_dump(mode="json"))


@router.get("/{minuta_id}/versions/{version}/pdf", response_class=FileResponse)
async def download_pdf(
    minuta_id: UUID,
    version: int,
    user: User = Depends(get_current_user),
    meta: RequestMeta = Depends(get_request_meta),
    session: AsyncSession = Depends(get_db),
):
    service = MinutaService(session)
    minuta = await service.get(minuta_id)
    row = await service.get_version(minuta_id, version)
    if row.pdf_status != PdfStatus.READY or not row.pdf_path:
        raise AppError(f"PDF não disponível (status: {row.pdf_status.value})", status_code=409)

    path = safe_join(get_settings().generated_documents_dir, row.pdf_path)
    if not path.is_file():
        raise NotFoundError("Arquivo do PDF não encontrado no armazenamento")

    await AuditRepository(session).log_action(
        action="minuta.pdf_download",
        user_id=user.id,
        resource_type="minuta",
        resource_id=minuta.id,
        ip_address=meta.ip_address,
        user_agent=meta.user_agent,
        extra={"version": version},
    )
    await session.commit()
    filename = f"minuta-{str(minuta.id)[:8]}-v{version}.pdf"
    return FileResponse(path, media_type="application/pdf", filename=filename)
