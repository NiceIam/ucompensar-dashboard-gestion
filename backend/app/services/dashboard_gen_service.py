"""Servicio de auto-generacion de dashboards post-ETL."""

import json
import logging
from datetime import datetime, timezone

from app.database import get_main_pool, get_org_pool

logger = logging.getLogger(__name__)


async def auto_generate_dashboard(org_id: str, job_id: str) -> dict:
    """Genera automaticamente un dashboard basado en los datos cargados.

    Llamado al completar un job ETL. Crea o actualiza el dashboard
    principal de la org y genera widgets segun las columnas disponibles
    en las tablas con datos.
    """
    # Obtener nombre de la org desde la BD principal
    main_pool = await get_main_pool()
    async with main_pool.acquire() as conn:
        org_row = await conn.fetchrow(
            "SELECT name, business_type FROM organizations WHERE id = $1",
            org_id,
        )

    if not org_row:
        return {"error": "Organizacion no encontrada."}

    org_name: str = org_row["name"] or ""

    # Consultar tablas con datos en la DB org
    org_pool = await get_org_pool(org_id)
    async with org_pool.acquire() as conn:
        table_rows = await conn.fetch(
            """
            SELECT id, table_name, display_name, row_count, columns_definition
            FROM org_data_tables
            WHERE row_count > 0
            """
        )

    tables: list[dict] = []
    for r in table_rows:
        d = dict(r)
        d["id"] = str(d["id"])
        cols = d.get("columns_definition")
        if isinstance(cols, str):
            d["columns_definition"] = json.loads(cols)
        elif cols is None:
            d["columns_definition"] = []
        tables.append(d)

    if not tables:
        return {"message": "No hay datos para generar dashboard."}

    now = datetime.now(timezone.utc)

    async with org_pool.acquire() as conn:
        # Buscar dashboard existente
        existing = await conn.fetchrow(
            """
            SELECT id FROM dashboards
            WHERE name = 'Dashboard Principal' AND deleted_at IS NULL
            """
        )

        if existing:
            dashboard_id: str = str(existing["id"])
            await conn.execute(
                "UPDATE dashboards SET updated_at = NOW() WHERE id = $1",
                existing["id"],
            )
        else:
            dash_row = await conn.fetchrow(
                """
                INSERT INTO dashboards (name, description, is_public)
                VALUES ('Dashboard Principal', $1, FALSE)
                RETURNING id
                """,
                f"Dashboard auto-generado para {org_name}",
            )
            dashboard_id = str(dash_row["id"])

        # Eliminar widgets previos
        await conn.execute(
            "DELETE FROM widgets WHERE dashboard_id = $1",
            dashboard_id,
        )

        widgets_inserted = 0

        # Fila de KPI cards — una por tabla con datos (max 3)
        for i, table in enumerate(tables[:3]):
            await conn.execute(
                """
                INSERT INTO widgets (
                    dashboard_id, title, widget_type, config,
                    position_x, position_y, width, height
                )
                VALUES ($1, $2, 'kpi_card', $3::jsonb, $4, 0, 4, 2)
                """,
                dashboard_id,
                f"Total {table['display_name']}",
                json.dumps({
                    "table_name": table["table_name"],
                    "metric": "count",
                    "format": "number",
                }),
                i * 4,
            )
            widgets_inserted += 1

        position_y = 2

        # Graficas por tabla
        for table in tables:
            cols: list[dict] = table.get("columns_definition") or []
            numeric_cols = [c for c in cols if c.get("type") in ("currency", "integer", "number")]
            date_cols = [c for c in cols if c.get("type") == "date"]

            if numeric_cols:
                x_col = date_cols[0]["name"] if date_cols else (cols[0]["name"] if cols else "")
                label = numeric_cols[0].get("label") or numeric_cols[0].get("name", "")
                await conn.execute(
                    """
                    INSERT INTO widgets (
                        dashboard_id, title, widget_type, config,
                        position_x, position_y, width, height
                    )
                    VALUES ($1, $2, 'bar_chart', $3::jsonb, 0, $4, 6, 4)
                    """,
                    dashboard_id,
                    f"{label} — {table['display_name']}",
                    json.dumps({
                        "table_name": table["table_name"],
                        "y_column": numeric_cols[0]["name"],
                        "x_column": x_col,
                        "aggregation": "SUM",
                    }),
                    position_y,
                )
                widgets_inserted += 1

            if date_cols and len(numeric_cols) > 1:
                label2 = numeric_cols[1].get("label") or numeric_cols[1].get("name", "")
                await conn.execute(
                    """
                    INSERT INTO widgets (
                        dashboard_id, title, widget_type, config,
                        position_x, position_y, width, height
                    )
                    VALUES ($1, $2, 'line_chart', $3::jsonb, 6, $4, 6, 4)
                    """,
                    dashboard_id,
                    f"Tendencia {label2}",
                    json.dumps({
                        "table_name": table["table_name"],
                        "x_column": date_cols[0]["name"],
                        "y_column": numeric_cols[1]["name"],
                    }),
                    position_y,
                )
                widgets_inserted += 1

            position_y += 4

    return {
        "dashboard_id": dashboard_id,
        "widgets_created": widgets_inserted,
        "tables_analyzed": len(tables),
    }
