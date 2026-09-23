"""Tools del ChatAgent para consultas, graficas y reportes."""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
from google.adk.tools import ToolContext

from agents.config import get_main_conn, get_org_conn
from agents.tools._security import validate_org_id

logger = logging.getLogger("agents.tools.chat")

MAX_QUERY_ROWS = 100


def query_org_data(
    org_id: str,
    table_name: str,
    tool_context: ToolContext,
    filters: str = "",
    aggregation: str = "",
    group_by: str = "",
    order_by: str = "",
    limit: int = 50,
) -> dict:
    """Consulta los datos de una tabla de la organizacion con filtros y agregaciones.

    Los datos estan en org_data_rows.data (JSONB). Soporta filtros basicos,
    agregaciones (SUM, AVG, COUNT, MIN, MAX) y agrupamiento.

    Args:
        org_id: UUID de la organizacion.
        table_name: Nombre de la tabla a consultar (ej: 'productos', 'ventas').
        filters: Filtros en formato JSON string, ej: '{"stock_actual": {"lt": 10}}'.
            Operadores: eq, neq, gt, gte, lt, lte, like, in.
        aggregation: Funcion de agregacion, ej: 'SUM(total)' o 'COUNT(*)'.
        group_by: Columna para agrupar, ej: 'metodo_pago'.
        order_by: Columna para ordenar, ej: 'fecha' o '-total' (- para desc).
        limit: Maximo de filas a retornar (max 100).

    Returns:
        dict con rows (lista de registros), total_count, columns.
    """
    _auth_err = validate_org_id(org_id, tool_context)
    if _auth_err:
        return _auth_err
    try:
        limit = min(limit, MAX_QUERY_ROWS)

        with get_org_conn(org_id) as conn:
            with conn.cursor() as cur:
                # Get table_id
                cur.execute(
                    """
                    SELECT id, display_name, columns_definition, row_count
                    FROM org_data_tables
                    WHERE org_id = %s AND table_name = %s
                    """,
                    (org_id, table_name),
                )
                table_row = cur.fetchone()
                if not table_row:
                    return {"error": f"Tabla '{table_name}' no encontrada."}

                table_id = str(table_row["id"])
                total_count = table_row.get("row_count", 0) or 0

                # Fetch rows
                cur.execute(
                    """
                    SELECT data FROM org_data_rows
                    WHERE org_id = %s AND table_id = %s
                    LIMIT %s
                    """,
                    (org_id, table_id, limit),
                )
                result_rows = cur.fetchall()

        rows = [r["data"] for r in result_rows]

        if not rows:
            return {
                "rows": [],
                "total_count": total_count,
                "columns": [
                    c["name"]
                    for c in (table_row.get("columns_definition") or [])
                ],
                "message": f"La tabla '{table_name}' no tiene datos cargados.",
            }

        df = pd.DataFrame(rows)

        # Apply filters
        if filters:
            try:
                filter_dict = (
                    json.loads(filters) if isinstance(filters, str) else filters
                )
                for col, condition in filter_dict.items():
                    if col not in df.columns:
                        continue
                    if isinstance(condition, dict):
                        for op, val in condition.items():
                            series = pd.to_numeric(df[col], errors="coerce")
                            if op == "gt":
                                df = df[series > val]
                            elif op == "gte":
                                df = df[series >= val]
                            elif op == "lt":
                                df = df[series < val]
                            elif op == "lte":
                                df = df[series <= val]
                            elif op == "eq":
                                df = df[df[col] == val]
                            elif op == "neq":
                                df = df[df[col] != val]
                            elif op == "like":
                                df = df[
                                    df[col]
                                    .astype(str)
                                    .str.contains(
                                        str(val), case=False, na=False
                                    )
                                ]
                    else:
                        df = df[df[col] == condition]
            except (json.JSONDecodeError, TypeError):
                pass

        # Apply aggregation
        if aggregation and group_by and group_by in df.columns:
            agg_match = re.match(
                r"(SUM|AVG|COUNT|MIN|MAX)\((\w+|\*)\)",
                aggregation.upper(),
            )
            if agg_match:
                func = agg_match.group(1).lower()
                col = agg_match.group(2)

                if col == "*":
                    agg_result = (
                        df.groupby(group_by)
                        .size()
                        .reset_index(name="count")
                    )
                elif col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                    agg_map = {
                        "sum": "sum",
                        "avg": "mean",
                        "count": "count",
                        "min": "min",
                        "max": "max",
                    }
                    agg_result = (
                        df.groupby(group_by)[col]
                        .agg(agg_map.get(func, "sum"))
                        .reset_index()
                    )
                    agg_result.columns = [group_by, f"{func}_{col}"]
                else:
                    agg_result = df

                rows = agg_result.head(limit).to_dict("records")
                return {
                    "rows": rows,
                    "total_count": len(agg_result),
                    "columns": list(agg_result.columns),
                    "aggregation_applied": aggregation,
                }

        # Apply order
        if order_by:
            desc = order_by.startswith("-")
            col = order_by.lstrip("-")
            if col in df.columns:
                df = df.sort_values(col, ascending=not desc)

        rows = df.head(limit).to_dict("records")
        # Clean NaN values
        for row in rows:
            for k, v in row.items():
                if isinstance(v, float) and pd.isna(v):
                    row[k] = None

        return {
            "rows": rows,
            "total_count": total_count,
            "columns": list(df.columns),
            "rows_returned": len(rows),
        }

    except Exception as e:
        logger.error(f"Error en query_org_data: {e}", exc_info=True)
        return {"error": f"Error al consultar datos: {type(e).__name__}"}


