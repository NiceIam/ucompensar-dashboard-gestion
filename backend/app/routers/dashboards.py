from typing import List

from fastapi import APIRouter, File, UploadFile, status
from fastapi.responses import Response

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
    summary="Crea un nuevo dashboard con script Python auto-generado",
)
async def create(body: DashboardCreate, current_user: CurrentUserDep) -> DashboardResponse:
    from app.services.dashboard_script_service import create_dashboard_script
    result = await create_dashboard(current_user.org_id, current_user.user_id, body)
    # Auto-generar script Python
    await create_dashboard_script(current_user.org_id, result.dashboard_id)
    return result


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
# Script Python del Dashboard
# ---------------------------------------------------------------------------


@router.get(
    "/{dashboard_id}/script",
    summary="Obtiene el script Python del dashboard",
)
async def get_script(dashboard_id: str, current_user: CurrentUserDep):
    from app.services.dashboard_script_service import get_dashboard_script, create_dashboard_script
    script = get_dashboard_script(current_user.org_id, dashboard_id)
    if script is None:
        script = await create_dashboard_script(current_user.org_id, dashboard_id)
    return {"script": script, "dashboard_id": dashboard_id}


@router.get(
    "/{dashboard_id}/script/download",
    summary="Descarga el script Python como archivo .py",
)
async def download_script(dashboard_id: str, current_user: CurrentUserDep):
    from app.services.dashboard_script_service import get_dashboard_script, create_dashboard_script
    script = get_dashboard_script(current_user.org_id, dashboard_id)
    if script is None:
        script = await create_dashboard_script(current_user.org_id, dashboard_id)
    return Response(
        content=script,
        media_type="text/x-python",
        headers={"Content-Disposition": f'attachment; filename="dashboard_{dashboard_id[:8]}.py"'},
    )


@router.put(
    "/{dashboard_id}/script",
    summary="Sube/actualiza el script Python del dashboard",
)
async def update_script(dashboard_id: str, file: UploadFile = File(...), current_user: CurrentUserDep = None):
    from app.services.dashboard_script_service import save_dashboard_script
    content = (await file.read()).decode("utf-8")
    save_dashboard_script(current_user.org_id, dashboard_id, content)
    return {"message": "Script actualizado", "size": len(content)}


@router.post(
    "/{dashboard_id}/execute",
    summary="Ejecuta el script Python y retorna charts + kpis para Recharts",
)
async def execute_script(dashboard_id: str, current_user: CurrentUserDep):
    from app.services.dashboard_script_service import execute_dashboard_script
    result = await execute_dashboard_script(current_user.org_id, dashboard_id)
    return result
