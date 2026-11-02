"""Motor Jinja2 em sandbox para templates cadastrados por usuários.

Templates são conteúdo de usuário (editores), então:
- `SandboxedEnvironment` bloqueia acesso a atributos internos (SSTI → RCE);
- `autoescape=True` escapa valores das variáveis (evita injeção de HTML no PDF);
- `StrictUndefined` faz variável ausente virar erro explícito em vez de texto vazio.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateError,
    meta,
    select_autoescape,
)
from jinja2.sandbox import SandboxedEnvironment
from markupsafe import Markup

from app.core.exceptions import AppError

MAX_TEMPLATE_SIZE = 200_000
_LAYOUT_DIR = Path(__file__).resolve().parent.parent / "templates"


class TemplateRenderError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422)


def _fmt_moeda(value: Any) -> str:
    """Formata número no padrão brasileiro: 1234.5 -> 'R$ 1.234,50'."""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    formatted = f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def _fmt_data(value: Any) -> str:
    if isinstance(value, datetime | date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10]).strftime("%d/%m/%Y")
        except ValueError:
            return value
    return str(value)


def _fmt_documento(value: Any) -> str:
    """Formata CPF (11 dígitos) ou CNPJ (14 dígitos); outros valores ficam como estão."""
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    if len(digits) == 14:
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
    return str(value)


def _build_env() -> SandboxedEnvironment:
    env = SandboxedEnvironment(
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["moeda"] = _fmt_moeda
    env.filters["data"] = _fmt_data
    env.filters["documento"] = _fmt_documento
    env.globals["hoje"] = lambda: date.today().strftime("%d/%m/%Y")
    return env


_env = _build_env()

# Layout HTML do PDF: arquivo versionado no repositório (não é conteúdo de usuário).
_layout_env = Environment(
    loader=FileSystemLoader(str(_LAYOUT_DIR)),
    autoescape=select_autoescape(["html"]),
)


def validate_template(content: str) -> list[str]:
    """Valida sintaxe e retorna as variáveis de topo usadas no template (ordenadas)."""
    if len(content) > MAX_TEMPLATE_SIZE:
        raise TemplateRenderError("Template excede o tamanho máximo permitido")
    try:
        ast = _env.parse(content)
    except TemplateError as exc:
        raise TemplateRenderError(f"Template inválido: {exc}") from exc
    names = meta.find_undeclared_variables(ast)
    return sorted(n for n in names if n not in _env.globals)


def render_template(content: str, variables: dict[str, Any]) -> str:
    try:
        return _env.from_string(content).render(**variables)
    except TemplateError as exc:
        # Inclui UndefinedError (variável ausente) e SecurityError (sandbox)
        raise TemplateRenderError(f"Falha ao renderizar template: {exc}") from exc


def missing_variables(required: list[str], variables: dict[str, Any]) -> list[str]:
    return [name for name in required if name not in variables]


def render_document_html(*, title: str, body_html: str, version: int) -> str:
    """Envolve o corpo já renderizado (e escapado) no layout de impressão."""
    layout = _layout_env.get_template("document_base.html")
    return layout.render(title=title, body=Markup(body_html), version=version)
