from __future__ import annotations

from fastapi.testclient import TestClient

API = "/api/v1"


def test_full_flow_is_audited(client: TestClient, editor_headers, admin_headers, minuta_id) -> None:
    client.post(f"{API}/minutas/{minuta_id}/pdf", headers=editor_headers)
    client.get(f"{API}/minutas/{minuta_id}/versions/1/pdf", headers=editor_headers)

    response = client.get(f"{API}/audit?resource_id={minuta_id}", headers=admin_headers)
    assert response.status_code == 200
    actions = {item["action"] for item in response.json()["items"]}
    assert {
        "minuta.create",
        "minuta.pdf_requested",
        "minuta.pdf_generated",
        "minuta.pdf_download",
    } <= actions

    templates = client.get(f"{API}/audit?action=template.", headers=admin_headers).json()
    assert [i["action"] for i in templates["items"]] == ["template.create"]
    assert templates["items"][0]["user_id"] == editor_headers["X-User-Id"]


def test_failed_login_is_audited(client: TestClient, admin_headers) -> None:
    client.post(f"{API}/auth/login", json={"email": "x@test.dev", "password": "errada"})
    logs = client.get(f"{API}/audit?action=auth.login_failed", headers=admin_headers).json()
    assert logs["total"] == 1


def test_audit_is_admin_only(client: TestClient, editor_headers) -> None:
    assert client.get(f"{API}/audit", headers=editor_headers).status_code == 403


def test_audit_pagination(client: TestClient, admin_headers, minuta_id) -> None:
    page = client.get(f"{API}/audit?limit=1&offset=0", headers=admin_headers).json()
    assert page["limit"] == 1
    assert len(page["items"]) == 1
    assert page["total"] >= 2
