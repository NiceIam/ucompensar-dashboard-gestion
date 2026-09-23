from fastapi import APIRouter, UploadFile, File, Form, status
from typing import Optional

from app.auth import CurrentUserDep
from app.models.schemas import (
    ChatHistoryResponse,
    ChatMessageRequest,
    ChatMessageResponse,
)
from app.services.chat_service import get_history, send_message, send_file_message

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])


@router.post(
    "/message",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Envia mensaje al ChatAgent y obtiene respuesta IA",
)
async def message(body: ChatMessageRequest, current_user: CurrentUserDep) -> ChatMessageResponse:
    _user_msg, assistant_msg = await send_message(
        org_id=current_user.org_id,
        user_id=current_user.user_id,
        content=body.content,
        file_id=body.file_id,
    )
    return assistant_msg


@router.post(
    "/upload",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Sube archivo via chat — el agente lo analiza y carga automaticamente",
)
async def upload_and_process(
    file: UploadFile = File(...),
    message: Optional[str] = Form(default=None),
    current_user: CurrentUserDep = None,
) -> ChatMessageResponse:
    """El Schema Agent analiza el CSV, decide donde cargarlo, y responde."""
    return await send_file_message(
        org_id=current_user.org_id,
        user_id=current_user.user_id,
        file=file,
        user_message=message,
    )


@router.get(
    "/history",
    response_model=ChatHistoryResponse,
    summary="Historial de chat de la organizacion",
)
async def history(current_user: CurrentUserDep, limit: int = 50) -> ChatHistoryResponse:
    return await get_history(current_user.org_id, limit=min(limit, 200))
