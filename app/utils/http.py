from __future__ import annotations

from fastapi import Request


def client_ip(request: Request) -> str | None:
    # TODO: confiar em X-Forwarded-For só atrás de proxy reverso conhecido
    if request.client:
        return request.client.host
    return None
