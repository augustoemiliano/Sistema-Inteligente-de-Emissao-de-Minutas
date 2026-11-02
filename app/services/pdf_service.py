"""Geração de PDF a partir do HTML renderizado da minuta.

Dois motores:
- **wkhtmltopdf** (via pdfkit): fidelidade total ao HTML/CSS — usado no Docker.
- **ReportLab**: puro Python, sem dependência de sistema — fallback em dev/CI.
  Suporta o subconjunto de HTML usado em minutas (títulos, parágrafos, listas, ênfase).
"""

from __future__ import annotations

import io
import shutil
from html import escape
from html.parser import HTMLParser

from app.core.config import Settings, get_settings
from app.core.logger import get_logger

logger = get_logger(__name__)

_BLOCK_TAGS = {"h1", "h2", "h3", "h4", "p", "li", "div", "blockquote"}
_INLINE_MAP = {"b": "b", "strong": "b", "i": "i", "em": "i", "u": "u"}


class PdfGenerationError(RuntimeError):
    pass


class _HtmlToBlocks(HTMLParser):
    """Converte HTML simples em blocos (estilo, markup aceito pelo Paragraph do ReportLab)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str]] = []
        self._style = "p"
        self._buf: list[str] = []
        self._skip = 0  # dentro de <style>/<script>/<head>

    def _flush(self) -> None:
        text = "".join(self._buf).strip()
        if text:
            self.blocks.append((self._style, text))
        self._buf = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"style", "script", "head", "title"}:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self._flush()
            self._style = tag
        elif tag in _INLINE_MAP:
            self._buf.append(f"<{_INLINE_MAP[tag]}>")
        elif tag == "br":
            self._buf.append("<br/>")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"style", "script", "head", "title"}:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK_TAGS:
            self._flush()
            self._style = "p"
        elif tag in _INLINE_MAP:
            self._buf.append(f"</{_INLINE_MAP[tag]}>")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        # Texto vem desescapado do parser; reescapamos para o mini-markup do ReportLab
        # Preserva o espaço nas bordas (ex.: "<b>Nome:</b> Fulano")
        lead = " " if data[:1].isspace() else ""
        trail = " " if data[-1:].isspace() else ""
        self._buf.append(escape(lead + " ".join(data.split()) + trail))

    def close(self) -> None:
        super().close()
        self._flush()


def _render_with_reportlab(html: str, title: str) -> bytes:
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    parser = _HtmlToBlocks()
    parser.feed(html)
    parser.close()

    base = getSampleStyleSheet()
    styles = {
        "h1": ParagraphStyle("h1", parent=base["Heading1"], alignment=TA_CENTER, fontSize=15),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=12.5),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontSize=11.5),
        "p": ParagraphStyle("p", parent=base["BodyText"], alignment=TA_JUSTIFY, leading=15),
        "li": ParagraphStyle(
            "li", parent=base["BodyText"], leftIndent=0.8 * cm, bulletIndent=0.3 * cm
        ),
    }
    styles["h4"] = styles["h3"]
    styles["div"] = styles["blockquote"] = styles["p"]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=title,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2 * cm,
    )
    story = []
    for style_name, markup in parser.blocks:
        bullet = "•" if style_name == "li" else None
        story.append(Paragraph(markup, styles[style_name], bulletText=bullet))
        story.append(Spacer(1, 0.15 * cm))
    if not story:
        story.append(Paragraph("(documento vazio)", styles["p"]))
    doc.build(story)
    return buffer.getvalue()


def _wkhtmltopdf_binary(settings: Settings) -> str | None:
    if settings.wkhtmltopdf_path and shutil.which(settings.wkhtmltopdf_path):
        return settings.wkhtmltopdf_path
    return shutil.which("wkhtmltopdf")


def _render_with_wkhtmltopdf(html: str, binary: str) -> bytes:
    import pdfkit

    config = pdfkit.configuration(wkhtmltopdf=binary)
    options = {
        "encoding": "UTF-8",
        "page-size": "A4",
        "quiet": "",
        # Template é conteúdo de usuário: impede <img src="file:///etc/passwd"> e afins
        "disable-local-file-access": "",
        "disable-javascript": "",
    }
    result = pdfkit.from_string(html, False, configuration=config, options=options)
    if not isinstance(result, bytes):
        raise PdfGenerationError("wkhtmltopdf não retornou bytes")
    return result


def resolve_engine(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if settings.pdf_engine == "reportlab":
        return "reportlab"
    binary = _wkhtmltopdf_binary(settings)
    if settings.pdf_engine == "wkhtmltopdf" and binary is None:
        raise PdfGenerationError("PDF_ENGINE=wkhtmltopdf, mas o binário não foi encontrado")
    return "wkhtmltopdf" if binary else "reportlab"


def html_to_pdf(html: str, *, title: str, settings: Settings | None = None) -> tuple[bytes, str]:
    """Retorna (bytes do PDF, motor utilizado)."""
    settings = settings or get_settings()
    engine = resolve_engine(settings)
    try:
        if engine == "wkhtmltopdf":
            binary = _wkhtmltopdf_binary(settings)
            assert binary is not None
            return _render_with_wkhtmltopdf(html, binary), engine
        return _render_with_reportlab(html, title), engine
    except PdfGenerationError:
        raise
    except Exception as exc:  # noqa: BLE001 — erro de lib externa vira erro de domínio
        logger.exception("Falha ao gerar PDF com %s", engine)
        raise PdfGenerationError(f"Falha ao gerar PDF ({engine}): {exc}") from exc
