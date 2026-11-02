from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_roles
from app.api.dependencies.context import Pagination, get_pagination
from app.api.dependencies.db import get_db
from app.models.user import User, UserRole
from app.repositories.audit_repository import AuditRepository
from app.schemas.documents import AuditLogResponse, Page

router = APIRouter(prefix="/audit", tags=["auditoria"])


@router.get("", response_model=Page[AuditLogResponse], summary="Trilha de auditoria (admin)")
async def list_audit_logs(
    action: str | None = Query(default=None, max_length=128, description="Prefixo, ex.: minuta."),
    user_id: UUID | None = None,
    resource_type: str | None = Query(default=None, max_length=64),
    resource_id: UUID | None = None,
    since: datetime | None = None,
    page: Pagination = Depends(get_pagination),
    _: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_db),
):
    items, total = await AuditRepository(session).search(
        action=action,
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        since=since,
        limit=page.limit,
        offset=page.offset,
    )
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)
