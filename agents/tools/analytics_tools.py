"""Tools del AnalyticalAgent para analisis avanzado de datos empresariales.

Incluye deteccion de tendencias, comparacion de periodos, anomalias,
reportes automaticos y analisis cruzado entre tablas.
"""

import logging
from typing import Any

import numpy as np
import pandas as pd
from google.adk.tools import ToolContext

from agents.config import get_main_conn, get_org_conn
from agents.tools._security import validate_org_id

logger = logging.getLogger("agents.tools.analytics")

MAX_ROWS = 10_000


# ---------------------------------------------------------------------------
# Helper: cargar tabla como DataFrame
# ---------------------------------------------------------------------------
def _load_table_df(org_id: str, table_name: str) -> tuple[pd.DataFrame, dict]:
    """Carga los datos de una tabla de la organizacion como DataFrame.

    Args:
        org_id: UUID de la organizacion.
        table_name: Nombre de la tabla a consultar.

    Returns:
        Tupla (DataFrame con los datos, dict con info de la tabla).
        Si la tabla no existe retorna (DataFrame vacio, dict vacio).
    """
    with get_org_conn(org_id) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, columns_definition, row_count FROM org_data_tables WHERE org_id = %s AND table_name = %s",
                (org_id, table_name),
            )
            table_row = cur.fetchone()
            if not table_row:
                return pd.DataFrame(), {}

            table_id = str(table_row["id"])
            cur.execute(
                """
                SELECT data FROM org_data_rows
                WHERE org_id = %s AND table_id = %s
                LIMIT %s
                """,
                (org_id, table_id, MAX_ROWS),
            )
            rows = [r["data"] for r in cur.fetchall()]

    table_info = dict(table_row)
    table_info["id"] = table_id
    return (pd.DataFrame(rows) if rows else pd.DataFrame()), table_info


def _clean_nan(obj: Any) -> Any:
    """Reemplaza NaN/Inf por None recursivamente en dicts y listas."""
    if isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_nan(item) for item in obj]
    if isinstance(obj, float) and (pd.isna(obj) or np.isinf(obj)):
        return None
    return obj