def get_org_summary(org_id: str, tool_context: ToolContext) -> dict:
    """Obtiene un resumen completo de los datos de la organizacion.

    Muestra que tablas existen, cuantas filas tiene cada una,
    y una muestra de datos de cada tabla.

    Args:
        org_id: UUID de la organizacion.

    Returns:
        dict con business_type, tables (lista con name, display_name,
        row_count, sample_rows), total_records.
    """
    _auth_err = validate_org_id(org_id, tool_context)
    if _auth_err:
        return _auth_err
    try:
        # Get org info from main DB
        with get_main_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT o.name, bt.name AS bt_name, bt.display_name AS bt_display
                    FROM organizations o
                    LEFT JOIN business_types bt ON bt.id = o.business_type_id
                    WHERE o.id = %s
                    """,
                    (org_id,),
                )
                org_row = cur.fetchone()

        org = org_row or {}
        org_name = org.get("name", "")
        bt_display = org.get("bt_display", "No configurado")

        # Get tables and sample data from org DB
        with get_org_conn(org_id) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, table_name, display_name, columns_definition, row_count
                    FROM org_data_tables
                    WHERE org_id = %s
                    """,
                    (org_id,),
                )
                tables_data = cur.fetchall()

                tables = []
                total_records = 0
                for t in tables_data:
                    row_count = t.get("row_count", 0) or 0
                    total_records += row_count

                    # Get sample rows
                    cur.execute(
                        """
                        SELECT data FROM org_data_rows
                        WHERE org_id = %s AND table_id = %s
                        LIMIT 3
                        """,
                        (org_id, str(t["id"])),
                    )
                    sample_rows = [r["data"] for r in cur.fetchall()]

                    tables.append(
                        {
                            "name": t["table_name"],
                            "display_name": t["display_name"],
                            "row_count": row_count,
                            "columns": [
                                c["name"]
                                for c in (t.get("columns_definition") or [])
                            ],
                            "sample_rows": sample_rows,
                        }
                    )

        return {
            "org_name": org_name,
            "business_type": bt_display,
            "tables": tables,
            "total_records": total_records,
            "has_data": total_records > 0,
        }

    except Exception as e:
        logger.error(f"Error en get_org_summary: {e}", exc_info=True)
        return {"error": f"Error al obtener resumen: {type(e).__name__}"}


def generate_chart_config(
    org_id: str,
    chart_type: str,
    title: str,
    table_name: str,
    x_column: str,
    y_column: str,
    tool_context: ToolContext,
    aggregation: str = "",
    group_by: str = "",
) -> dict:
    """Genera una configuracion de grafica que el frontend puede renderizar con Recharts.

    Ejecuta la consulta de datos y formatea el resultado como configuracion
    de grafica lista para el componente React.

    Args:
        org_id: UUID de la organizacion.
        chart_type: Tipo de grafica: 'bar', 'line', 'pie', 'area', 'kpi'.
        title: Titulo de la grafica en espanol.
        table_name: Tabla de donde obtener los datos.
        x_column: Columna para el eje X o categorias.
        y_column: Columna para el eje Y o valores.
        aggregation: Funcion de agregacion opcional (ej: 'SUM', 'AVG', 'COUNT').
        group_by: Columna para agrupar (usa x_column si no se especifica).

    Returns:
        dict con chart_type, title, data (lista de puntos), config (para Recharts).
    """
    _auth_err = validate_org_id(org_id, tool_context)
    if _auth_err:
        return _auth_err
    try:
        with get_org_conn(org_id) as conn:
            with conn.cursor() as cur:
                # Get table_id
                cur.execute(
                    "SELECT id FROM org_data_tables WHERE org_id = %s AND table_name = %s",
                    (org_id, table_name),
                )
                table_row = cur.fetchone()
                if not table_row:
                    return {"error": f"Tabla '{table_name}' no encontrada."}

                table_id = str(table_row["id"])

                # Fetch data
                cur.execute(
                    """
                    SELECT data FROM org_data_rows
                    WHERE org_id = %s AND table_id = %s
                    LIMIT %s
                    """,
                    (org_id, table_id, MAX_QUERY_ROWS),
                )
                result_rows = cur.fetchall()

        rows = [r["data"] for r in result_rows]
        if not rows:
            return {"error": "No hay datos para generar la grafica."}

        df = pd.DataFrame(rows)

        # Prepare data for chart
        group = group_by or x_column
        chart_data: list[dict] = []

        if aggregation and group in df.columns and y_column in df.columns:
            df[y_column] = pd.to_numeric(df[y_column], errors="coerce")
            agg_func = {
                "SUM": "sum",
                "AVG": "mean",
                "COUNT": "count",
                "MIN": "min",
                "MAX": "max",
            }
            func = agg_func.get(aggregation.upper(), "sum")
            grouped = (
                df.groupby(group)[y_column].agg(func).reset_index()
            )
            grouped.columns = [group, y_column]
            chart_data = grouped.head(20).to_dict("records")
        elif x_column in df.columns and y_column in df.columns:
            chart_data = (
                df[[x_column, y_column]].dropna().head(50).to_dict("records")
            )
        elif chart_type == "kpi" and y_column in df.columns:
            df[y_column] = pd.to_numeric(df[y_column], errors="coerce")
            chart_data = [
                {
                    "value": round(float(df[y_column].sum()), 2),
                    "label": title,
                }
            ]

        # Clean NaN
        for row in chart_data:
            for k, v in row.items():
                if isinstance(v, float) and pd.isna(v):
                    row[k] = 0
                elif isinstance(v, float):
                    row[k] = round(v, 2)

        return {
            "chart_type": chart_type,
            "title": title,
            "data": chart_data,
            "config": {
                "x_key": x_column if chart_type != "kpi" else None,
                "y_key": y_column,
                "color": "#3b82f6",
            },
        }

    except Exception as e:
        logger.error(f"Error generando chart: {e}", exc_info=True)
        return {"error": f"Error al generar grafica: {type(e).__name__}"}


