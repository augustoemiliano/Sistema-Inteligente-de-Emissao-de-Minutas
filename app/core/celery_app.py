"""Celery — filas para PDF, OCR e jobs pesados (ETAPA 5 expande as tasks)."""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings


def make_celery() -> Celery:
    settings = get_settings()
    app = Celery(
        "minutas",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        broker_connection_retry_on_startup=True,
    )
    return app


celery_app = make_celery()


@celery_app.task(name="health.ping")
def ping() -> str:
    return "pong"
