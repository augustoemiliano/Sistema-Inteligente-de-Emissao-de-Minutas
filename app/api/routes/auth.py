from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user, require_roles
from app.api.dependencies.db import get_db
from app.core.exceptions import ConflictError, UnauthorizedError
from app.models.user import User, UserRole
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPairResponse,
    UserResponse,
)
from app.services.auth_service import AuthService
from app.utils.http import client_ip

router = APIRouter(prefix="/auth", tags=["auth"])


def _auth_service(session: AsyncSession) -> AuthService:
    return AuthService(session)


@router.post(
    "/register",
    response_model=TokenPairResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    request: Request,
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_db),
) -> TokenPairResponse:
    try:
        return await _auth_service(session).register(
            payload,
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except ConflictError:
        await session.rollback()
        raise


@router.post("/login", response_model=TokenPairResponse)
async def login(
    request: Request,
    payload: LoginRequest,
    session: AsyncSession = Depends(get_db),
) -> TokenPairResponse:
    try:
        return await _auth_service(session).login(
            email=str(payload.email),
            password=payload.password,
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except UnauthorizedError:
        await session.rollback()
        raise


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh_token(
    request: Request,
    payload: RefreshRequest,
    session: AsyncSession = Depends(get_db),
) -> TokenPairResponse:
    try:
        return await _auth_service(session).refresh(
            payload.refresh_token,
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except UnauthorizedError:
        await session.rollback()
        raise


@router.get("/me", response_model=UserResponse)
async def me(
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    return await _auth_service(session).me(current)


@router.get("/admin/ping", tags=["admin"])
async def admin_ping(
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> dict[str, str]:
    # Smoke interno: RBAC sem espalhar lógica nas rotas de negócio
    return {"status": "ok"}
