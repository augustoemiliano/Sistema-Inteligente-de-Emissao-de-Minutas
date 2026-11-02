"""Infra de testes: SQLite em arquivo temporário, Celery eager e IA fake.

Para rodar contra PostgreSQL (como no CI), defina TEST_DATABASE_URL e TEST_DATABASE_URL_SYNC.
As variáveis precisam existir ANTES de importar `app` — por isso ficam no topo do módulo.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="minutas-tests-"))

os.environ.update(
    {
        "ENVIRONMENT": "development",
        "SECRET_KEY": "test-secret-key-at-least-32-characters-long!",
        "DATABASE_URL": os.environ.get(
            "TEST_DATABASE_URL", f"sqlite+aiosqlite:///{(_TMP / 'test.db').as_posix()}"
        ),
        "DATABASE_URL_SYNC": os.environ.get(
            "TEST_DATABASE_URL_SYNC", f"sqlite:///{(_TMP / 'test.db').as_posix()}"
        ),
        "DATABASE_NULLPOOL": "true",
        "CELERY_TASK_ALWAYS_EAGER": "true",
        "CELERY_BROKER_URL": "memory://",
        "CELERY_RESULT_BACKEND": "cache+memory://",
        "AI_PROVIDER": "fake",
        "OPENAI_API_KEY": "",
        "PDF_ENGINE": "reportlab",
        "CORS_ORIGINS": "",
        "UPLOAD_DIR": str(_TMP / "uploads"),
        "GENERATED_DOCUMENTS_DIR": str(_TMP / "generated"),
        "LOG_DIR": str(_TMP / "logs"),
        "MAX_UPLOAD_SIZE_MB": "1",
        "BCRYPT_ROUNDS": "4",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_database() -> Iterator[None]:
    """Schema recriado a cada teste — isolamento total, sem ordem implícita entre casos."""
    import app.models  # noqa: F401 — registra metadados
    from app.db.base import Base
    from app.db.session import get_sync_engine

    engine = get_sync_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    for folder in ("uploads", "generated"):
        shutil.rmtree(_TMP / folder, ignore_errors=True)


@pytest.fixture
def client() -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as c:
        yield c


def _create_user(email: str, role: str) -> dict[str, str]:
    from app.core.security import create_access_token, hash_password
    from app.db.session import get_sync_session_factory
    from app.models.user import User, UserRole

    with get_sync_session_factory()() as session:
        user = User(
            email=email,
            hashed_password=hash_password("SenhaForte123"),
            full_name=email.split("@")[0].title(),
            role=UserRole(role),
        )
        session.add(user)
        session.commit()
        token = create_access_token(user.id, extra_claims={"role": role})
        return {"Authorization": f"Bearer {token}", "X-User-Id": str(user.id)}


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return _create_user("admin@test.dev", "admin")


@pytest.fixture
def editor_headers() -> dict[str, str]:
    return _create_user("editor@test.dev", "editor")


@pytest.fixture
def viewer_headers() -> dict[str, str]:
    return _create_user("viewer@test.dev", "viewer")


SAMPLE_TEMPLATE = (
    "<h1>Contrato</h1>"
    "<p>Contratante: {{ contratante }}, documento {{ documento | documento }}.</p>"
    "<p>Valor: {{ valor | moeda }} — início em {{ inicio | data }}.</p>"
)

SAMPLE_VARIABLES = {
    "contratante": "Maria Silva",
    "documento": "12345678901",
    "valor": 1500.5,
    "inicio": "2026-01-15",
}


@pytest.fixture
def template_id(client: TestClient, editor_headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/templates",
        json={"name": "Contrato Teste", "category": "contratos", "content": SAMPLE_TEMPLATE},
        headers=editor_headers,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


@pytest.fixture
def minuta_id(client: TestClient, editor_headers: dict[str, str], template_id: str) -> str:
    response = client.post(
        "/api/v1/minutas",
        json={"title": "Minuta Teste", "template_id": template_id, "variables": SAMPLE_VARIABLES},
        headers=editor_headers,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])
