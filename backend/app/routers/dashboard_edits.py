"""Deshacer y versiones de las ediciones de tableros hechas por el asistente — PI0320251.

Va en su propio router (mismo prefijo que `dashboards`) para no tocar los archivos del detalle del tablero.
Cualquier miembro de la organizacion puede deshacer (igual que pedir la edicion); el borrado de tableros sigue
restringido a owner/admin en `dashboards.py`. La base de datos ya es de la organizacion del usuario autenticado:
una version de otra organizacion simplemente no existe aqui (404).
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.auth import CurrentUserDep
from app.database import get_org_pool
from app.services import dashboard_edit_service as editor

router = APIRouter(prefix="/api/v1/dashboards", tags=["Dashboards"])


class UndoEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, max_length=64, description="Version previa que se restaura (de la tarjeta del chat)")
    include_newer: bool = Field(False, description="Confirma perder tambien las ediciones mas recientes del tablero")


class UndoEditResponse(BaseModel):
    id: str
    name: str
    widgets: int
    discarded_newer: int


class DashboardVersion(BaseModel):
    version: str
    created_at: datetime
    name: str
    widgets: int
    summary: dict[str, Any]


def _http(exc: editor.UndoError) -> HTTPException:
    if exc.status == status.HTTP_409_CONFLICT:
        return HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message, **exc.extra})
    return HTTPException(status_code=exc.status, detail=exc.message)


@router.post(
    "/{dashboard_id}/undo-edit",
    response_model=UndoEditResponse,
    summary="Deshace una edicion del asistente: restaura el tablero a como estaba antes de ese cambio",
)
async def undo_edit(dashboard_id: str, body: UndoEditRequest, current_user: CurrentUserDep) -> UndoEditResponse:
    pool = await get_org_pool(current_user.org_id)
    try:
        return UndoEditResponse(**await editor.undo_edit(pool, dashboard_id, body.version, include_newer=body.include_newer))
    except editor.UndoError as exc:
        raise _http(exc)


@router.get(
    "/{dashboard_id}/versions",
    response_model=list[DashboardVersion],
    summary="Versiones previas del tablero que se pueden restaurar (solo lectura, sin datos)",
)
async def versions(dashboard_id: str, current_user: CurrentUserDep) -> list[DashboardVersion]:
    pool = await get_org_pool(current_user.org_id)
    try:
        return [DashboardVersion(**v) for v in await editor.list_versions(pool, dashboard_id)]
    except editor.UndoError as exc:
        raise _http(exc)
