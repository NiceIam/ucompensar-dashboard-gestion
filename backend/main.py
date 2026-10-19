from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
    insights,
    templates,
    schema,
)

logger = logging.getLogger(__name__)


def _on_rate_limit_exceeded(request: Request, exc: RateLimitExceeded):
    """429 de slowapi. En /api/v1/chat usa la misma estructura de `detail` que el tope por cuota
    (code/message/retry_after_seconds), para que el frontend no tenga que distinguirlos; el resto
    de rutas (auth) conserva el cuerpo por defecto de slowapi."""
    if not request.url.path.startswith("/api/v1/chat/"):
        return _rate_limit_exceeded_handler(request, exc)
    retry_after = max(1, int(exc.limit.limit.get_expiry()))  # ventana completa: cota superior del tiempo de espera
    retry_at = datetime.now(timezone.utc) + timedelta(seconds=retry_after)
    return JSONResponse(
        {
            "detail": {
                "code": "rate_limit_user",
                "message": f"Estás enviando mensajes muy rápido. Intenta de nuevo en {retry_after} segundos.",
                "retry_after_seconds": retry_after,
                "retry_at": retry_at.isoformat(),
            }
        },
        status_code=429,
        headers={"Retry-After": str(retry_after)},
    )


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
    app.add_exception_handler(RateLimitExceeded, _on_rate_limit_exceeded)

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
    app.include_router(insights.router)
    app.include_router(templates.router)
    app.include_router(etl.router)
    app.include_router(analytics.router)
    app.include_router(schema.router)

    return app


app = create_app()