# ---------------------------------------------------------------------------
# Tool 1: detect_trends
# ---------------------------------------------------------------------------
def detect_trends(
    org_id: str,
    table_name: str,
    date_column: str,
    value_column: str,
    tool_context: ToolContext,
) -> dict:
    """Detecta tendencias temporales en una columna numerica agrupando por mes.

    Agrupa los datos por mes, calcula la direccion de la tendencia
    (subiendo, bajando o estable), el cambio porcentual total y una
    linea de tendencia lineal.

    Args:
        org_id: UUID de la organizacion.
        table_name: Nombre de la tabla a analizar (ej: 'ventas').
        date_column: Nombre de la columna de fecha (ej: 'fecha').
        value_column: Nombre de la columna numerica a evaluar (ej: 'total').

    Returns:
        dict con direction (subiendo/bajando/estable), cambio_porcentual,
        monthly_data (lista de meses con valor), trend_line (pendiente e intercepto),
        y chart_config para renderizar la grafica.
    """
    _auth_err = validate_org_id(org_id, tool_context)
    if _auth_err:
        return _auth_err
    try:
        df, table_info = _load_table_df(org_id, table_name)
        if df.empty:
            return {"error": f"La tabla '{table_name}' no tiene datos."}

        if date_column not in df.columns:
            return {"error": f"La columna '{date_column}' no existe en la tabla."}
        if value_column not in df.columns:
            return {"error": f"La columna '{value_column}' no existe en la tabla."}

        # Preparar datos
        df[date_column] = pd.to_datetime(df[date_column], errors="coerce")
        df[value_column] = pd.to_numeric(df[value_column], errors="coerce")
        df = df.dropna(subset=[date_column, value_column])

        if df.empty:
            return {"error": "No hay datos validos para analizar tendencias."}

        # Agrupar por mes
        df["_mes"] = df[date_column].dt.to_period("M")
        monthly = (
            df.groupby("_mes")[value_column]
            .agg(["sum", "mean", "count"])
            .reset_index()
        )
        monthly.columns = ["periodo", "total", "promedio", "registros"]
        monthly = monthly.sort_values("periodo")

        if len(monthly) < 2:
            return {
                "error": "Se necesitan al menos 2 meses de datos para detectar tendencias.",
            }

        # Calcular direccion y cambio porcentual
        primer_valor = float(monthly["total"].iloc[0])
        ultimo_valor = float(monthly["total"].iloc[-1])

        if primer_valor == 0:
            cambio_pct = 0.0
        else:
            cambio_pct = round(((ultimo_valor - primer_valor) / abs(primer_valor)) * 100, 2)

        if cambio_pct > 5:
            direction = "subiendo"
        elif cambio_pct < -5:
            direction = "bajando"
        else:
            direction = "estable"

        # Linea de tendencia lineal (polyfit grado 1)
        x_values = np.arange(len(monthly), dtype=float)
        y_values = monthly["total"].values.astype(float)
        coeffs = np.polyfit(x_values, y_values, 1)
        pendiente = round(float(coeffs[0]), 2)
        intercepto = round(float(coeffs[1]), 2)

        # Datos mensuales para grafica
        monthly_data = []
        for _, row in monthly.iterrows():
            monthly_data.append({
                "mes": str(row["periodo"]),
                "total": round(float(row["total"]), 2),
                "promedio": round(float(row["promedio"]), 2),
                "registros": int(row["registros"]),
            })

        # Chart config para el frontend
        chart_config = {
            "chart_type": "line",
            "title": f"Tendencia de {value_column.replace('_', ' ').title()} por Mes",
            "data": monthly_data,
            "config": {
                "x_key": "mes",
                "y_key": "total",
                "color": "#3b82f6",
            },
        }

        result = {
            "table_name": table_name,
            "value_column": value_column,
            "direction": direction,
            "cambio_porcentual": cambio_pct,
            "meses_analizados": len(monthly),
            "monthly_data": monthly_data,
            "trend_line": {
                "pendiente": pendiente,
                "intercepto": intercepto,
            },
            "chart_config": chart_config,
        }

        return _clean_nan(result)

    except Exception as e:
        logger.error(f"Error en detect_trends: {e}", exc_info=True)
        return {"error": f"Error al detectar tendencias: {type(e).__name__}"}


