"""Servicio para gestionar templates de tipo de negocio."""

import json
import logging
from typing import Any

from fastapi import HTTPException, status

from app.database import create_org_database, get_main_pool, get_org_pool

logger = logging.getLogger(__name__)


async def get_business_types() -> list[dict[str, Any]]:
    """Lista todos los tipos de negocio disponibles."""
    pool = await get_main_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, display_name, description, icon, default_kpis
            FROM business_types
            ORDER BY name
            """
        )
    result: list[dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        d["id"] = str(d["id"])
        kpis = d.get("default_kpis")
        if isinstance(kpis, str):
            d["default_kpis"] = json.loads(kpis)
        result.append(d)
    return result


async def get_business_type_detail(type_id: str) -> dict[str, Any]:
    """Obtiene un tipo de negocio con su schema completo."""
    pool = await get_main_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM business_types WHERE id = $1",
            type_id,
        )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tipo de negocio no encontrado.",
        )

    d = dict(row)
    d["id"] = str(d["id"])
    for jsonb_field in ("schema_definition", "default_kpis", "default_dashboard_config"):
        val = d.get(jsonb_field)
        if isinstance(val, str):
            d[jsonb_field] = json.loads(val)
        elif val is None:
            d[jsonb_field] = {} if jsonb_field != "default_kpis" else []
    return d


async def initialize_org_schema(org_id: str, business_type_id: str) -> dict[str, Any]:
    """Asocia el tipo de negocio a la org y crea/rellena la DB org con las tablas estándar.

    Flujo:
    1. Verifica que el business_type exista en pi_main
    2. Actualiza organizations.business_type en pi_main
    3. Llama create_org_database() que inicializa el schema de la DB org
    4. Retorna las tablas creadas consultando org_data_tables
    """
    main_pool = await get_main_pool()

    async with main_pool.acquire() as conn:
        bt_row = await conn.fetchrow(
            "SELECT id, name, display_name, schema_definition FROM business_types WHERE id = $1",
            business_type_id,
        )

    if not bt_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tipo de negocio no encontrado.",
        )

    business_type_name: str = bt_row["name"]

    # Actualizar la org en la BD principal
    async with main_pool.acquire() as conn:
        await conn.execute(
            "UPDATE organizations SET business_type = $1 WHERE id = $2",
            business_type_name,
            org_id,
        )

    # (Re)inicializar la DB org con el schema del tipo de negocio
    await create_org_database(org_id, business_type_name)

    # Consultar tablas creadas
    org_pool = await get_org_pool(org_id)
    async with org_pool.acquire() as conn:
        table_rows = await conn.fetch(
            "SELECT table_name, display_name, columns_definition FROM org_data_tables"
        )

    tables_created: list[dict] = []
    for r in table_rows:
        cols = r["columns_definition"]
        if isinstance(cols, str):
            cols = json.loads(cols)
        tables_created.append(
            {
                "name": r["table_name"],
                "display_name": r["display_name"],
                "columns": len(cols or []),
            }
        )

    return {
        "org_id": org_id,
        "business_type": bt_row["display_name"],
        "tables_created": tables_created,
    }


async def get_org_tables(org_id: str) -> list[dict[str, Any]]:
    """Lista las tablas de datos de una organizacion con su conteo de filas."""
    org_pool = await get_org_pool(org_id)
    async with org_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, table_name, display_name, columns_definition, row_count FROM org_data_tables"
        )

    result: list[dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        d["id"] = str(d["id"])
        cols = d.get("columns_definition")
        if isinstance(cols, str):
            d["columns_definition"] = json.loads(cols)
        elif cols is None:
            d["columns_definition"] = []
        result.append(d)
    return result
