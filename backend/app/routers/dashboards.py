from typing import List

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.auth import CurrentUserDep
from app.models.schemas import (
    DashboardCreate,
    DashboardDetail,
    DashboardResponse,
    DashboardUpdate,
    MessageResponse,
    WidgetCreate,
    WidgetResponse,
    WidgetUpdate,
)
from app.services.dashboard_service import (
    create_dashboard,
    create_widget,
    get_dashboard_data,
    list_dashboards,
    soft_delete_dashboard,
    soft_delete_widget,
    update_dashboard,
    update_widget,
)

router = APIRouter(prefix="/api/v1/dashboards", tags=["Dashboards"])


@router.post(
    "",
    response_model=DashboardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crea un dashboard vacio (los tableros con graficos los crea el asistente o /suggest)",
)
async def create(body: DashboardCreate, current_user: CurrentUserDep) -> DashboardResponse:
    return await create_dashboard(current_user.org_id, current_user.user_id, body)


class SuggestRequest(BaseModel):
    # auto=True: solo si la organizacion no tiene tableros y esos datos no se sugirieron antes (lo usa Tableros
    # cuando esta vacio). auto=False: el boton "Sugerir tableros".
    auto: bool = False


@router.post(
    "/suggest",
    summary="Sugiere y crea 1-3 tableros con tus datos (una llamada pequeña a la IA o una regla sin IA)",
)
async def suggest(current_user: CurrentUserDep, body: SuggestRequest | None = None):
    from app.services.dashboard_suggest_service import suggest as suggest_dashboards
    return await suggest_dashboards(current_user.org_id, auto=bool(body and body.auto))


@router.get("", response_model=List[DashboardResponse], summary="Lista dashboards de la organización")
async def list_all(current_user: CurrentUserDep) -> List[DashboardResponse]:
    return await list_dashboards(current_user.org_id)


@router.get(
    "/{dashboard_id}",
    response_model=DashboardDetail,
    summary="Detalle de dashboard con widgets",
)
async def get_one(dashboard_id: str, current_user: CurrentUserDep) -> DashboardDetail:
    return await get_dashboard_data(dashboard_id, current_user.org_id)


@router.put(
    "/{dashboard_id}",
    response_model=DashboardResponse,
    summary="Reemplaza todos los campos del dashboard",
)
async def replace(
    dashboard_id: str,
    body: DashboardCreate,
    current_user: CurrentUserDep,
) -> DashboardResponse:
    updates = body.model_dump()
    return await update_dashboard(dashboard_id, current_user.org_id, updates)


@router.patch(
    "/{dashboard_id}",
    response_model=DashboardResponse,
    summary="Actualización parcial del dashboard",
)
async def patch(
    dashboard_id: str,
    body: DashboardUpdate,
    current_user: CurrentUserDep,
) -> DashboardResponse:
    updates = body.model_dump(exclude_none=True)
    return await update_dashboard(dashboard_id, current_user.org_id, updates)


@router.delete(
    "/{dashboard_id}",
    response_model=MessageResponse,
    summary="Soft delete del dashboard",
)
async def delete(dashboard_id: str, current_user: CurrentUserDep) -> MessageResponse:
    await soft_delete_dashboard(dashboard_id, current_user.org_id)
    return MessageResponse(message="Dashboard eliminado correctamente.")


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------


@router.post(
    "/{dashboard_id}/widgets",
    response_model=WidgetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Agrega un widget al dashboard",
)
async def add_widget(
    dashboard_id: str,
    body: WidgetCreate,
    current_user: CurrentUserDep,
) -> WidgetResponse:
    return await create_widget(dashboard_id, current_user.org_id, body)


@router.put(
    "/{dashboard_id}/widgets/{widget_id}",
    response_model=WidgetResponse,
    summary="Reemplaza la configuración del widget",
)
async def replace_widget(
    dashboard_id: str,
    widget_id: str,
    body: WidgetCreate,
    current_user: CurrentUserDep,
) -> WidgetResponse:
    updates = body.model_dump()
    return await update_widget(widget_id, dashboard_id, current_user.org_id, updates)


@router.patch(
    "/{dashboard_id}/widgets/{widget_id}",
    response_model=WidgetResponse,
    summary="Actualización parcial del widget (drag-and-drop friendly)",
)
async def patch_widget(
    dashboard_id: str,
    widget_id: str,
    body: WidgetUpdate,
    current_user: CurrentUserDep,
) -> WidgetResponse:
    updates = body.model_dump(exclude_none=True)
    return await update_widget(widget_id, dashboard_id, current_user.org_id, updates)


@router.delete(
    "/{dashboard_id}/widgets/{widget_id}",
    response_model=MessageResponse,
    summary="Elimina un widget del dashboard",
)
async def delete_widget(
    dashboard_id: str,
    widget_id: str,
    current_user: CurrentUserDep,
) -> MessageResponse:
    await soft_delete_widget(widget_id, dashboard_id, current_user.org_id)
    return MessageResponse(message="Widget eliminado correctamente.")


# ---------------------------------------------------------------------------
# Calculo del tablero
# ---------------------------------------------------------------------------


@router.post(
    "/{dashboard_id}/execute",
    summary="Calcula los graficos y cifras del tablero con tus datos de este momento",
)
async def execute(dashboard_id: str, current_user: CurrentUserDep):
    from app.services.dashboard_render_service import render_dashboard
    return await render_dashboard(current_user.org_id, dashboard_id)
