from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.context import RequestMeta
from app.core.exceptions import ConflictError, NotFoundError
from app.models.document import DocumentTemplate
from app.models.user import User
from app.repositories.audit_repository import AuditRepository
from app.repositories.document_repository import TemplateRepository
from app.schemas.documents import TemplateCreate, TemplatePreviewResponse, TemplateUpdate
from app.services.template_engine import missing_variables, render_template, validate_template


class TemplateService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = TemplateRepository(session)
        self._audit = AuditRepository(session)

    async def get(self, template_id: UUID) -> DocumentTemplate:
        template = await self._repo.get(template_id)
        if template is None:
            raise NotFoundError("Template não encontrado")
        return template

    async def paginate(self, *, category: str | None, active_only: bool, limit: int, offset: int):
        return await self._repo.paginate(
            category=category, active_only=active_only, limit=limit, offset=offset
        )

    async def create(
        self, payload: TemplateCreate, user: User, meta: RequestMeta
    ) -> DocumentTemplate:
        if await self._repo.get_by_name(payload.name) is not None:
            raise ConflictError("Já existe um template com este nome")
        variables = validate_template(payload.content)
        template = await self._repo.add(
            DocumentTemplate(
                name=payload.name.strip(),
                description=payload.description,
                category=payload.category,
                content=payload.content,
                variables=variables,
                version=1,
                is_active=True,
                created_by_id=user.id,
            )
        )
        await self._audit.log_action(
            action="template.create",
            user_id=user.id,
            resource_type="template",
            resource_id=template.id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            extra={"name": template.name, "variables": variables},
        )
        await self._session.commit()
        return template

    async def update(
        self, template_id: UUID, payload: TemplateUpdate, user: User, meta: RequestMeta
    ) -> DocumentTemplate:
        template = await self.get(template_id)
        changes = payload.model_dump(exclude_unset=True)

        if "name" in changes and changes["name"].lower() != template.name.lower():
            if await self._repo.get_by_name(changes["name"]) is not None:
                raise ConflictError("Já existe um template com este nome")
        if "content" in changes and changes["content"] != template.content:
            template.variables = validate_template(changes["content"])
            # Mudança de conteúdo = nova versão do template; minutas guardam a versão usada
            template.version += 1

        for field, value in changes.items():
            setattr(template, field, value)

        await self._audit.log_action(
            action="template.update",
            user_id=user.id,
            resource_type="template",
            resource_id=template.id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            extra={"fields": sorted(changes), "version": template.version},
        )
        await self._session.commit()
        await self._session.refresh(template)
        return template

    async def delete(self, template_id: UUID, user: User, meta: RequestMeta) -> None:
        template = await self.get(template_id)
        if await self._repo.count_minutas(template.id) > 0:
            raise ConflictError("Template possui minutas vinculadas — desative-o em vez de excluir")
        await self._audit.log_action(
            action="template.delete",
            user_id=user.id,
            resource_type="template",
            resource_id=template.id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            extra={"name": template.name},
        )
        await self._repo.delete(template)
        await self._session.commit()

    async def preview(
        self, template_id: UUID, variables: dict[str, Any]
    ) -> TemplatePreviewResponse:
        template = await self.get(template_id)
        missing = missing_variables(template.variables, variables)
        # Variáveis ausentes viram marcadores visíveis — útil para montar o formulário
        filled = {**{name: f"[[{name}]]" for name in missing}, **variables}
        return TemplatePreviewResponse(
            html=render_template(template.content, filled),
            missing_variables=missing,
        )
