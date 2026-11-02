"""Logging estruturado — JSON em produção, legível em dev."""

from __future__ import annotations

import logging
import re
import sys
import time
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from typing import Any

import orjson
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import Settings, get_settings

_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return _request_id.get()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = get_request_id()
        if rid:
            payload["request_id"] = rid
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return orjson.dumps(payload).decode("utf-8")


def configure_logging(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    root = logging.getLogger()
    for old in list(root.handlers):
        root.removeHandler(old)
        old.close()
    root.setLevel(logging.DEBUG if not settings.is_production else logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    if settings.is_production:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))

    root.addHandler(handler)

    # Arquivo rotativo em LOG_DIR (sempre JSON — pronto para ingestão por coletor de logs)
    try:
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            settings.log_dir / "app.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(JsonFormatter())
        file_handler.setLevel(logging.INFO)
        root.addHandler(file_handler)
    except OSError:
        root.warning("Não foi possível abrir arquivo de log em %s", settings.log_dir)

    for noisy in ("sqlalchemy.engine", "aiosqlite", "multipart", "httpcore", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Propaga request_id para logs e cabeçalho de resposta (rastreio corporativo)."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        rid = request.headers.get("X-Request-ID")
        # Valor vem do cliente: aceita só formato seguro para não poluir/forjar logs
        if not rid or not _SAFE_REQUEST_ID.fullmatch(rid):
            rid = str(time.time_ns())
        token = _request_id.set(rid)
        try:
            response: Response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            _request_id.reset(token)
