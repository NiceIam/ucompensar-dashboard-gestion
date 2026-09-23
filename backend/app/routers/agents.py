from typing import List

from fastapi import APIRouter, status

from app.auth import CurrentUserDep
from app.models.schemas import AgentResultDetail, AgentSessionResponse
from app.services.agent_service import get_session_results, list_sessions, run_pipeline

router = APIRouter(prefix="/api/v1/agents", tags=["Agents"])


@router.post(
    "/analyze/{file_id}",
    response_model=AgentSessionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Dispara el pipeline de agentes IA para un archivo",
)
async def analyze_file(file_id: str, current_user: CurrentUserDep) -> AgentSessionResponse:
    """El pipeline se ejecuta en background. Usa GET /sessions/{session_id} para seguir el estado."""
    return await run_pipeline(file_id, current_user.org_id, current_user.user_id)


@router.get(
    "/sessions",
    response_model=List[AgentSessionResponse],
    summary="Lista sesiones de agentes de la organización",
)
async def get_sessions(current_user: CurrentUserDep) -> List[AgentSessionResponse]:
    return await list_sessions(current_user.org_id)


@router.get(
    "/sessions/{session_id}",
    response_model=AgentResultDetail,
    summary="Detalle de sesión con resultados del pipeline",
)
async def get_session(session_id: str, current_user: CurrentUserDep) -> AgentResultDetail:
    return await get_session_results(session_id, current_user.org_id)
