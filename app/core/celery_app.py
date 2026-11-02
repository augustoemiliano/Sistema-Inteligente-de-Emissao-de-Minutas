"""Celery — filas para geração de PDF e OCR de uploads."""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings


def make_celery() -> Celery:
    settings = get_settings()
    app = Celery(
        "minutas",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=["app.tasks.documents"],
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        broker_connection_retry_on_startup=True,
        # Eager: executa no próprio processo (dev sem Redis e testes automatizados)
        task_always_eager=settings.celery_task_always_eager,
        task_store_eager_result=False,
        worker_prefetch_multiplier=1,
        result_expires=3600,
    )
    return app


celery_app = make_celery()


@celery_app.task(name="health.ping")
def ping() -> str:
    return "pong"
