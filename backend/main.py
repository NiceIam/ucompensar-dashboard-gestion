from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.auth import limiter
from app.config import get_settings
from app.database import init_main_db, close_all_pools, get_main_pool
from app.routers import health as health_router
from app.routers import (
    analytics,
    auth_router,
    agents,
    chat,
    dashboards,
    etl,
    files,
    templates,
    schema,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    try:
        await init_main_db()
        pool = await get_main_pool()
        count = await pool.fetchval("SELECT count(*) FROM organizations")
        logger.info(
            "PostgreSQL connected. Organizations: %s, Environment: %s",
            count,
            settings.APP_ENV,
        )
    except Exception as exc:
        logger.warning("Failed to connect to PostgreSQL: %s", exc)
    yield
    await close_all_pools()
    logger.info("Backend shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()

    _is_dev = settings.APP_ENV != "production"
    app = FastAPI(
        title="PI0320251 — Plataforma SaaS para PYMES",
        description=(
            "API para la gestion estrategica de datos con IA. "
            "Desarrollada por el semillero Data Core Tech — Fundacion Universitaria Ucompensar."
        ),
        version="0.1.0",
        docs_url="/docs" if _is_dev else None,
        redoc_url="/redoc" if _is_dev else None,
        openapi_url="/openapi.json" if _is_dev else None,
        lifespan=lifespan,
    )

    # Rate limiting (slowapi)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins_list(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    )

    # Routers
    app.include_router(health_router.router)
    app.include_router(auth_router.router)
    app.include_router(files.router)
    app.include_router(agents.router)
    app.include_router(dashboards.router)
    app.include_router(chat.router)
    app.include_router(templates.router)
    app.include_router(etl.router)
    app.include_router(analytics.router)
    app.include_router(schema.router)

    return app


app = create_app()