def calculate_kpis(org_id: str, tool_context: ToolContext) -> dict:
    """Calcula los KPIs predeterminados para la organizacion basados en su tipo de negocio.

    Lee la configuracion de KPIs del business_type y calcula cada uno
    usando los datos reales de la organizacion.

    Args:
        org_id: UUID de la organizacion.

    Returns:
        dict con kpis (lista de name, value, format, description).
    """
    _auth_err = validate_org_id(org_id, tool_context)
    if _auth_err:
        return _auth_err
    try:
        # Get business type from main DB
        with get_main_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT bt.name, bt.default_kpis
                    FROM organizations o
                    LEFT JOIN business_types bt ON bt.id = o.business_type_id
                    WHERE o.id = %s
                    """,
                    (org_id,),
                )
                bt_row = cur.fetchone()

        bt_name = (bt_row or {}).get("name", "")

        # Get all tables with data from org DB
        with get_org_conn(org_id) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, table_name, row_count FROM org_data_tables WHERE org_id = %s",
                    (org_id,),
                )
                tables_list = cur.fetchall()
                tables = {t["table_name"]: t for t in tables_list}

                kpis: list[dict] = []

                for table_name, table_info in tables.items():
                    table_id = str(table_info["id"])
                    row_count = table_info.get("row_count", 0) or 0

                    if row_count == 0:
                        continue

                    # Fetch data for calculations
                    cur.execute(
                        """
                        SELECT data FROM org_data_rows
                        WHERE org_id = %s AND table_id = %s
                        LIMIT %s
                        """,
                        (org_id, table_id, MAX_QUERY_ROWS),
                    )
                    rows = [r["data"] for r in cur.fetchall()]
                    if not rows:
                        continue

                    df = pd.DataFrame(rows)

                    kpis.append(
                        {
                            "name": f"Total {table_name}",
                            "value": row_count,
                            "format": "number",
                            "description": f"Registros en {table_name}",
                        }
                    )

                    # Find monetary columns and sum them
                    for col in df.columns:
                        if any(
                            kw in col
                            for kw in [
                                "total",
                                "precio",
                                "monto",
                                "valor",
                                "ingreso",
                                "venta",
                            ]
                        ):
                            series = pd.to_numeric(df[col], errors="coerce").dropna()
                            if not series.empty:
                                kpis.append(
                                    {
                                        "name": f"Total {col.replace('_', ' ').title()}",
                                        "value": round(float(series.sum()), 2),
                                        "format": "currency",
                                        "description": f"Suma de {col} en {table_name}",
                                    }
                                )
                                kpis.append(
                                    {
                                        "name": f"Promedio {col.replace('_', ' ').title()}",
                                        "value": round(float(series.mean()), 2),
                                        "format": "currency",
                                        "description": f"Promedio de {col} en {table_name}",
                                    }
                                )

        return {"kpis": kpis[:12], "business_type": bt_name}  # Max 12 KPIs

    except Exception as e:
        logger.error(f"Error calculando KPIs: {e}", exc_info=True)
        return {"error": f"Error al calcular KPIs: {type(e).__name__}"}
