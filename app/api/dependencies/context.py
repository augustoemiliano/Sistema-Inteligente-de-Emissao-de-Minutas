from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query, Request

from app.utils.http import client_ip


@dataclass(slots=True, frozen=True)
class RequestMeta:
    """Dados do request que vão para a trilha de auditoria."""

    ip_address: str | None
    user_agent: str | None


def get_request_meta(request: Request) -> RequestMeta:
    ua = request.headers.get("user-agent")
    return RequestMeta(ip_address=client_ip(request), user_agent=ua[:500] if ua else None)


@dataclass(slots=True, frozen=True)
class Pagination:
    limit: int
    offset: int


def get_pagination(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Pagination:
    return Pagination(limit=limit, offset=offset)
