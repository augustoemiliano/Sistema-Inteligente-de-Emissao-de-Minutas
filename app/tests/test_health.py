from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready_checks_database(client: TestClient) -> None:
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ok", "redis": "skipped"}


def test_ready_reports_degraded(client: TestClient, monkeypatch) -> None:
    import app.api.routes.health as health

    async def down() -> bool:
        return False

    monkeypatch.setattr(health, "check_database", down)
    response = client.get("/api/v1/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_request_id_is_propagated_and_sanitized(client: TestClient) -> None:
    ok = client.get("/api/v1/health", headers={"X-Request-ID": "abc-123"})
    assert ok.headers["X-Request-ID"] == "abc-123"
    forged = client.get("/api/v1/health", headers={"X-Request-ID": 'x" injected=1'})
    assert forged.headers["X-Request-ID"] != 'x" injected=1'


def test_insecure_secret_rejected_in_production() -> None:
    import pytest
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            secret_key="change-me-use-openssl-rand-hex-32",
            DATABASE_URL="sqlite+aiosqlite://",
            DATABASE_URL_SYNC="sqlite://",
        )
