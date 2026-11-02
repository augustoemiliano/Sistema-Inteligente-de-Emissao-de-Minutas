from __future__ import annotations

from fastapi.testclient import TestClient

API = "/api/v1"


def _register(client: TestClient, email: str, password: str = "SenhaForte123") -> dict:
    response = client.post(
        f"{API}/auth/register",
        json={"email": email, "password": password, "full_name": "Fulano de Tal"},
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def _bearer(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_first_user_is_admin_and_next_is_viewer(client: TestClient) -> None:
    first = _register(client, "primeiro@test.dev")
    second = _register(client, "segundo@test.dev")

    assert client.get(f"{API}/auth/me", headers=_bearer(first)).json()["role"] == "admin"
    assert client.get(f"{API}/auth/me", headers=_bearer(second)).json()["role"] == "viewer"
    assert client.get(f"{API}/auth/admin/ping", headers=_bearer(first)).status_code == 200
    assert client.get(f"{API}/auth/admin/ping", headers=_bearer(second)).status_code == 403


def test_register_duplicate_email_is_conflict(client: TestClient) -> None:
    _register(client, "dup@test.dev")
    response = client.post(
        f"{API}/auth/register",
        json={"email": "DUP@test.dev", "password": "SenhaForte123", "full_name": "Outro"},
    )
    assert response.status_code == 409


def test_login_success_and_failure(client: TestClient) -> None:
    _register(client, "login@test.dev")
    ok = client.post(
        f"{API}/auth/login", json={"email": "login@test.dev", "password": "SenhaForte123"}
    )
    assert ok.status_code == 200
    assert ok.json()["token_type"] == "bearer"

    wrong = client.post(f"{API}/auth/login", json={"email": "login@test.dev", "password": "errada"})
    unknown = client.post(f"{API}/auth/login", json={"email": "nao@test.dev", "password": "x"})
    # Mesma resposta para senha errada e e-mail inexistente (sem enumeração de usuários)
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_refresh_rotates_and_old_token_is_revoked(client: TestClient) -> None:
    tokens = _register(client, "refresh@test.dev")
    rotated = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != tokens["refresh_token"]

    reused = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reused.status_code == 401


def test_logout_revokes_refresh_token(client: TestClient) -> None:
    tokens = _register(client, "logout@test.dev")
    response = client.post(
        f"{API}/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers=_bearer(tokens),
    )
    assert response.status_code == 204
    again = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert again.status_code == 401


def test_protected_route_rejects_missing_or_invalid_token(client: TestClient) -> None:
    assert client.get(f"{API}/auth/me").status_code == 401
    bad = client.get(f"{API}/auth/me", headers={"Authorization": "Bearer nao-e-um-jwt"})
    assert bad.status_code == 401


def test_token_with_stale_role_is_rejected(
    client: TestClient, admin_headers, viewer_headers
) -> None:
    viewer_id = viewer_headers["X-User-Id"]
    promoted = client.patch(
        f"{API}/users/{viewer_id}", json={"role": "editor"}, headers=admin_headers
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "editor"
    # Token emitido quando ainda era viewer não vale mais
    assert client.get(f"{API}/auth/me", headers=viewer_headers).status_code == 401


def test_admin_cannot_change_own_role(client: TestClient, admin_headers) -> None:
    response = client.patch(
        f"{API}/users/{admin_headers['X-User-Id']}", json={"role": "viewer"}, headers=admin_headers
    )
    assert response.status_code == 409


def test_users_list_requires_admin(client: TestClient, admin_headers, editor_headers) -> None:
    assert client.get(f"{API}/users", headers=editor_headers).status_code == 403
    listing = client.get(f"{API}/users", headers=admin_headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 2
