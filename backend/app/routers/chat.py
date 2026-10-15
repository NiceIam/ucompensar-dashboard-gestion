from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from slowapi.util import get_remote_address

from app.auth import CurrentUser, CurrentUserDep, limiter
from app.config import get_settings
from app.models.schemas import (
    ChatHistoryResponse,
    ChatMessageRequest,
    ChatMessageResponse,
)
from app.services.chat_service import get_history, send_message, send_file_message

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])


def _chat_rate_limit() -> str:
    """Limite de /message; configurable con CHAT_RATE_LIMIT (se lee en cada peticion)."""
    return get_settings().CHAT_RATE_LIMIT


def _rate_limit_key(request: Request) -> str:
    """Cuenta por usuario autenticado; si no hay (no deberia pasar), por IP como el resto del proyecto."""
    return getattr(request.state, "rate_limit_key", None) or get_remote_address(request)


async def _rate_limited_user(request: Request, current_user: CurrentUserDep) -> CurrentUser:
    """CurrentUser + publica su identidad para que el limiter la use como clave.

    Las dependencias se resuelven antes del decorador de slowapi, por eso la clave
    ya existe cuando el limiter la lee, y las peticiones sin sesion (401) no consumen cupo.
    """
    request.state.rate_limit_key = f"chat-user:{current_user.user_id}"
    return current_user


@router.post(
    "/message",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Envia mensaje al ChatAgent y obtiene respuesta IA",
)
@limiter.limit(_chat_rate_limit, key_func=_rate_limit_key)
async def message(
    request: Request,
    body: ChatMessageRequest,
    current_user: Annotated[CurrentUser, Depends(_rate_limited_user)],
) -> ChatMessageResponse:
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
