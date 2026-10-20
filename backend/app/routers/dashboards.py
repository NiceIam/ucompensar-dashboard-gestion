from typing import Annotated, Any, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from slowapi.util import get_remote_address

from app.auth import CurrentUser, CurrentUserDep, limiter
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

# Calcular un tablero, abrir el detalle de un dato y pedir las opciones de filtro leen las tablas de la organizacion
# (unas pocas consultas cada una). Es de solo lectura y sin IA: un tope por usuario protege la BD de un cliente que
# insista (el cambio de un filtro recalcula el tablero, por eso el de `execute` es mas holgado).
DASHBOARD_READ_RATE_LIMIT = "120/minute"
DRILL_RATE_LIMIT = "90/minute"


def _rate_limit_key(request: Request) -> str:
    return getattr(request.state, "rate_limit_key", None) or get_remote_address(request)


async def _rate_limited_user(request: Request, current_user: CurrentUserDep) -> CurrentUser:
    """CurrentUser + su identidad como clave del limiter. Las peticiones sin sesion (401) no consumen cupo."""
    request.state.rate_limit_key = f"dashboards-user:{current_user.user_id}"
    return current_user


RateLimitedUser = Annotated[CurrentUser, Depends(_rate_limited_user)]

# Quien borra tableros. Crear (por chat o sugerencias) lo puede hacer cualquier miembro; borrar, solo
# owner/admin (los tableros son de toda la organizacion y no tienen dueno propio).
_DELETE_ROLES = ("owner", "admin")


def _require_delete_role(current_user) -> None:
    if current_user.role not in _DELETE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Solo el propietario o un administrador puede eliminar tableros."
        )


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
    _require_delete_role(current_user)
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


class ExecuteRequest(BaseModel):
    """Cuerpo OPCIONAL de /execute: `{}` (o sin cuerpo) calcula el tablero como siempre."""
    model_config = ConfigDict(extra="ignore")

    # Filtros globales de solo lectura: {"period": {"preset"|"from","to"}, "where": [{"key", "values"}]}.
    filters: dict[str, Any] | None = None


class DrillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # El valor tocado: la categoria o el periodo del eje X (`key` del dato si lo trae, si no su `name`).
    # null = el grupo "(sin dato)". Se puede omitir solo con `other: true`.
    value: str | int | float | None = None
    by: str | None = Field(default=None, max_length=80)       # dimension de detalle (de la lista `dimensions`)
    other: bool = False                                      # la porcion "Otros (n)" de un pastel
    limit: int | None = Field(default=None, ge=1, le=50)
    filters: dict[str, Any] | None = None


def _http_error(exc: Exception) -> HTTPException:
    from app.services.dashboard_drill_service import DrillError

    code = exc.status_code if isinstance(exc, DrillError) else 422
    return HTTPException(status_code=code, detail=str(exc))


@router.post(
    "/{dashboard_id}/execute",
    summary="Calcula los graficos y cifras del tablero con tus datos de este momento (con filtros opcionales)",
)
@limiter.limit(DASHBOARD_READ_RATE_LIMIT, key_func=_rate_limit_key)
async def execute(
    request: Request,
    dashboard_id: str,
    current_user: RateLimitedUser,
    body: ExecuteRequest | None = None,
):
    from app.services import data_query_engine as engine
    from app.services.dashboard_filters import FilterError
    from app.services.dashboard_render_service import render_dashboard

    try:
        return await render_dashboard(current_user.org_id, dashboard_id, body.filters if body else None)
    except (FilterError, engine.QueryError) as exc:
        raise _http_error(exc) from exc


@router.post(
    "/{dashboard_id}/widgets/{widget_id}/drill",
    summary="Detalle de un dato tocado en un grafico: de que esta hecho, por producto, cliente, mes... (solo lectura, sin IA)",
)
@limiter.limit(DRILL_RATE_LIMIT, key_func=_rate_limit_key)
async def drill(
    request: Request,
    dashboard_id: str,
    widget_id: str,
    body: DrillRequest,
    current_user: RateLimitedUser,
):
    from app.services import data_query_engine as engine
    from app.services.dashboard_drill_service import DrillError, drill as run_drill
    from app.services.dashboard_filters import FilterError

    try:
        return await run_drill(current_user.org_id, dashboard_id, widget_id, body.model_dump(exclude_unset=True))
    except (DrillError, FilterError, engine.QueryError) as exc:
        raise _http_error(exc) from exc


@router.get(
    "/{dashboard_id}/filter-options",
    summary="Que puedes filtrar en este tablero: rango de fechas y valores mas frecuentes de cada categoria",
)
@limiter.limit(DASHBOARD_READ_RATE_LIMIT, key_func=_rate_limit_key)
async def filter_options(
    request: Request,
    dashboard_id: str,
    current_user: RateLimitedUser,
    key: Annotated[str | None, Query(max_length=60, description="Solo esta categoria (para buscar sus valores)")] = None,
    q: Annotated[str | None, Query(max_length=60, description="Texto a buscar dentro de los valores de `key`")] = None,
):
    from app.services import data_query_engine as engine
    from app.services.dashboard_drill_service import DrillError
    from app.services.dashboard_filter_options_service import filter_options as run_options

    try:
        return await run_options(current_user.org_id, dashboard_id, key=key, q=q)
    except (DrillError, engine.QueryError) as exc:
        raise _http_error(exc) from exc
