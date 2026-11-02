from __future__ import annotations

from fastapi.testclient import TestClient

from app.tests.conftest import SAMPLE_VARIABLES

API = "/api/v1"


def test_create_minuta_renders_first_version(client: TestClient, editor_headers, minuta_id) -> None:
    response = client.get(f"{API}/minutas/{minuta_id}", headers=editor_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "draft"
    assert body["current_version"] == 1
    html = body["latest"]["rendered_content"]
    assert "Maria Silva" in html
    assert "123.456.789-01" in html
    assert "R$ 1.500,50" in html
    assert "15/01/2026" in html


def test_create_minuta_with_missing_variables_is_422(
    client: TestClient, editor_headers, template_id
) -> None:
    response = client.post(
        f"{API}/minutas",
        json={"title": "Incompleta", "template_id": template_id, "variables": {"contratante": "X"}},
        headers=editor_headers,
    )
    assert response.status_code == 422
    assert "documento" in response.json()["detail"]


def test_viewer_can_read_but_not_create(
    client: TestClient, viewer_headers, template_id, minuta_id
) -> None:
    assert client.get(f"{API}/minutas/{minuta_id}", headers=viewer_headers).status_code == 200
    response = client.post(
        f"{API}/minutas",
        json={"title": "Sem permissão", "template_id": template_id, "variables": SAMPLE_VARIABLES},
        headers=viewer_headers,
    )
    assert response.status_code == 403


def test_update_creates_new_immutable_version(
    client: TestClient, editor_headers, minuta_id
) -> None:
    changed = {**SAMPLE_VARIABLES, "contratante": "João Souza"}
    response = client.put(
        f"{API}/minutas/{minuta_id}",
        json={"variables": changed, "change_note": "Troca de contratante"},
        headers=editor_headers,
    )
    assert response.status_code == 200
    assert response.json()["current_version"] == 2

    versions = client.get(f"{API}/minutas/{minuta_id}/versions", headers=editor_headers).json()
    assert [v["version"] for v in versions] == [2, 1]
    assert "João Souza" in versions[0]["rendered_content"]
    assert "Maria Silva" in versions[1]["rendered_content"]


def test_approval_workflow_and_rbac(
    client: TestClient, editor_headers, admin_headers, minuta_id
) -> None:
    status_url = f"{API}/minutas/{minuta_id}/status"

    submit = client.post(status_url, json={"status": "in_review"}, headers=editor_headers)
    assert submit.status_code == 200
    assert submit.json()["status"] == "in_review"

    # Editor não aprova
    assert (
        client.post(status_url, json={"status": "approved"}, headers=editor_headers).status_code
        == 403
    )
    # Minuta em revisão não pode ser editada
    edit = client.put(
        f"{API}/minutas/{minuta_id}", json={"variables": SAMPLE_VARIABLES}, headers=editor_headers
    )
    assert edit.status_code == 409

    approve = client.post(
        status_url, json={"status": "approved", "comment": "ok jurídico"}, headers=admin_headers
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    # Transição inexistente
    back = client.post(status_url, json={"status": "draft"}, headers=admin_headers)
    assert back.status_code == 409


def test_pdf_generation_and_download(client: TestClient, editor_headers, minuta_id) -> None:
    job = client.post(f"{API}/minutas/{minuta_id}/pdf", headers=editor_headers)
    assert job.status_code == 202, job.text
    body = job.json()
    # Celery em modo eager nos testes: a task já executou
    assert body["pdf_status"] == "ready"
    assert body["download_url"].endswith(f"/minutas/{minuta_id}/versions/1/pdf")

    pdf = client.get(body["download_url"], headers=editor_headers)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


def test_download_before_generation_is_conflict(
    client: TestClient, editor_headers, minuta_id
) -> None:
    response = client.get(f"{API}/minutas/{minuta_id}/versions/1/pdf", headers=editor_headers)
    assert response.status_code == 409


def test_pdf_for_unknown_version_is_404(client: TestClient, editor_headers, minuta_id) -> None:
    response = client.post(f"{API}/minutas/{minuta_id}/pdf?version=9", headers=editor_headers)
    assert response.status_code == 404


def test_pdf_failure_is_recorded(
    client: TestClient, editor_headers, minuta_id, monkeypatch
) -> None:
    import app.tasks.documents as tasks

    def boom(*_args, **_kwargs):
        raise RuntimeError("motor quebrado")

    monkeypatch.setattr(tasks, "html_to_pdf", boom)
    body = client.post(f"{API}/minutas/{minuta_id}/pdf", headers=editor_headers).json()
    assert body["pdf_status"] == "failed"
    assert "motor quebrado" in body["error"]


def test_list_minutas_filters(client: TestClient, editor_headers, minuta_id) -> None:
    all_items = client.get(f"{API}/minutas", headers=editor_headers).json()
    assert all_items["total"] == 1
    drafts = client.get(f"{API}/minutas?status=draft", headers=editor_headers).json()
    assert drafts["total"] == 1
    approved = client.get(f"{API}/minutas?status=approved", headers=editor_headers).json()
    assert approved["total"] == 0
