"""Dados de demonstração (idempotente): usuários admin/editor/viewer e um template de contrato.

Uso: `python -m app.scripts.seed`  (o Compose roda automaticamente com SEED_DEMO_DATA=true).
NÃO use em produção — as senhas são públicas no README.
"""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import get_session_factory, reset_engine
from app.models.document import DocumentTemplate
from app.models.user import UserRole
from app.repositories.document_repository import TemplateRepository
from app.repositories.user_repository import UserRepository
from app.services.template_engine import validate_template

DEMO_USERS = [
    ("admin@minutas.dev", "Admin@12345", "Administradora Demo", UserRole.ADMIN),
    ("editor@minutas.dev", "Editor@12345", "Editor Demo", UserRole.EDITOR),
    ("viewer@minutas.dev", "Viewer@12345", "Leitor Demo", UserRole.VIEWER),
]

DEMO_TEMPLATE_NAME = "Contrato de Prestação de Serviços"
DEMO_TEMPLATE = """<h1>CONTRATO DE PRESTAÇÃO DE SERVIÇOS</h1>
<p><strong>CONTRATANTE:</strong> {{ contratante_nome }}, inscrito(a) no CPF/CNPJ sob o nº
{{ contratante_documento | documento }}.</p>
<p><strong>CONTRATADA:</strong> {{ contratada_nome }}, inscrita no CNPJ sob o nº
{{ contratada_documento | documento }}.</p>
<h2>CLÁUSULA 1ª — DO OBJETO</h2>
<p>{{ objeto }}</p>
<h2>CLÁUSULA 2ª — DO VALOR</h2>
<p>Pelos serviços, a CONTRATANTE pagará o valor total de {{ valor | moeda }},
{% if parcelas > 1 %}em {{ parcelas }} parcelas mensais{% else %}à vista{% endif %}.</p>
<h2>CLÁUSULA 3ª — DO PRAZO</h2>
<p>Este contrato vigora de {{ data_inicio | data }} até {{ data_fim | data }}.</p>
<h2>CLÁUSULA 4ª — DO FORO</h2>
<p>Fica eleito o foro da comarca de {{ foro }} para dirimir quaisquer dúvidas.</p>
<p>{{ foro }}, {{ hoje() }}.</p>
"""


async def seed() -> None:
    factory = get_session_factory(get_settings())
    async with factory() as session:
        users = UserRepository(session)
        admin = None
        for email, password, name, role in DEMO_USERS:
            user = await users.get_by_email(email)
            if user is None:
                user = await users.create(
                    email=email,
                    hashed_password=hash_password(password),
                    full_name=name,
                    role=role,
                )
                print(f"  usuário criado: {email} ({role.value})")
            if role == UserRole.ADMIN:
                admin = user

        templates = TemplateRepository(session)
        if await templates.get_by_name(DEMO_TEMPLATE_NAME) is None:
            await templates.add(
                DocumentTemplate(
                    name=DEMO_TEMPLATE_NAME,
                    description="Modelo de demonstração com filtros moeda/data/documento.",
                    category="contratos",
                    content=DEMO_TEMPLATE,
                    variables=validate_template(DEMO_TEMPLATE),
                    version=1,
                    is_active=True,
                    created_by_id=admin.id if admin else None,
                )
            )
            print(f"  template criado: {DEMO_TEMPLATE_NAME}")
        await session.commit()
    await reset_engine()


def main() -> None:
    print("Seed de dados de demonstração...")
    asyncio.run(seed())
    print("Seed concluído.")


if __name__ == "__main__":
    main()
