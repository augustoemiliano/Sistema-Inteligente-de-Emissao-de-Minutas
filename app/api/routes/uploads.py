from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user, require_roles
from app.api.dependencies.context import Pagination, RequestMeta, get_pagination, get_request_meta
from app.api.dependencies.db import get_db
from app.core.exceptions import ForbiddenError
from app.models.user import User, UserRole
from app.schemas.documents import Page, UploadResponse
from app.services.upload_service import UploadService

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post(
    "",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Envia PDF/imagem para extração de texto (pdfplumber + OCR Tesseract)",
)
async def create_upload(
    file: UploadFile = File(...),
    user: User = Depends(require_roles(UserRole.EDITOR, UserRole.ADMIN)),
    meta: RequestMeta = Depends(get_request_meta),
    session: AsyncSession = Depends(get_db),
):
    return await UploadService(session).create(file, user, meta)


@router.get("", response_model=Page[UploadResponse])
async def list_uploads(
    page: Pagination = Depends(get_pagination),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    # Não-admin enxerga apenas os próprios uploads (podem conter dados pessoais)
    owner = None if user.role == UserRole.ADMIN else user.id
    items, total = await UploadService(session).paginate(
        created_by_id=owner, limit=page.limit, offset=page.offset
    )
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/{upload_id}", response_model=UploadResponse)
async def get_upload(
    upload_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    upload = await UploadService(session).get(upload_id)
    if user.role != UserRole.ADMIN and upload.created_by_id != user.id:
        raise ForbiddenError("Upload pertence a outro usuário")
    return upload
