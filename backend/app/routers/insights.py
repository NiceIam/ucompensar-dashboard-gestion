"""Endpoint de hallazgos de negocio ("Esta semana en tu negocio") — PI0320251.

Solo lectura y SIN IA: no pasa por Gemini ni consume la cuota de mensajes del chat (`reserve_user_message`).
Todo se calcula de forma exacta con el motor de consultas sobre los datos de la organizacion del JWT.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi.util import get_remote_address

from app.auth import CurrentUser, CurrentUserDep, limiter
from app.models.schemas import InsightsResponse
from app.services.business_insights_service import InsightsUnavailable, get_business_insights

router = APIRouter(prefix="/api/v1/insights", tags=["Insights"])

# Cada llamada lee las tablas de la org (unas pocas consultas): 30 por minuto por usuario es de sobra para un
# panel que se abre y se refresca, y protege la BD de un cliente que insista en recargar.
INSIGHTS_RATE_LIMIT = "30/minute"


def _rate_limit_key(request: Request) -> str:
    return getattr(request.state, "rate_limit_key", None) or get_remote_address(request)


async def _rate_limited_user(request: Request, current_user: CurrentUserDep) -> CurrentUser:
    """CurrentUser + su identidad como clave del limiter. Las peticiones sin sesion (401) no consumen cupo."""
    request.state.rate_limit_key = f"insights-user:{current_user.user_id}"
    return current_user


@router.get(
    "",
    response_model=InsightsResponse,
    status_code=status.HTTP_200_OK,
    summary="Hallazgos de plata de la semana, calculados de forma exacta (sin IA)",
)
@limiter.limit(INSIGHTS_RATE_LIMIT, key_func=_rate_limit_key)
async def get_insights(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(_rate_limited_user)],
) -> InsightsResponse:
    try:
        data = await get_business_insights(current_user.org_id)
    except InsightsUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return InsightsResponse.model_validate(data)
