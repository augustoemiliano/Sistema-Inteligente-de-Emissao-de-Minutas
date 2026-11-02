"""Sessões — engine async para a API e engine síncrono para workers Celery."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_sync_engine: Engine | None = None
_sync_session_factory: sessionmaker[Session] | None = None


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = settings or get_settings()
        kwargs: dict = {"pool_pre_ping": True, "echo": False}
        if settings.database_nullpool:
            kwargs["poolclass"] = NullPool
        _engine = create_async_engine(settings.database_url, **kwargs)
    return _engine


def get_session_factory(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        engine = get_engine(settings)
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


def get_sync_engine(settings: Settings | None = None) -> Engine:
    global _sync_engine
    if _sync_engine is None:
        settings = settings or get_settings()
        _sync_engine = create_engine(settings.database_url_sync, pool_pre_ping=True)
    return _sync_engine


def get_sync_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    """Usado pelas tasks Celery (workers são síncronos)."""
    global _sync_session_factory
    if _sync_session_factory is None:
        _sync_session_factory = sessionmaker(get_sync_engine(settings), expire_on_commit=False)
    return _sync_session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def reset_engine() -> None:
    """Útil em testes para não vazar conexões entre casos."""
    global _engine, _session_factory, _sync_engine, _sync_session_factory
    if _engine is not None:
        await _engine.dispose()
    if _sync_engine is not None:
        _sync_engine.dispose()
    _engine = None
    _session_factory = None
    _sync_engine = None
    _sync_session_factory = None