# ---------------------------------------------------------------------------
# Tool 2: compare_periods
# ---------------------------------------------------------------------------
def compare_periods(
    org_id: str,
    table_name: str,
    date_column: str,
    value_column: str,
    tool_context: ToolContext,
    period_type: str = "month",
) -> dict:
    """Compara el rendimiento entre periodos consecutivos (meses o semanas).

    Agrupa los datos por el periodo seleccionado y calcula el cambio
    absoluto y porcentual respecto al periodo anterior. Identifica el
    mejor y peor periodo.

    Args:
        org_id: UUID de la organizacion.
        table_name: Nombre de la tabla a analizar (ej: 'ventas').
        date_column: Nombre de la columna de fecha (ej: 'fecha').
        value_column: Nombre de la columna numerica (ej: 'total').
        period_type: Tipo de periodo para agrupar: 'month' o 'week'.

    Returns:
        dict con periods (lista con periodo, valor, cambio, cambio_pct),
        mejor_periodo, peor_periodo, y chart_config.
    """
    _auth_err = validate_org_id(org_id, tool_context)
    if _auth_err:
        return _auth_err
    try:
        df, table_info = _load_table_df(org_id, table_name)
        if df.empty:
            return {"error": f"La tabla '{table_name}' no tiene datos."}

        if date_column not in df.columns:
            return {"error": f"La columna '{date_column}' no existe en la tabla."}
        if value_column not in df.columns:
            return {"error": f"La columna '{value_column}' no existe en la tabla."}

        # Preparar datos
        df[date_column] = pd.to_datetime(df[date_column], errors="coerce")
        df[value_column] = pd.to_numeric(df[value_column], errors="coerce")
        df = df.dropna(subset=[date_column, value_column])

        if df.empty:
            return {"error": "No hay datos validos para comparar periodos."}

        # Agrupar por periodo
        freq = "M" if period_type == "month" else "W"
        df["_periodo"] = df[date_column].dt.to_period(freq)
        grouped = (
            df.groupby("_periodo")[value_column]
            .sum()
            .reset_index()
        )
        grouped.columns = ["periodo", "valor"]
        grouped = grouped.sort_values("periodo")

        if len(grouped) < 2:
            return {"error": "Se necesitan al menos 2 periodos para comparar."}

        # Calcular cambios
        periods_list = []
        for i, row in grouped.iterrows():
            entry = {
                "periodo": str(row["periodo"]),
                "valor": round(float(row["valor"]), 2),
                "cambio": None,
                "cambio_pct": None,
            }
            idx = grouped.index.get_loc(i)
            if idx > 0:
                prev_val = float(grouped.iloc[idx - 1]["valor"])
                curr_val = float(row["valor"])
                cambio = round(curr_val - prev_val, 2)
                cambio_pct = (
                    round((cambio / abs(prev_val)) * 100, 2)
                    if prev_val != 0
                    else 0.0
                )
                entry["cambio"] = cambio
                entry["cambio_pct"] = cambio_pct
            periods_list.append(entry)

        # Mejor y peor periodo
        values_by_period = {str(row["periodo"]): float(row["valor"]) for _, row in grouped.iterrows()}
        mejor = max(values_by_period, key=values_by_period.get)
        peor = min(values_by_period, key=values_by_period.get)

        period_label = "Mes" if period_type == "month" else "Semana"

        chart_config = {
            "chart_type": "bar",
            "title": f"Comparacion de {value_column.replace('_', ' ').title()} por {period_label}",
            "data": [
                {"periodo": p["periodo"], "valor": p["valor"]}
                for p in periods_list
            ],
            "config": {
                "x_key": "periodo",
                "y_key": "valor",
                "color": "#10b981",
            },
        }

        result = {
            "table_name": table_name,
            "value_column": value_column,
            "period_type": period_type,
            "periodos_analizados": len(periods_list),
            "periods": periods_list,
            "mejor_periodo": {
                "periodo": mejor,
                "valor": round(values_by_period[mejor], 2),
            },
            "peor_periodo": {
                "periodo": peor,
                "valor": round(values_by_period[peor], 2),
            },
            "chart_config": chart_config,
        }

        return _clean_nan(result)

    except Exception as e:
        logger.error(f"Error en compare_periods: {e}", exc_info=True)
        return {"error": f"Error al comparar periodos: {type(e).__name__}"}


