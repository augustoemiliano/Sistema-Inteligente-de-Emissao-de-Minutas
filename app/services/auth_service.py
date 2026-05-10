from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import (
    create_access_token,
    generate_refresh_token_value,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.user import User, UserRole
from app.repositories.audit_repository import AuditRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import RegisterRequest, TokenPairResponse, UserResponse


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._refresh = RefreshTokenRepository(session)
        self._audit = AuditRepository(session)

    async def register(
        self,
        payload: RegisterRequest,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> TokenPairResponse:
        started = time.monotonic()
        if await self._users.get_by_email(payload.email) is not None:
            raise ConflictError("E-mail já cadastrado")

        total = await self._users.count_active()
        role = UserRole.ADMIN if total == 0 else UserRole.VIEWER

        user = await self._users.create(
            email=payload.email,
            hashed_password=hash_password(payload.password),
            full_name=payload.full_name,
            role=role,
        )
        refresh_raw = generate_refresh_token_value()
        refresh_h = hash_refresh_token(refresh_raw)
        await self._refresh.create(user_id=user.id, token_hash=refresh_h)

        access = create_access_token(
            user.id,
            extra_claims={"role": user.role.value},
        )
        settings = get_settings()
        expires_in = settings.access_token_expire_minutes * 60

        await self._audit.log_action(
            action="auth.register",
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        await self._session.commit()

        return TokenPairResponse(
            access_token=access,
            refresh_token=refresh_raw,
            expires_in=expires_in,
        )

    async def login(
        self,
        email: str,
        password: str,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> TokenPairResponse:
        started = time.monotonic()
        user = await self._users.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            await self._audit.log_action(
                action="auth.login_failed",
                user_id=None,
                ip_address=ip_address,
                user_agent=user_agent,
                extra={"email": email},
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            await self._session.commit()
            raise UnauthorizedError("Credenciais inválidas")

        if not user.is_active:
            raise UnauthorizedError("Usuário inativo")

        refresh_raw = generate_refresh_token_value()
        await self._refresh.create(user_id=user.id, token_hash=hash_refresh_token(refresh_raw))

        access = create_access_token(user.id, extra_claims={"role": user.role.value})
        settings = get_settings()

        await self._audit.log_action(
            action="auth.login",
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        await self._session.commit()

        return TokenPairResponse(
            access_token=access,
            refresh_token=refresh_raw,
            expires_in=settings.access_token_expire_minutes * 60,
        )

    async def refresh(
        self,
        refresh_token: str,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> TokenPairResponse:
        started = time.monotonic()
        token_hash = hash_refresh_token(refresh_token)
        row = await self._refresh.get_valid_by_hash(token_hash)
        if row is None:
            await self._audit.log_action(
                action="auth.refresh_invalid",
                user_id=None,
                ip_address=ip_address,
                user_agent=user_agent,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            await self._session.commit()
            raise UnauthorizedError("Refresh inválido ou expirado")

        user = await self._users.get_by_id(row.user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("Usuário inválido")

        await self._refresh.revoke(row.id)
        new_raw = generate_refresh_token_value()
        await self._refresh.create(user_id=user.id, token_hash=hash_refresh_token(new_raw))

        access = create_access_token(user.id, extra_claims={"role": user.role.value})
        settings = get_settings()

        await self._audit.log_action(
            action="auth.refresh",
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        await self._session.commit()

        return TokenPairResponse(
            access_token=access,
            refresh_token=new_raw,
            expires_in=settings.access_token_expire_minutes * 60,
        )

    async def me(self, user: User) -> UserResponse:
        return UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role.value,
            is_active=user.is_active,
        )
