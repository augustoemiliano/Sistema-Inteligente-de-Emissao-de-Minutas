from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, user_id: UUID, token_hash: str) -> RefreshToken:
        settings = get_settings()
        expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        row = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get_valid_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > func.now(),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke(self, token_id: UUID) -> None:
        stmt = select(RefreshToken).where(RefreshToken.id == token_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return
        row.revoked_at = datetime.now(UTC)
        await self._session.flush()

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        result = await self._session.execute(stmt)
        now = datetime.now(UTC)
        for row in result.scalars():
            row.revoked_at = now
        await self._session.flush()
