from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log_action(
        self,
        *,
        action: str,
        user_id: UUID | None,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        extra: dict | None = None,
        duration_ms: int | None = None,
    ) -> None:
        row = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            extra=extra,
            duration_ms=duration_ms,
        )
        self._session.add(row)
        await self._session.flush()

    async def count_for_user(self, user_id: UUID) -> int:
        stmt = select(func.count()).select_from(AuditLog).where(AuditLog.user_id == user_id)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def search(
        self,
        *,
        action: str | None = None,
        user_id: UUID | None = None,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
        since: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditLog], int]:
        filters = []
        if action:
            # Prefixo: "minuta." traz todas as ações de minuta
            filters.append(AuditLog.action.startswith(action))
        if user_id:
            filters.append(AuditLog.user_id == user_id)
        if resource_type:
            filters.append(AuditLog.resource_type == resource_type)
        if resource_id:
            filters.append(AuditLog.resource_id == resource_id)
        if since:
            filters.append(AuditLog.created_at >= since)

        total = await self._session.scalar(
            select(func.count()).select_from(AuditLog).where(*filters)
        )
        stmt = (
            select(AuditLog)
            .where(*filters)
            .order_by(AuditLog.created_at.desc(), AuditLog.id)
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), int(total or 0)
