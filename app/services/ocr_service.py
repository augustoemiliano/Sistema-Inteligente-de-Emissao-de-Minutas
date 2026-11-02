"""Extração de texto de uploads: texto embutido do PDF (pdfplumber) e OCR (Tesseract).

Estratégia:
1. PDF com camada de texto → pdfplumber (rápido, sem dependência de sistema).
2. PDF escaneado (sem texto) ou imagem → Tesseract, se instalado.
3. Sem Tesseract → falha explícita e descritiva (o restante do sistema continua funcionando).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings, get_settings

# Abaixo disso consideramos que o PDF é escaneado e vale tentar OCR
MIN_TEXT_CHARS = 20
MAX_OCR_PAGES = 30


class OcrUnavailableError(RuntimeError):
    pass


@dataclass(slots=True)
class ExtractionResult:
    text: str
    method: str  # "pdf_text" | "ocr"


def tesseract_available(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return shutil.which(settings.tesseract_cmd or "tesseract") is not None


def _ocr_image(image, settings: Settings) -> str:
    import pytesseract

    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
    return str(pytesseract.image_to_string(image, lang=settings.ocr_language))


def _require_ocr(settings: Settings) -> None:
    if not tesseract_available(settings):
        raise OcrUnavailableError(
            "OCR indisponível: instale o Tesseract (incluído na imagem Docker) "
            "ou configure TESSERACT_CMD"
        )


def extract_text(
    path: Path, content_type: str, settings: Settings | None = None
) -> ExtractionResult:
    settings = settings or get_settings()

    if content_type == "application/pdf":
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            text = "\n\n".join((page.extract_text() or "") for page in pdf.pages).strip()
            if len(text) >= MIN_TEXT_CHARS:
                return ExtractionResult(text=text, method="pdf_text")
            _require_ocr(settings)
            pages = []
            for page in pdf.pages[:MAX_OCR_PAGES]:
                image = page.to_image(resolution=200).original
                pages.append(_ocr_image(image, settings))
            return ExtractionResult(text="\n\n".join(pages).strip(), method="ocr")

    from PIL import Image

    _require_ocr(settings)
    with Image.open(path) as image:
        return ExtractionResult(text=_ocr_image(image, settings).strip(), method="ocr")
