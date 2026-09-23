from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.database import get_main_pool

router = APIRouter(tags=["Health"])

APP_VERSION = "0.1.0"


@router.get("/api/health", summary="Liveness check")
async def health() -> dict:
    return {"status": "ok", "version": APP_VERSION}


@router.get("/api/health/detailed", summary="Readiness check — verifica dependencias externas")
async def health_detailed() -> JSONResponse:
    """Verifica conectividad a la BD principal PostgreSQL. Retorna 503 si falla."""
    checks: dict = {
        "status": "ok",
        "version": APP_VERSION,
        "dependencies": {},
    }
    overall_ok = True

    # Check PostgreSQL main pool
    try:
        pool = await get_main_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks["dependencies"]["postgresql_main"] = "ok"
    except Exception as exc:
        checks["dependencies"]["postgresql_main"] = f"error: {exc}"
        overall_ok = False

    if not overall_ok:
        checks["status"] = "degraded"
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=checks,
        )

    return JSONResponse(status_code=status.HTTP_200_OK, content=checks)
