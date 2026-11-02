from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import (
    DocumentTemplate,
    DocumentUpload,
    Minuta,
    MinutaStatus,
    MinutaVersion,
)


class TemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, template_id: UUID) -> DocumentTemplate | None:
        return await self._session.get(DocumentTemplate, template_id)

    async def get_by_name(self, name: str) -> DocumentTemplate | None:
        stmt = select(DocumentTemplate).where(func.lower(DocumentTemplate.name) == name.lower())
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def paginate(
        self, *, category: str | None, active_only: bool, limit: int, offset: int
    ) -> tuple[list[DocumentTemplate], int]:
        filters = []
        if category:
            filters.append(DocumentTemplate.category == category)
        if active_only:
            filters.append(DocumentTemplate.is_active.is_(True))
        total = await self._session.scalar(
            select(func.count()).select_from(DocumentTemplate).where(*filters)
        )
        stmt = (
            select(DocumentTemplate)
            .where(*filters)
            .order_by(DocumentTemplate.name)
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), int(total or 0)

    async def add(self, template: DocumentTemplate) -> DocumentTemplate:
        self._session.add(template)
        await self._session.flush()
        await self._session.refresh(template)
        return template

    async def count_minutas(self, template_id: UUID) -> int:
        stmt = select(func.count()).select_from(Minuta).where(Minuta.template_id == template_id)
        return int(await self._session.scalar(stmt) or 0)

    async def delete(self, template: DocumentTemplate) -> None:
        await self._session.delete(template)
        await self._session.flush()


class MinutaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, minuta_id: UUID) -> Minuta | None:
        return await self._session.get(Minuta, minuta_id)

    async def paginate(
        self,
        *,
        status: MinutaStatus | None,
        template_id: UUID | None,
        created_by_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Minuta], int]:
        filters = []
        if status:
            filters.append(Minuta.status == status)
        if template_id:
            filters.append(Minuta.template_id == template_id)
        if created_by_id:
            filters.append(Minuta.created_by_id == created_by_id)
        total = await self._session.scalar(select(func.count()).select_from(Minuta).where(*filters))
        stmt = (
            select(Minuta)
            .where(*filters)
            .order_by(Minuta.updated_at.desc(), Minuta.id)
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), int(total or 0)

    async def add(self, minuta: Minuta) -> Minuta:
        self._session.add(minuta)
        await self._session.flush()
        return minuta

    async def add_version(self, version: MinutaVersion) -> MinutaVersion:
        self._session.add(version)
        await self._session.flush()
        await self._session.refresh(version)
        return version

    async def get_version(self, minuta_id: UUID, version: int) -> MinutaVersion | None:
        stmt = select(MinutaVersion).where(
            MinutaVersion.minuta_id == minuta_id, MinutaVersion.version == version
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_versions(self, minuta_id: UUID) -> list[MinutaVersion]:
        stmt = (
            select(MinutaVersion)
            .where(MinutaVersion.minuta_id == minuta_id)
            .order_by(MinutaVersion.version.desc())
        )
        return list((await self._session.execute(stmt)).scalars().all())


class UploadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, upload_id: UUID) -> DocumentUpload | None:
        return await self._session.get(DocumentUpload, upload_id)

    async def add(self, upload: DocumentUpload) -> DocumentUpload:
        self._session.add(upload)
        await self._session.flush()
        await self._session.refresh(upload)
        return upload

    async def paginate(
        self, *, created_by_id: UUID | None, limit: int, offset: int
    ) -> tuple[list[DocumentUpload], int]:
        filters = []
        if created_by_id:
            filters.append(DocumentUpload.created_by_id == created_by_id)
        total = await self._session.scalar(
            select(func.count()).select_from(DocumentUpload).where(*filters)
        )
        stmt = (
            select(DocumentUpload)
            .where(*filters)
            .order_by(DocumentUpload.created_at.desc(), DocumentUpload.id)
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), int(total or 0)