# ---------------------------------------------------------------------------
# Tool 3: find_anomalies
# ---------------------------------------------------------------------------
def find_anomalies(
    org_id: str,
    table_name: str,
    column: str,
    tool_context: ToolContext,
) -> dict:
    """Detecta valores anomalos (outliers) en una columna numerica usando el metodo IQR.

    Calcula Q1, Q3 y el rango intercuartilico (IQR). Los valores fuera
    del rango [Q1 - 1.5*IQR, Q3 + 1.5*IQR] se consideran anomalias.
    Retorna las anomalias encontradas con su contexto (otras columnas de la fila).

    Args:
        org_id: UUID de la organizacion.
        table_name: Nombre de la tabla a analizar (ej: 'ventas').
        column: Nombre de la columna numerica donde buscar anomalias (ej: 'total').

    Returns:
        dict con anomalies (lista max 20 con valor, tipo alto/bajo, contexto),
        stats (Q1, Q3, IQR, mediana, media), thresholds (limite_inferior, limite_superior),
        total_anomalias, total_registros.
    """
    _auth_err = validate_org_id(org_id, tool_context)
    if _auth_err:
        return _auth_err
    try:
        df, table_info = _load_table_df(org_id, table_name)
        if df.empty:
            return {"error": f"La tabla '{table_name}' no tiene datos."}

        if column not in df.columns:
            return {"error": f"La columna '{column}' no existe en la tabla."}

        # Preparar datos
        df[column] = pd.to_numeric(df[column], errors="coerce")
        valid_mask = df[column].notna()
        if valid_mask.sum() < 4:
            return {"error": "Se necesitan al menos 4 valores numericos para detectar anomalias."}

        series = df.loc[valid_mask, column]

        # Calcular IQR
        q1 = float(series.quantile(0.25))
        q3 = float(series.quantile(0.75))
        iqr = q3 - q1
        limite_inferior = q1 - 1.5 * iqr
        limite_superior = q3 + 1.5 * iqr

        # Encontrar anomalias
        anomaly_mask = (series < limite_inferior) | (series > limite_superior)
        anomaly_df = df.loc[anomaly_mask]

        anomalies = []
        for _, row in anomaly_df.head(20).iterrows():
            valor = float(row[column])
            tipo = "alto" if valor > limite_superior else "bajo"

            # Contexto: otras columnas de la fila (excluyendo la analizada)
            contexto = {}
            for col in df.columns:
                if col == column:
                    continue
                val = row[col]
                if isinstance(val, float) and pd.isna(val):
                    contexto[col] = None
                else:
                    contexto[col] = val

            anomalies.append({
                "valor": round(valor, 2),
                "tipo": tipo,
                "contexto": contexto,
            })

        stats = {
            "q1": round(q1, 2),
            "q3": round(q3, 2),
            "iqr": round(iqr, 2),
            "mediana": round(float(series.median()), 2),
            "media": round(float(series.mean()), 2),
            "desviacion_estandar": round(float(series.std()), 2),
        }

        thresholds = {
            "limite_inferior": round(limite_inferior, 2),
            "limite_superior": round(limite_superior, 2),
        }

        result = {
            "table_name": table_name,
            "column": column,
            "total_registros": int(valid_mask.sum()),
            "total_anomalias": int(anomaly_mask.sum()),
            "anomalies": anomalies,
            "stats": stats,
            "thresholds": thresholds,
        }

        return _clean_nan(result)

    except Exception as e:
        logger.error(f"Error en find_anomalies: {e}", exc_info=True)
        return {"error": f"Error al buscar anomalias: {type(e).__name__}"}


