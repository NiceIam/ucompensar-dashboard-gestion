"""
DataAnalyzerAgent — Agente 2 del pipeline.

Analiza los datos limpios: estadisticas descriptivas, tendencias,
correlaciones y categorias principales. Opera directamente sobre PostgreSQL.
"""

import json
import logging
from itertools import combinations

import numpy as np
import pandas as pd
from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext

from agents.config import (
    GEMINI_MODEL,
    AGENT_TEMPERATURES,
    get_org_conn,
    with_retry,
)

logger = logging.getLogger("agents.data_analyzer")

MAX_RECORDS = 10_000


# ---------------------------------------------------------------------------
# Tool: analyze_data
# ---------------------------------------------------------------------------
def analyze_data(file_id: str, org_id: str, tool_context: ToolContext) -> dict:
    """Analiza los datos limpios de un archivo y genera estadisticas,
    tendencias, correlaciones y categorias principales.

    Lee los datos directamente de PostgreSQL (tabla data_records) y utiliza
    la informacion del DataCleanerAgent (columnas numericas, de fecha, etc.)
    disponible en el state del pipeline.

    Args:
        file_id: UUID del archivo a analizar.
        org_id: UUID de la organizacion propietaria.

    Returns:
        dict con descriptive_stats, trends, correlations, top_categories
        y period_comparison cuando hay columnas de fecha.
    """
    try:
        # Obtener metadata del cleaner
        cleaner_output = tool_context.state.get("cleaner_output", {})
        if isinstance(cleaner_output, str):
            try:
                cleaner_output = json.loads(cleaner_output)
            except (json.JSONDecodeError, TypeError):
                cleaner_output = {}

        numeric_columns = cleaner_output.get("numeric_columns", [])
        date_columns = cleaner_output.get("date_columns", [])
        columns_detected = cleaner_output.get("columns_detected", [])

        # Cargar datos limpios de PostgreSQL
        with get_org_conn(org_id) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT data FROM data_records
                    WHERE file_id = %s AND org_id = %s AND data IS NOT NULL
                    ORDER BY row_number
                    LIMIT %s
                    """,
                    (file_id, org_id, MAX_RECORDS),
                )
                records = cur.fetchall()

        if not records:
            return {"error": "No se encontraron registros limpios para analizar."}

        df = pd.DataFrame([r["data"] for r in records])
        total_rows = len(df)

        # -------------------------------------------------------------------
        # 1. Estadisticas descriptivas por columna numerica
        # -------------------------------------------------------------------
        descriptive_stats: list[dict] = []

        # Si no tenemos metadata del cleaner, detectar numericas
        if not numeric_columns:
            for col in df.columns:
                try:
                    pd.to_numeric(df[col], errors="raise")
                    numeric_columns.append(col)
                except (ValueError, TypeError):
                    pass

        for col in numeric_columns:
            if col not in df.columns:
                continue
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            if series.empty:
                continue
            descriptive_stats.append({
                "column": col,
                "min": round(float(series.min()), 2),
                "max": round(float(series.max()), 2),
                "mean": round(float(series.mean()), 2),
                "median": round(float(series.median()), 2),
                "std": round(float(series.std()), 2),
                "p25": round(float(series.quantile(0.25)), 2),
                "p75": round(float(series.quantile(0.75)), 2),
            })

        # -------------------------------------------------------------------
        # 2. Correlaciones entre columnas numericas
        # -------------------------------------------------------------------
        correlations: list[dict] = []
        if len(numeric_columns) >= 2:
            numeric_df = df[
                [c for c in numeric_columns if c in df.columns]
            ].apply(pd.to_numeric, errors="coerce")
            corr_matrix = numeric_df.corr(method="pearson")

            for col_a, col_b in combinations(numeric_df.columns, 2):
                r = corr_matrix.loc[col_a, col_b]
                if pd.isna(r):
                    continue
                abs_r = abs(r)
                strength = (
                    "fuerte" if abs_r >= 0.7
                    else "moderada" if abs_r >= 0.4
                    else "debil"
                )
                # Solo reportar correlaciones moderadas o fuertes
                if abs_r >= 0.4:
                    correlations.append({
                        "column_a": col_a,
                        "column_b": col_b,
                        "pearson_r": round(float(r), 3),
                        "strength": strength,
                    })

        # -------------------------------------------------------------------
        # 3. Tendencias temporales
        # -------------------------------------------------------------------
        trends: list[dict] = []

        # Si no tenemos metadata, detectar columnas de fecha
        if not date_columns:
            for col in df.columns:
                if col in numeric_columns:
                    continue
                try:
                    pd.to_datetime(df[col].dropna().head(50), infer_datetime_format=True)
                    date_columns.append(col)
                except (ValueError, TypeError):
                    pass

        for date_col in date_columns:
            if date_col not in df.columns:
                continue
            try:
                df_temp = df.copy()
                df_temp[date_col] = pd.to_datetime(df_temp[date_col], errors="coerce")
                df_temp = df_temp.dropna(subset=[date_col])
                if df_temp.empty:
                    continue

                df_temp = df_temp.sort_values(date_col)

                for val_col in numeric_columns:
                    if val_col not in df_temp.columns:
                        continue
                    series = pd.to_numeric(df_temp[val_col], errors="coerce").dropna()
                    if len(series) < 4:
                        continue

                    # Dividir en primera y segunda mitad
                    mid = len(series) // 2
                    first_half = series.iloc[:mid].mean()
                    second_half = series.iloc[mid:].mean()

                    if first_half == 0:
                        continue

                    pct_change = ((second_half - first_half) / abs(first_half)) * 100
                    direction = (
                        "up" if pct_change > 5
                        else "down" if pct_change < -5
                        else "stable"
                    )

                    trends.append({
                        "date_column": date_col,
                        "value_column": val_col,
                        "direction": direction,
                        "percentage_change": round(float(pct_change), 2),
                    })
            except Exception as e:
                logger.warning(f"Error analizando tendencia {date_col}: {e}")

        # -------------------------------------------------------------------
        # 4. Top categorias para columnas categoricas
        # -------------------------------------------------------------------
        top_categories: dict[str, list[dict]] = {}
        categorical_cols = [
            c for c in columns_detected or df.columns
            if c not in numeric_columns
            and c not in date_columns
            and c in df.columns
        ]

        for col in categorical_cols:
            value_counts = df[col].value_counts().head(10)
            if not value_counts.empty:
                top_categories[col] = [
                    {"value": str(val), "count": int(count)}
                    for val, count in value_counts.items()
                ]

        # -------------------------------------------------------------------
        # 5. Comparacion de periodos (si hay fechas)
        # -------------------------------------------------------------------
        period_comparison = None
        if date_columns and numeric_columns:
            date_col = date_columns[0]
            try:
                df_pc = df.copy()
                df_pc[date_col] = pd.to_datetime(df_pc[date_col], errors="coerce")
                df_pc = df_pc.dropna(subset=[date_col])
                if not df_pc.empty:
                    date_range = df_pc[date_col].max() - df_pc[date_col].min()
                    mid_date = df_pc[date_col].min() + date_range / 2
                    first_period = df_pc[df_pc[date_col] <= mid_date]
                    second_period = df_pc[df_pc[date_col] > mid_date]

                    comparison = {}
                    for val_col in numeric_columns[:5]:
                        if val_col not in df_pc.columns:
                            continue
                        fp_mean = pd.to_numeric(
                            first_period[val_col], errors="coerce"
                        ).mean()
                        sp_mean = pd.to_numeric(
                            second_period[val_col], errors="coerce"
                        ).mean()
                        if pd.notna(fp_mean) and pd.notna(sp_mean):
                            comparison[val_col] = {
                                "first_period_avg": round(float(fp_mean), 2),
                                "second_period_avg": round(float(sp_mean), 2),
                            }

                    if comparison:
                        period_comparison = {
                            "date_column": date_col,
                            "split_date": str(mid_date.date()),
                            "metrics": comparison,
                        }
            except Exception as e:
                logger.warning(f"Error en period_comparison: {e}")

        # -------------------------------------------------------------------
        # Resultado final
        # -------------------------------------------------------------------
        result = {
            "file_id": file_id,
            "org_id": org_id,
            "total_rows": total_rows,
            "descriptive_stats": descriptive_stats,
            "trends": trends,
            "correlations": correlations,
            "top_categories": top_categories,
            "period_comparison": period_comparison,
        }

        tool_context.state["analyzer_output"] = result
        return result

    except Exception as e:
        logger.error(f"Error en analyze_data: {e}", exc_info=True)
        return {"error": f"Error al analizar datos: {str(e)}"}


# ---------------------------------------------------------------------------
# Definicion del agente
# ---------------------------------------------------------------------------
data_analyzer_agent = LlmAgent(
    model=GEMINI_MODEL,
    name="DataAnalyzerAgent",
    description="Agente especializado en analisis estadistico de datos empresariales.",
    instruction="""Eres un analista de datos de negocios especializado en PYMES.
Tu tarea es analizar los datos limpios y generar un analisis estadistico completo.

Contexto disponible:
- El DataCleanerAgent ya limpio los datos. Su resumen esta en state["cleaner_output"].
- Usa esa informacion para saber que columnas son numericas, de fecha, etc.

Proceso obligatorio:
1. Usa la herramienta analyze_data con el file_id y org_id del mensaje.
2. La herramienta calcula: estadisticas descriptivas, correlaciones, tendencias
   temporales y categorias principales.
3. Presenta los hallazgos mas relevantes de forma clara y concisa.

Reglas:
- Siempre responde en Espanol.
- Destaca las correlaciones fuertes y tendencias significativas.
- Menciona los top 3-5 hallazgos mas relevantes para un directivo de PYME.
- No inventes datos: solo reporta lo que la herramienta calculo.
""",
    tools=[analyze_data],
    output_key="analyzer_output",
    generate_content_config={
        "temperature": AGENT_TEMPERATURES["data_analyzer"],
    },
)
