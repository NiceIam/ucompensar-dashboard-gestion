import json
import uuid as _uuid_mod
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status

from app.database import get_org_pool


def _to_uuid(val: str):
    """Convierte string a UUID para asyncpg."""
    try:
        return _uuid_mod.UUID(val)
    except (ValueError, AttributeError):
        return val
from app.models.schemas import DashboardCreate, DashboardDetail, DashboardResponse, WidgetCreate, WidgetResponse


async def create_dashboard(org_id: str, user_id: str, body: DashboardCreate) -> DashboardResponse:
    pool = await get_org_pool(org_id)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO dashboards (name, description, is_public)
            VALUES ($1, $2, $3)
            RETURNING *
            """,
            body.name,
            body.description,
            body.is_public,
        )
    return _map_dashboard(dict(row), org_id)


async def list_dashboards(org_id: str) -> list[DashboardResponse]:
    pool = await get_org_pool(org_id)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM dashboards
            WHERE deleted_at IS NULL
            ORDER BY created_at DESC
            """
        )
    return [_map_dashboard(dict(r), org_id) for r in rows]


async def get_dashboard_data(dashboard_id: str, org_id: str) -> DashboardDetail:
    pool = await get_org_pool(org_id)
    did = _to_uuid(dashboard_id)
    async with pool.acquire() as conn:
        dash_row = await conn.fetchrow(
            "SELECT * FROM dashboards WHERE id = $1 AND deleted_at IS NULL",
            did,
        )
        if not dash_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard no encontrado.")

        widget_rows = await conn.fetch(
            "SELECT * FROM widgets WHERE dashboard_id = $1 ORDER BY position_y, position_x",
            did,
        )

    return DashboardDetail(
        **_map_dashboard(dict(dash_row), org_id).model_dump(),
        widgets=[_map_widget(dict(w)) for w in widget_rows],
    )


async def update_dashboard(
    dashboard_id: str,
    org_id: str,
    updates: dict[str, Any],
) -> DashboardResponse:
    # Construir SET clause dinámicamente
    allowed_fields = {"name", "description", "is_public"}
    set_clauses: list[str] = []
    values: list = []
    param_idx = 1

    for field, value in updates.items():
        if field in allowed_fields:
            set_clauses.append(f"{field} = ${param_idx}")
            values.append(value)
            param_idx += 1

    if not set_clauses:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No hay campos válidos para actualizar.",
        )

    set_clauses.append(f"updated_at = NOW()")
    values.append(_to_uuid(dashboard_id))

    pool = await get_org_pool(org_id)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE dashboards
            SET {', '.join(set_clauses)}
            WHERE id = ${param_idx} AND deleted_at IS NULL
            RETURNING *
            """,
            *values,
        )

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard no encontrado.")
    return _map_dashboard(dict(row), org_id)


async def soft_delete_dashboard(dashboard_id: str, org_id: str) -> None:
    pool = await get_org_pool(org_id)
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE dashboards SET deleted_at = NOW() WHERE id = $1 AND deleted_at IS NULL",
            _to_uuid(dashboard_id),
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard no encontrado.")


async def create_widget(dashboard_id: str, org_id: str, body: WidgetCreate) -> WidgetResponse:
    pool = await get_org_pool(org_id)
    did = _to_uuid(dashboard_id)
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT id FROM dashboards WHERE id = $1 AND deleted_at IS NULL",
            did,
        )
        if not exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard no encontrado.")

        row = await conn.fetchrow(
            """
            INSERT INTO widgets (
                dashboard_id, title, widget_type, config,
                position_x, position_y, width, height, data_source_query
            )
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9::jsonb)
            RETURNING *
            """,
            did,
            body.title,
            body.widget_type,
            json.dumps(body.config),
            body.position_x,
            body.position_y,
            body.width,
            body.height,
            json.dumps(body.data_source_query) if body.data_source_query else None,
        )

    return _map_widget(dict(row))


async def update_widget(
    widget_id: str,
    dashboard_id: str,
    org_id: str,
    updates: dict[str, Any],
) -> WidgetResponse:
    allowed_fields = {"title", "widget_type", "config", "position_x", "position_y", "width", "height", "data_source_query"}
    set_clauses: list[str] = []
    values: list = []
    param_idx = 1

    for field, value in updates.items():
        if field in allowed_fields:
            if field in ("config", "data_source_query"):
                set_clauses.append(f"{field} = ${param_idx}::jsonb")
                values.append(json.dumps(value) if value is not None else None)
            else:
                set_clauses.append(f"{field} = ${param_idx}")
                values.append(value)
            param_idx += 1

    if not set_clauses:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No hay campos válidos para actualizar.",
        )

    set_clauses.append("updated_at = NOW()")
    values.extend([_to_uuid(widget_id), _to_uuid(dashboard_id)])

    pool = await get_org_pool(org_id)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE widgets
            SET {', '.join(set_clauses)}
            WHERE id = ${param_idx} AND dashboard_id = ${param_idx + 1}
            RETURNING *
            """,
            *values,
        )

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Widget no encontrado.")
    return _map_widget(dict(row))


async def soft_delete_widget(widget_id: str, dashboard_id: str, org_id: str) -> None:
    pool = await get_org_pool(org_id)
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM widgets WHERE id = $1 AND dashboard_id = $2",
            _to_uuid(widget_id),
            _to_uuid(dashboard_id),
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Widget no encontrado.")


# ---------------------------------------------------------------------------
# Mappers
# ---------------------------------------------------------------------------

def _map_dashboard(row: dict, org_id: str) -> DashboardResponse:
    return DashboardResponse(
        dashboard_id=str(row["id"]),
        org_id=org_id,
        name=row["name"],
        description=row.get("description"),
        is_public=row.get("is_public", False),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _map_widget(row: dict) -> WidgetResponse:
    config = row.get("config")
    if isinstance(config, str):
        import json as _json
        config = _json.loads(config)
    dsq = row.get("data_source_query")
    if isinstance(dsq, str):
        import json as _json
        dsq = _json.loads(dsq)

    return WidgetResponse(
        widget_id=str(row["id"]),
        dashboard_id=str(row["dashboard_id"]),
        title=row["title"],
        widget_type=row["widget_type"],
        config=config or {},
        position_x=row.get("position_x", 0),
        position_y=row.get("position_y", 0),
        width=row.get("width", 6),
        height=row.get("height", 4),
        data_source_query=dsq,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
