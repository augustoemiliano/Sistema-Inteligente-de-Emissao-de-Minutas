from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.db import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Autenticação necessária")
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = UUID(payload["sub"])
    except (ValueError, KeyError) as exc:
        raise UnauthorizedError("Token inválido") from exc

    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise UnauthorizedError("Usuário não encontrado")
    if not user.is_active:
        raise UnauthorizedError("Usuário inativo")
    token_role = payload.get("role")
    if token_role != user.role.value:
        # Papel mudou no banco — token antigo não reflete mais o perfil efetivo
        raise UnauthorizedError("Sessão expirada — faça login novamente")
    return user


def require_roles(*roles: UserRole):
    allowed = set(roles)

    async def checker(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed:
            raise ForbiddenError("Permissão insuficiente para este recurso")
        return user

    return checker
