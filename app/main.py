"""Aplicação ASGI — composição de middlewares, rotas e tratamento de erros."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import auth, health
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logger import RequestContextMiddleware, configure_logging, get_logger
from app.db.session import get_engine, get_session_factory

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    get_engine(settings)
    get_session_factory(settings)
    for path in (
        settings.upload_dir,
        settings.generated_documents_dir,
        settings.log_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)
    logger.info("Serviço iniciado (%s)", settings.environment)
    yield
    logger.info("Serviço encerrando")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        lifespan=lifespan,
        title=settings.project_name,
        version="0.1.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
    )

    app.add_middleware(RequestContextMiddleware)

    if settings.cors_origins:
        allow_credentials = True
        allow_origins = settings.cors_origins
    else:
        # Dev sem .env: CORS aberto sem credenciais (* + cookies falha no browser).
        allow_credentials = False
        allow_origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def app_error_handler(_, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_, exc: RequestValidationError):
        # Mantém payload do FastAPI, mas padroniza chave `detail`
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_, exc: Exception):
        logger.exception("Erro não tratado: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Erro interno — time notificado pelo correlation id"},
        )

    app.include_router(health.router, prefix=settings.api_v1_prefix)
    app.include_router(auth.router, prefix=settings.api_v1_prefix)

    if not settings.is_production:
        playground_dir = Path(__file__).resolve().parent.parent / "playground"
        if playground_dir.is_dir():
            app.mount(
                "/playground",
                StaticFiles(directory=str(playground_dir), html=True),
                name="playground",
            )

    return app


app = create_app()
