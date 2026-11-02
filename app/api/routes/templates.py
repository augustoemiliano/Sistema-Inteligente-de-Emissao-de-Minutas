from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user, require_roles
from app.api.dependencies.context import Pagination, RequestMeta, get_pagination, get_request_meta
from app.api.dependencies.db import get_db
from app.models.user import User, UserRole
from app.schemas.documents import (
    Page,
    TemplateCreate,
    TemplatePreviewRequest,
    TemplatePreviewResponse,
    TemplateResponse,
    TemplateUpdate,
)
from app.services.template_service import TemplateService

router = APIRouter(prefix="/templates", tags=["templates"])

editor_or_admin = require_roles(UserRole.EDITOR, UserRole.ADMIN)


@router.get("", response_model=Page[TemplateResponse])
async def list_templates(
    category: str | None = Query(default=None, max_length=100),
    active_only: bool = True,
    page: Pagination = Depends(get_pagination),
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    items, total = await TemplateService(session).paginate(
        category=category, active_only=active_only, limit=page.limit, offset=page.offset
    )
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: TemplateCreate,
    user: User = Depends(editor_or_admin),
    meta: RequestMeta = Depends(get_request_meta),
    session: AsyncSession = Depends(get_db),
):
    return await TemplateService(session).create(payload, user, meta)


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await TemplateService(session).get(template_id)


@router.patch("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: UUID,
    payload: TemplateUpdate,
    user: User = Depends(editor_or_admin),
    meta: RequestMeta = Depends(get_request_meta),
    session: AsyncSession = Depends(get_db),
):
    return await TemplateService(session).update(template_id, payload, user, meta)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    user: User = Depends(require_roles(UserRole.ADMIN)),
    meta: RequestMeta = Depends(get_request_meta),
    session: AsyncSession = Depends(get_db),
) -> Response:
    await TemplateService(session).delete(template_id, user, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{template_id}/preview", response_model=TemplatePreviewResponse)
async def preview_template(
    template_id: UUID,
    payload: TemplatePreviewRequest,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await TemplateService(session).preview(template_id, payload.variables)