# ---------------------------------------------------------------------------
# Tool 4: generate_report
# ---------------------------------------------------------------------------
def generate_report(
    org_id: str,
    report_type: str,
    tool_context: ToolContext,
    table_name: str = "",
    date_from: str = "",
    date_to: str = "",
) -> dict:
    """Genera un reporte analitico con metricas, secciones y graficas.

    Recopila datos de las tablas relevantes de la organizacion, calcula
    metricas clave y genera configuraciones de graficas listas para
    renderizar. El agente LLM complementa con recomendaciones.

    Args:
        org_id: UUID de la organizacion.
        report_type: Tipo de reporte. Opciones:
            'resumen_general' - vision completa del negocio,
            'ventas' - analisis de ventas,
            'inventario' - estado del inventario,
            'clientes' - analisis de clientes,
            'financiero' - resumen financiero.
        table_name: Tabla especifica a analizar (opcional, se detecta automaticamente).
        date_from: Fecha inicio filtro ISO (yyyy-mm-dd, opcional).
        date_to: Fecha fin filtro ISO (yyyy-mm-dd, opcional).

    Returns:
        dict con title, report_type, metrics (lista de KPIs), sections (lista
        de hallazgos), charts (lista de chart_configs), recommendations (vacia,
        el LLM la llena).
    """
    _auth_err = validate_org_id(org_id, tool_context)
    if _auth_err:
        return _auth_err
    try:
        # Obtener info de la organizacion desde main DB
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
        org_name = org.get("name", "Empresa")
        bt_display = org.get("bt_display", "General")

        # Obtener todas las tablas de la org
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
                all_tables_list = cur.fetchall()

        all_tables = {t["table_name"]: dict(t) for t in all_tables_list}

        # Determinar tablas relevantes segun report_type
        report_table_map = {
            "ventas": ["ventas", "facturas", "pedidos"],
            "inventario": ["productos", "inventario", "inventario_movimientos"],
            "clientes": ["clientes", "cotizaciones"],
            "financiero": ["ventas", "facturas", "gastos", "ingresos"],
            "resumen_general": list(all_tables.keys()),
        }

        target_tables = report_table_map.get(report_type, list(all_tables.keys()))

        # Si se especifica tabla, usarla
        if table_name and table_name in all_tables:
            target_tables = [table_name]

        # Titulos por tipo
        report_titles = {
            "resumen_general": f"Resumen General — {org_name}",
            "ventas": f"Reporte de Ventas — {org_name}",
            "inventario": f"Reporte de Inventario — {org_name}",
            "clientes": f"Reporte de Clientes — {org_name}",
            "financiero": f"Reporte Financiero — {org_name}",
        }

        metrics: list[dict] = []
        sections: list[dict] = []
        charts: list[dict] = []

        for tbl_name in target_tables:
            if tbl_name not in all_tables:
                continue

            tbl_info = all_tables[tbl_name]
            row_count = tbl_info.get("row_count", 0) or 0
            if row_count == 0:
                continue

            # Cargar datos
            df, _ = _load_table_df(org_id, tbl_name)
            if df.empty:
                continue

            # Filtrar por fechas si se proporcionan
            date_cols = [
                c["name"]
                for c in (tbl_info.get("columns_definition") or [])
                if c.get("type") in ("date", "datetime", "timestamp")
            ]
            if date_cols and (date_from or date_to):
                dcol = date_cols[0]
                if dcol in df.columns:
                    df[dcol] = pd.to_datetime(df[dcol], errors="coerce")
                    if date_from:
                        df = df[df[dcol] >= pd.to_datetime(date_from)]
                    if date_to:
                        df = df[df[dcol] <= pd.to_datetime(date_to)]

            if df.empty:
                continue

            # Metrica basica: conteo
            metrics.append({
                "name": f"Total {tbl_info['display_name']}",
                "value": len(df),
                "format": "number",
                "description": f"Registros en {tbl_info['display_name']}",
            })

            # Detectar columnas numericas y calcular metricas
            numeric_cols = []
            for col in df.columns:
                series = pd.to_numeric(df[col], errors="coerce")
                if series.notna().sum() > len(df) * 0.3:
                    numeric_cols.append(col)

            section_findings = []
            for col in numeric_cols:
                series = pd.to_numeric(df[col], errors="coerce").dropna()
                if series.empty:
                    continue

                col_label = col.replace("_", " ").title()

                # Metricas monetarias
                is_monetary = any(
                    kw in col
                    for kw in ["total", "precio", "monto", "valor", "ingreso", "venta", "costo"]
                )
                if is_monetary:
                    metrics.append({
                        "name": f"Total {col_label}",
                        "value": round(float(series.sum()), 2),
                        "format": "currency",
                        "description": f"Suma de {col} en {tbl_name}",
                    })
                    metrics.append({
                        "name": f"Promedio {col_label}",
                        "value": round(float(series.mean()), 2),
                        "format": "currency",
                        "description": f"Promedio de {col} en {tbl_name}",
                    })

                section_findings.append({
                    "columna": col_label,
                    "min": round(float(series.min()), 2),
                    "max": round(float(series.max()), 2),
                    "promedio": round(float(series.mean()), 2),
                })

            if section_findings:
                sections.append({
                    "titulo": f"Analisis de {tbl_info['display_name']}",
                    "tabla": tbl_name,
                    "registros": len(df),
                    "hallazgos": section_findings,
                })

            # Generar graficas
            if numeric_cols and date_cols:
                dcol = date_cols[0]
                ncol = numeric_cols[0]
                if dcol in df.columns and ncol in df.columns:
                    df_chart = df.copy()
                    df_chart[dcol] = pd.to_datetime(df_chart[dcol], errors="coerce")
                    df_chart[ncol] = pd.to_numeric(df_chart[ncol], errors="coerce")
                    df_chart = df_chart.dropna(subset=[dcol, ncol])
                    if not df_chart.empty:
                        df_chart["_mes"] = df_chart[dcol].dt.to_period("M")
                        monthly = df_chart.groupby("_mes")[ncol].sum().reset_index()
                        monthly.columns = ["mes", "valor"]
                        monthly = monthly.sort_values("mes")
                        chart_data = [
                            {"mes": str(row["mes"]), "valor": round(float(row["valor"]), 2)}
                            for _, row in monthly.iterrows()
                        ]
                        if chart_data:
                            charts.append({
                                "chart_type": "line",
                                "title": f"{ncol.replace('_', ' ').title()} por Mes — {tbl_info['display_name']}",
                                "data": chart_data,
                                "config": {
                                    "x_key": "mes",
                                    "y_key": "valor",
                                    "color": "#3b82f6",
                                },
                            })

            # Grafica de top categorias
            cat_cols = [
                c for c in df.columns
                if c not in numeric_cols and c not in date_cols
            ]
            if cat_cols and numeric_cols:
                ccol = cat_cols[0]
                ncol = numeric_cols[0]
                if ccol in df.columns and ncol in df.columns:
                    df[ncol] = pd.to_numeric(df[ncol], errors="coerce")
                    top = df.groupby(ccol)[ncol].sum().nlargest(10).reset_index()
                    top.columns = [ccol, ncol]
                    chart_data_cat = [
                        {ccol: str(row[ccol]), ncol: round(float(row[ncol]), 2)}
                        for _, row in top.iterrows()
                    ]
                    if chart_data_cat:
                        charts.append({
                            "chart_type": "bar",
                            "title": f"Top {ccol.replace('_', ' ').title()} por {ncol.replace('_', ' ').title()}",
                            "data": chart_data_cat,
                            "config": {
                                "x_key": ccol,
                                "y_key": ncol,
                                "color": "#8b5cf6",
                            },
                        })

        # Limitar metricas y charts
        metrics = metrics[:15]
        charts = charts[:8]

        result = {
            "title": report_titles.get(report_type, f"Reporte — {org_name}"),
            "report_type": report_type,
            "org_name": org_name,
            "business_type": bt_display,
            "metrics": metrics,
            "sections": sections,
            "charts": charts,
            "recommendations": [],
        }

        return _clean_nan(result)

    except Exception as e:
        logger.error(f"Error en generate_report: {e}", exc_info=True)
        return {"error": f"Error al generar reporte: {type(e).__name__}"}


