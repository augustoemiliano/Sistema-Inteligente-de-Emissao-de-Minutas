"""Ciclo de vida da minuta: criação, versionamento, workflow de aprovação e PDF."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.context import RequestMeta
from app.core.exceptions import AppError, ConflictError, ForbiddenError, NotFoundError
from app.core.logger import get_logger
from app.models.document import DocumentTemplate, Minuta, MinutaStatus, MinutaVersion, PdfStatus
from app.models.user import User, UserRole
from app.repositories.audit_repository import AuditRepository
from app.repositories.document_repository import MinutaRepository, TemplateRepository
from app.schemas.documents import MinutaCreate, MinutaStatusChange, MinutaUpdate
from app.services.template_engine import (
    TemplateRenderError,
    missing_variables,
    render_template,
)

logger = get_logger(__name__)

# (origem, destino) -> papéis autorizados
TRANSITIONS: dict[tuple[MinutaStatus, MinutaStatus], set[UserRole]] = {
    (MinutaStatus.DRAFT, MinutaStatus.IN_REVIEW): {UserRole.EDITOR, UserRole.ADMIN},
    (MinutaStatus.IN_REVIEW, MinutaStatus.DRAFT): {UserRole.ADMIN},
    (MinutaStatus.IN_REVIEW, MinutaStatus.APPROVED): {UserRole.ADMIN},
    (MinutaStatus.DRAFT, MinutaStatus.ARCHIVED): {UserRole.ADMIN},
    (MinutaStatus.APPROVED, MinutaStatus.ARCHIVED): {UserRole.ADMIN},
}


class MinutaService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = MinutaRepository(session)
        self._templates = TemplateRepository(session)
        self._audit = AuditRepository(session)

    async def get(self, minuta_id: UUID) -> Minuta:
        minuta = await self._repo.get(minuta_id)
        if minuta is None:
            raise NotFoundError("Minuta não encontrada")
        return minuta

    async def get_version(self, minuta_id: UUID, version: int) -> MinutaVersion:
        row = await self._repo.get_version(minuta_id, version)
        if row is None:
            raise NotFoundError("Versão não encontrada")
        return row

    async def latest_version(self, minuta: Minuta) -> MinutaVersion:
        return await self.get_version(minuta.id, minuta.current_version)

    async def paginate(self, **filters: Any):
        return await self._repo.paginate(**filters)

    async def list_versions(self, minuta_id: UUID) -> list[MinutaVersion]:
        await self.get(minuta_id)
        return await self._repo.list_versions(minuta_id)

    @staticmethod
    def _render(template: DocumentTemplate, variables: dict[str, Any]) -> str:
        missing = missing_variables(template.variables, variables)
        if missing:
            raise TemplateRenderError(f"Variáveis obrigatórias ausentes: {', '.join(missing)}")
        return render_template(template.content, variables)

    async def create(self, payload: MinutaCreate, user: User, meta: RequestMeta) -> Minuta:
        template = await self._templates.get(payload.template_id)
        if template is None:
            raise NotFoundError("Template não encontrado")
        if not template.is_active:
            raise ConflictError("Template inativo não pode gerar novas minutas")

        rendered = self._render(template, payload.variables)
        minuta = await self._repo.add(
            Minuta(
                title=payload.title,
                template_id=template.id,
                status=MinutaStatus.DRAFT,
                current_version=1,
                created_by_id=user.id,
            )
        )
        await self._repo.add_version(
            MinutaVersion(
                minuta_id=minuta.id,
                version=1,
                template_version=template.version,
                variables=payload.variables,
                rendered_content=rendered,
                change_note="Versão inicial",
                pdf_status=PdfStatus.NONE,
                created_by_id=user.id,
            )
        )
        await self._audit.log_action(
            action="minuta.create",
            user_id=user.id,
            resource_type="minuta",
            resource_id=minuta.id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            extra={"template_id": str(template.id), "template_version": template.version},
        )
        await self._session.commit()
        await self._session.refresh(minuta)
        return minuta

    async def update(
        self, minuta_id: UUID, payload: MinutaUpdate, user: User, meta: RequestMeta
    ) -> Minuta:
        minuta = await self.get(minuta_id)
        if minuta.status != MinutaStatus.DRAFT:
            raise ConflictError("Somente minutas em rascunho podem ser editadas")
        template = await self._templates.get(minuta.template_id)
        assert template is not None  # FK RESTRICT garante existência

        rendered = self._render(template, payload.variables)
        new_version = minuta.current_version + 1
        await self._repo.add_version(
            MinutaVersion(
                minuta_id=minuta.id,
                version=new_version,
                template_version=template.version,
                variables=payload.variables,
                rendered_content=rendered,
                change_note=payload.change_note,
                pdf_status=PdfStatus.NONE,
                created_by_id=user.id,
            )
        )
        minuta.current_version = new_version
        if payload.title:
            minuta.title = payload.title
        await self._audit.log_action(
            action="minuta.update",
            user_id=user.id,
            resource_type="minuta",
            resource_id=minuta.id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            extra={"version": new_version, "change_note": payload.change_note},
        )
        await self._session.commit()
        await self._session.refresh(minuta)
        return minuta

    async def change_status(
        self, minuta_id: UUID, payload: MinutaStatusChange, user: User, meta: RequestMeta
    ) -> Minuta:
        minuta = await self.get(minuta_id)
        source, target = minuta.status, payload.status
        allowed = TRANSITIONS.get((source, target))
        if allowed is None:
            raise ConflictError(f"Transição inválida: {source.value} → {target.value}")
        if user.role not in allowed:
            raise ForbiddenError("Seu perfil não pode executar esta transição")

        minuta.status = target
        await self._audit.log_action(
            action="minuta.status_change",
            user_id=user.id,
            resource_type="minuta",
            resource_id=minuta.id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            extra={
                "from": source.value,
                "to": target.value,
                "version": minuta.current_version,
                "comment": payload.comment,
            },
        )
        await self._session.commit()
        await self._session.refresh(minuta)
        return minuta

    async def request_pdf(
        self, minuta_id: UUID, version: int | None, user: User, meta: RequestMeta
    ) -> tuple[MinutaVersion, str | None]:
        """Marca a versão como pendente e enfileira a task Celery de geração do PDF."""
        from app.tasks.documents import generate_minuta_pdf

        minuta = await self.get(minuta_id)
        row = await self.get_version(minuta.id, version or minuta.current_version)
        if row.pdf_status == PdfStatus.PENDING:
            raise ConflictError("PDF desta versão já está sendo gerado")

        row.pdf_status = PdfStatus.PENDING
        row.pdf_error = None
        await self._audit.log_action(
            action="minuta.pdf_requested",
            user_id=user.id,
            resource_type="minuta",
            resource_id=minuta.id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
            extra={"version": row.version},
        )
        # Commit ANTES de enfileirar: o worker precisa enxergar o estado PENDING
        await self._session.commit()

        try:
            result = generate_minuta_pdf.delay(str(row.id), str(user.id))
        except Exception as exc:
            logger.exception("Falha ao enfileirar geração de PDF")
            row.pdf_status = PdfStatus.FAILED
            row.pdf_error = "Fila de processamento indisponível"
            await self._session.commit()
            raise AppError("Fila de processamento indisponível", status_code=503) from exc

        # Em modo eager a task já rodou em outra sessão — recarrega o estado
        await self._session.refresh(row)
        return row, result.id
