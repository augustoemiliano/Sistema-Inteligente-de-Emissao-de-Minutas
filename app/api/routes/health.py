from __future__ import annotations

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.logger import get_logger
from app.db.session import get_engine

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def check_database() -> bool:
    try:
        async with get_engine().connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=3)
        return True
    except Exception as exc:
        logger.warning("Readiness: banco indisponível (%s)", type(exc).__name__)
        return False


async def check_redis() -> bool:
    import redis.asyncio as aioredis

    client = aioredis.from_url(get_settings().redis_url, socket_connect_timeout=2)
    try:
        return bool(await asyncio.wait_for(client.ping(), timeout=3))
    except Exception as exc:
        logger.warning("Readiness: redis indisponível (%s)", type(exc).__name__)
        return False
    finally:
        await client.aclose()


@router.get("/ready")
async def ready() -> JSONResponse:
    settings = get_settings()
    checks: dict[str, str] = {"database": "ok" if await check_database() else "fail"}
    if settings.celery_task_always_eager:
        # Sem fila: tasks executam no próprio processo, Redis não é necessário
        checks["redis"] = "skipped"
    else:
        checks["redis"] = "ok" if await check_redis() else "fail"
    healthy = all(v != "fail" for v in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "degraded", "checks": checks},
    )