# ---------------------------------------------------------------------------
# Tool 5: cross_table_analysis
# ---------------------------------------------------------------------------
def cross_table_analysis(
    org_id: str,
    table_a: str,
    column_a: str,
    table_b: str,
    column_b: str,
    tool_context: ToolContext,
) -> dict:
    """Analiza y compara columnas numericas de dos tablas diferentes.

    Carga datos de ambas tablas, calcula estadisticas descriptivas para
    cada columna y genera una grafica comparativa. Util para correlacionar
    ventas con inventario, clientes con facturacion, etc.

    Args:
        org_id: UUID de la organizacion.
        table_a: Nombre de la primera tabla (ej: 'ventas').
        column_a: Columna numerica de la primera tabla (ej: 'total').
        table_b: Nombre de la segunda tabla (ej: 'productos').
        column_b: Columna numerica de la segunda tabla (ej: 'stock_actual').

    Returns:
        dict con stats_a y stats_b (estadisticas de cada columna),
        comparison (diferencias entre ambas), y chart_config.
    """
    _auth_err = validate_org_id(org_id, tool_context)
    if _auth_err:
        return _auth_err
    try:
        # Cargar ambas tablas
        df_a, info_a = _load_table_df(org_id, table_a)
        if df_a.empty:
            return {"error": f"La tabla '{table_a}' no tiene datos."}

        df_b, info_b = _load_table_df(org_id, table_b)
        if df_b.empty:
            return {"error": f"La tabla '{table_b}' no tiene datos."}

        if column_a not in df_a.columns:
            return {"error": f"La columna '{column_a}' no existe en '{table_a}'."}
        if column_b not in df_b.columns:
            return {"error": f"La columna '{column_b}' no existe en '{table_b}'."}

        # Convertir a numerico
        series_a = pd.to_numeric(df_a[column_a], errors="coerce").dropna()
        series_b = pd.to_numeric(df_b[column_b], errors="coerce").dropna()

        if series_a.empty:
            return {"error": f"La columna '{column_a}' no tiene valores numericos."}
        if series_b.empty:
            return {"error": f"La columna '{column_b}' no tiene valores numericos."}

        # Estadisticas de cada columna
        def _calc_stats(series: pd.Series, name: str, table: str) -> dict:
            return {
                "tabla": table,
                "columna": name,
                "registros": int(len(series)),
                "suma": round(float(series.sum()), 2),
                "promedio": round(float(series.mean()), 2),
                "mediana": round(float(series.median()), 2),
                "min": round(float(series.min()), 2),
                "max": round(float(series.max()), 2),
                "desviacion_estandar": round(float(series.std()), 2),
            }

        stats_a = _calc_stats(series_a, column_a, table_a)
        stats_b = _calc_stats(series_b, column_b, table_b)

        # Comparacion
        comparison = {
            "diferencia_promedio": round(stats_a["promedio"] - stats_b["promedio"], 2),
            "ratio_sumas": (
                round(stats_a["suma"] / stats_b["suma"], 4)
                if stats_b["suma"] != 0
                else None
            ),
            "tabla_mayor_promedio": table_a if stats_a["promedio"] >= stats_b["promedio"] else table_b,
        }

        # Grafica comparativa
        chart_data = [
            {
                "metrica": "Suma",
                f"{table_a}.{column_a}": stats_a["suma"],
                f"{table_b}.{column_b}": stats_b["suma"],
            },
            {
                "metrica": "Promedio",
                f"{table_a}.{column_a}": stats_a["promedio"],
                f"{table_b}.{column_b}": stats_b["promedio"],
            },
            {
                "metrica": "Mediana",
                f"{table_a}.{column_a}": stats_a["mediana"],
                f"{table_b}.{column_b}": stats_b["mediana"],
            },
            {
                "metrica": "Maximo",
                f"{table_a}.{column_a}": stats_a["max"],
                f"{table_b}.{column_b}": stats_b["max"],
            },
        ]

        chart_config = {
            "chart_type": "bar",
            "title": f"Comparacion: {column_a.replace('_', ' ').title()} vs {column_b.replace('_', ' ').title()}",
            "data": chart_data,
            "config": {
                "x_key": "metrica",
                "y_key": f"{table_a}.{column_a}",
                "color": "#3b82f6",
            },
        }

        result = {
            "stats_a": stats_a,
            "stats_b": stats_b,
            "comparison": comparison,
            "chart_config": chart_config,
        }

        return _clean_nan(result)

    except Exception as e:
        logger.error(f"Error en cross_table_analysis: {e}", exc_info=True)
        return {"error": f"Error al analizar tablas cruzadas: {type(e).__name__}"}
