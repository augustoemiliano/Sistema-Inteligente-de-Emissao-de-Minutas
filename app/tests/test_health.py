from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_ok() -> None:
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
