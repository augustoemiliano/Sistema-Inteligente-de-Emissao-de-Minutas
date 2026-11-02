from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.template_engine import (
    TemplateRenderError,
    render_template,
    validate_template,
)

API = "/api/v1"


def test_validate_extracts_variables_ignoring_globals() -> None:
    assert validate_template("{{ b }} {{ a | moeda }} {{ hoje() }}") == ["a", "b"]


def test_filters_brazilian_format() -> None:
    out = render_template(
        "{{ v | moeda }}|{{ d | data }}|{{ cpf | documento }}|{{ cnpj | documento }}",
        {"v": 1234567.891, "d": "2026-03-09", "cpf": "12345678901", "cnpj": "12345678000199"},
    )
    assert out == "R$ 1.234.567,89|09/03/2026|123.456.789-01|12.345.678/0001-99"


def test_autoescape_prevents_html_injection() -> None:
    out = render_template("<p>{{ nome }}</p>", {"nome": "<script>alert(1)</script>"})
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


@pytest.mark.parametrize(
    "payload",
    [
        "{{ ''.__class__.__mro__[1].__subclasses__() }}",
        "{{ cycler.__init__.__globals__.os.popen('id').read() }}",
    ],
)
def test_sandbox_blocks_ssti(payload: str) -> None:
    with pytest.raises(TemplateRenderError):
        render_template(payload, {})


def test_missing_variable_is_explicit_error() -> None:
    with pytest.raises(TemplateRenderError):
        render_template("{{ ausente }}", {})


def test_invalid_syntax_rejected() -> None:
    with pytest.raises(TemplateRenderError):
        validate_template("{% if %}")


def test_create_template_extracts_variables(client: TestClient, editor_headers) -> None:
    response = client.post(
        f"{API}/templates",
        json={"name": "Procuração", "content": "<p>{{ outorgante }} nomeia {{ outorgado }}</p>"},
        headers=editor_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["variables"] == ["outorgado", "outorgante"]
    assert body["version"] == 1


def test_viewer_cannot_create_template(client: TestClient, viewer_headers) -> None:
    response = client.post(
        f"{API}/templates", json={"name": "X template", "content": "oi"}, headers=viewer_headers
    )
    assert response.status_code == 403


def test_invalid_template_returns_422(client: TestClient, editor_headers) -> None:
    response = client.post(
        f"{API}/templates",
        json={"name": "Quebrado", "content": "{% for %}"},
        headers=editor_headers,
    )
    assert response.status_code == 422


def test_duplicate_name_conflict(client: TestClient, editor_headers, template_id) -> None:
    response = client.post(
        f"{API}/templates",
        json={"name": "contrato teste", "content": "x"},
        headers=editor_headers,
    )
    assert response.status_code == 409


def test_update_content_bumps_version(client: TestClient, editor_headers, template_id) -> None:
    response = client.patch(
        f"{API}/templates/{template_id}",
        json={"content": "<p>{{ novo_campo }}</p>"},
        headers=editor_headers,
    )
    assert response.status_code == 200
    assert response.json()["version"] == 2
    assert response.json()["variables"] == ["novo_campo"]


def test_preview_marks_missing_variables(client: TestClient, viewer_headers, template_id) -> None:
    response = client.post(
        f"{API}/templates/{template_id}/preview",
        json={"variables": {"contratante": "Ana"}},
        headers=viewer_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert "Ana" in body["html"]
    assert set(body["missing_variables"]) == {"documento", "valor", "inicio"}


def test_delete_template_with_minutas_is_blocked(
    client: TestClient, admin_headers, template_id, minuta_id
) -> None:
    response = client.delete(f"{API}/templates/{template_id}", headers=admin_headers)
    assert response.status_code == 409


def test_delete_template_requires_admin(
    client: TestClient, admin_headers, editor_headers, template_id
) -> None:
    assert (
        client.delete(f"{API}/templates/{template_id}", headers=editor_headers).status_code == 403
    )
    assert client.delete(f"{API}/templates/{template_id}", headers=admin_headers).status_code == 204
    assert client.get(f"{API}/templates/{template_id}", headers=admin_headers).status_code == 404
