from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.services.pdf_service import html_to_pdf
from app.services.storage import UnsafePathError, safe_join
from app.services.upload_service import sanitize_filename

API = "/api/v1"
PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00"
    b"\x00\x00IEND\xaeB`\x82"
)


def _text_pdf() -> bytes:
    pdf, _ = html_to_pdf(
        "<h1>Contrato antigo</h1><p>As partes acordam o pagamento de R$ 2.000,00 mensais.</p>",
        title="teste",
    )
    return pdf


def test_pdf_upload_extracts_embedded_text(client: TestClient, editor_headers) -> None:
    response = client.post(
        f"{API}/uploads",
        files={"file": ("contrato.pdf", _text_pdf(), "application/pdf")},
        headers=editor_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "done"
    assert body["extraction_method"] == "pdf_text"
    assert "pagamento" in body["extracted_text"]
    assert len(body["sha256"]) == 64


def test_filename_with_traversal_is_neutralized(client: TestClient, editor_headers) -> None:
    response = client.post(
        f"{API}/uploads",
        files={"file": ("../../etc/passwd.pdf", _text_pdf(), "application/pdf")},
        headers=editor_headers,
    )
    assert response.status_code == 201
    assert response.json()["original_filename"] == "passwd.pdf"
    upload_dir = get_settings().upload_dir.resolve()
    stored = list(upload_dir.iterdir())
    assert len(stored) == 1 and stored[0].suffix == ".pdf"


def test_type_is_checked_by_content_not_extension(client: TestClient, editor_headers) -> None:
    response = client.post(
        f"{API}/uploads",
        files={"file": ("malware.pdf", b"MZ\x90\x00 executavel", "application/pdf")},
        headers=editor_headers,
    )
    assert response.status_code == 415


def test_upload_size_limit(client: TestClient, editor_headers) -> None:
    big = b"%PDF-" + b"0" * (1024 * 1024 + 10)  # MAX_UPLOAD_SIZE_MB=1 nos testes
    response = client.post(
        f"{API}/uploads",
        files={"file": ("grande.pdf", io.BytesIO(big), "application/pdf")},
        headers=editor_headers,
    )
    assert response.status_code == 413


def test_image_without_tesseract_fails_gracefully(
    client: TestClient, editor_headers, monkeypatch
) -> None:
    import app.services.ocr_service as ocr

    monkeypatch.setattr(ocr, "tesseract_available", lambda settings=None: False)
    response = client.post(
        f"{API}/uploads", files={"file": ("foto.png", PNG_1PX, "image/png")}, headers=editor_headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "failed"
    assert "Tesseract" in body["error"]


def test_image_ocr_with_tesseract(client: TestClient, editor_headers, monkeypatch) -> None:
    import app.services.ocr_service as ocr

    monkeypatch.setattr(ocr, "tesseract_available", lambda settings=None: True)
    monkeypatch.setattr(ocr, "_ocr_image", lambda image, settings: "texto reconhecido")
    body = client.post(
        f"{API}/uploads", files={"file": ("doc.png", PNG_1PX, "image/png")}, headers=editor_headers
    ).json()
    assert body["status"] == "done"
    assert body["extraction_method"] == "ocr"
    assert body["extracted_text"] == "texto reconhecido"


def test_uploads_are_private_to_owner(
    client: TestClient, editor_headers, viewer_headers, admin_headers
) -> None:
    upload_id = client.post(
        f"{API}/uploads",
        files={"file": ("c.pdf", _text_pdf(), "application/pdf")},
        headers=editor_headers,
    ).json()["id"]
    assert client.get(f"{API}/uploads/{upload_id}", headers=viewer_headers).status_code == 403
    assert client.get(f"{API}/uploads/{upload_id}", headers=admin_headers).status_code == 200
    assert client.get(f"{API}/uploads", headers=viewer_headers).json()["total"] == 0


def test_viewer_cannot_upload(client: TestClient, viewer_headers) -> None:
    response = client.post(
        f"{API}/uploads",
        files={"file": ("c.pdf", b"%PDF-1.4", "application/pdf")},
        headers=viewer_headers,
    )
    assert response.status_code == 403


@pytest.mark.parametrize("name", ["../fora.pdf", "..\\fora.pdf", "/etc/passwd", "a/../../b", ""])
def test_safe_join_rejects_traversal(tmp_path: Path, name: str) -> None:
    with pytest.raises(UnsafePathError):
        safe_join(tmp_path, name)


def test_safe_join_accepts_nested_relative(tmp_path: Path) -> None:
    assert safe_join(tmp_path, "abc/v1.pdf") == (tmp_path / "abc" / "v1.pdf").resolve()


def test_sanitize_filename() -> None:
    assert sanitize_filename("C:\\Users\\x\\contrato final.pdf") == "contrato final.pdf"
    assert sanitize_filename("nome\x00com\ncontrole.pdf") == "nomecomcontrole.pdf"
    assert sanitize_filename("..") == "arquivo"
    assert sanitize_filename(None) == "arquivo"
