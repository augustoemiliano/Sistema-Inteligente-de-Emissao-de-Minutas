from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_roles
from app.api.dependencies.context import Pagination, RequestMeta, get_pagination, get_request_meta
from app.api.dependencies.db import get_db
from app.core.exceptions import ConflictError, NotFoundError
from app.models.user import User, UserRole
from app.repositories.audit_repository import AuditRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import UserResponse
from app.schemas.documents import Page
from app.schemas.users import UserAdminUpdate

router = APIRouter(prefix="/users", tags=["usuários (admin)"])
admin_only = require_roles(UserRole.ADMIN)


def _to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        is_active=user.is_active,
    )


@router.get("", response_model=Page[UserResponse])
async def list_users(
    page: Pagination = Depends(get_pagination),
    _: User = Depends(admin_only),
    session: AsyncSession = Depends(get_db),
):
    base = select(User).where(User.deleted_at.is_(None))
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = (
        await session.execute(base.order_by(User.email).limit(page.limit).offset(page.offset))
    ).scalars()
    return Page(
        items=[_to_response(u) for u in rows],
        total=int(total or 0),
        limit=page.limit,
        offset=page.offset,
    )


@router.patch("/{user_id}", response_model=UserResponse, summary="Altera papel/ativação")
async def update_user(
    user_id: UUID,
    payload: UserAdminUpdate,
    admin: User = Depends(admin_only),
    meta: RequestMeta = Depends(get_request_meta),
    session: AsyncSession = Depends(get_db),
):
    target = await UserRepository(session).get_by_id(user_id)
    if target is None:
        raise NotFoundError("Usuário não encontrado")
    if target.id == admin.id:
        # Evita o admin se trancar para fora (rebaixar/desativar a si mesmo)
        raise ConflictError("Admin não pode alterar o próprio papel ou status")

    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "role" in changes:
        target.role = changes["role"]
    if "is_active" in changes:
        target.is_active = changes["is_active"]
    if changes:
        # Papel/ativação mudou: força novo login (tokens antigos carregam o papel anterior)
        await RefreshTokenRepository(session).revoke_all_for_user(target.id)

    await AuditRepository(session).log_action(
        action="user.update",
        user_id=admin.id,
        resource_type="user",
        resource_id=target.id,
        ip_address=meta.ip_address,
        user_agent=meta.user_agent,
        extra={k: (v.value if isinstance(v, UserRole) else v) for k, v in changes.items()},
    )
    await session.commit()
    return _to_response(target)
