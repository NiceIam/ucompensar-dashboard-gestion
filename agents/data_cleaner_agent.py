"""
DataCleanerAgent — Agente 1 del pipeline.

Limpia, deduplica y normaliza los datos crudos de un archivo subido.
Opera directamente sobre PostgreSQL (no pasa records al LLM).
Retorna un resumen de la limpieza al state del pipeline.
"""

import json
import logging
from datetime import datetime

import numpy as np
import pandas as pd
from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext
from psycopg2.extras import Json

from agents.config import (
    GEMINI_MODEL,
    AGENT_TEMPERATURES,
    get_org_conn,
    with_retry,
)

logger = logging.getLogger("agents.data_cleaner")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
MAX_RECORDS = 10_000
BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# Tool: clean_data
# ---------------------------------------------------------------------------
def clean_data(file_id: str, org_id: str, tool_context: ToolContext) -> dict:
    """Limpia los datos de un archivo: elimina duplicados, maneja nulos,
    normaliza formatos de fecha y montos, detecta outliers.

    Opera directamente sobre la tabla data_records en la BD de la org.
    NO retorna los registros completos, solo un resumen estadistico
    para que el agente comprenda el resultado de la limpieza.

    Args:
        file_id: UUID del archivo cuyos registros se van a limpiar.
        org_id: UUID de la organizacion propietaria del archivo.

    Returns:
        dict con resumen: original_row_count, cleaned_row_count,
        duplicates_removed, nulls_report, outliers_report,
        quality_score, columns_detected, date_columns, numeric_columns.
    """
    try:
        with get_org_conn(org_id) as conn:
            with conn.cursor() as cur:
                # 1. Verificar que el archivo pertenece a la org
                cur.execute(
                    """
                    SELECT id, filename, rows_count, status
                    FROM uploaded_files
                    WHERE id = %s AND org_id = %s AND deleted_at IS NULL
                    """,
                    (file_id, org_id),
                )
                file_row = cur.fetchone()
                if not file_row:
                    return {"error": f"Archivo {file_id} no encontrado para org {org_id}"}

                # 2. Cargar todos los registros (max 10K)
                cur.execute(
                    """
                    SELECT id, row_number, data
                    FROM data_records
                    WHERE file_id = %s AND org_id = %s
                    ORDER BY row_number
                    LIMIT %s
                    """,
                    (file_id, org_id, MAX_RECORDS),
                )
                records = cur.fetchall()

        if not records:
            return {"error": "No se encontraron registros para este archivo."}

        original_row_count = len(records)
        record_ids = [str(r["id"]) for r in records]
        df = pd.DataFrame([r["data"] for r in records])
        df["_record_id"] = record_ids

        # 3. Detectar tipos de columnas
        columns_detected = [c for c in df.columns if c != "_record_id"]
        date_columns: list[str] = []
        numeric_columns: list[str] = []
        currency_columns: list[str] = []

        for col in columns_detected:
            sample = df[col].dropna().head(50)
            if sample.empty:
                continue

            # Intentar detectar fechas
            try:
                pd.to_datetime(sample, infer_datetime_format=True)
                date_columns.append(col)
                continue
            except (ValueError, TypeError):
                pass

            # Intentar detectar montos/currency (con $, puntos de miles, etc.)
            str_sample = sample.astype(str)
            if str_sample.str.match(r"^[\$\s]*[\d.,]+$").mean() > 0.7:
                currency_columns.append(col)
                continue

            # Intentar numerico
            try:
                pd.to_numeric(sample)
                numeric_columns.append(col)
            except (ValueError, TypeError):
                pass

        # 4. Eliminar duplicados exactos
        mask_dup = df.drop(columns=["_record_id"]).duplicated(keep="first")
        duplicates_removed = int(mask_dup.sum())
        dup_record_ids = df.loc[mask_dup, "_record_id"].tolist()
        df = df[~mask_dup].copy()

        # Soft-delete duplicados en PostgreSQL
        if dup_record_ids:
            with get_org_conn(org_id) as conn:
                with conn.cursor() as cur:
                    for i in range(0, len(dup_record_ids), BATCH_SIZE):
                        batch = dup_record_ids[i : i + BATCH_SIZE]
                        cur.execute(
                            "UPDATE data_records SET data = NULL WHERE id = ANY(%s)",
                            (batch,),
                        )
                conn.commit()

        # 5. Manejar valores nulos
        nulls_report: list[dict] = []
        for col in columns_detected:
            null_count = int(df[col].isna().sum())
            if null_count == 0:
                nulls_report.append({
                    "column": col,
                    "null_count": 0,
                    "strategy_applied": "sin_nulls",
                })
                continue

            strategy = "eliminado"
            if col in numeric_columns or col in currency_columns:
                median_val = pd.to_numeric(df[col], errors="coerce").median()
                if pd.notna(median_val):
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(median_val)
                    strategy = "media"
            elif col in date_columns:
                # No rellenar fechas, dejar nulas
                strategy = "sin_cambio"
            else:
                # Categoricas: rellenar con moda si existe
                mode_val = df[col].mode()
                if not mode_val.empty:
                    df[col] = df[col].fillna(mode_val.iloc[0])
                    strategy = "moda"

            nulls_report.append({
                "column": col,
                "null_count": null_count,
                "strategy_applied": strategy,
            })

        # 6. Normalizar fechas a ISO 8601
        for col in date_columns:
            try:
                df[col] = pd.to_datetime(df[col], infer_datetime_format=True).dt.strftime(
                    "%Y-%m-%d"
                )
            except Exception:
                logger.warning(f"No se pudo normalizar la columna de fecha: {col}")

        # 7. Normalizar montos (quitar $, puntos de miles, convertir a float)
        for col in currency_columns:
            try:
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.replace(r"[\$\s]", "", regex=True)
                    .str.replace(".", "", regex=False)
                    .str.replace(",", ".", regex=False)
                )
                df[col] = pd.to_numeric(df[col], errors="coerce")
                if col not in numeric_columns:
                    numeric_columns.append(col)
            except Exception:
                logger.warning(f"No se pudo normalizar la columna de montos: {col}")

        # 8. Detectar outliers (IQR) en columnas numericas
        outliers_report: list[dict] = []
        all_numeric = list(set(numeric_columns + currency_columns))
        for col in all_numeric:
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(series) < 10:
                continue
            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            outlier_mask = (series < lower) | (series > upper)
            outlier_count = int(outlier_mask.sum())
            if outlier_count > 0:
                outlier_indices = series[outlier_mask].index.tolist()[:20]
                outliers_report.append({
                    "column": col,
                    "outlier_count": outlier_count,
                    "outlier_row_indices": outlier_indices,
                })

        # 9. Actualizar registros limpios en PostgreSQL
        cleaned_records = df.drop(columns=["_record_id"])
        remaining_ids = df["_record_id"].tolist()

        with get_org_conn(org_id) as conn:
            with conn.cursor() as cur:
                for i, (rec_id, row) in enumerate(
                    zip(remaining_ids, cleaned_records.to_dict("records"))
                ):
                    # Convertir NaN/NaT a None para JSON
                    clean_row = {
                        k: (None if pd.isna(v) else v) for k, v in row.items()
                    }
                    cur.execute(
                        "UPDATE data_records SET data = %s WHERE id = %s",
                        (Json(clean_row), rec_id),
                    )

                # 10. Actualizar status del archivo
                cur.execute(
                    "UPDATE uploaded_files SET status = %s, processed_at = NOW() WHERE id = %s",
                    ("ready", file_id),
                )
            conn.commit()

        # 11. Calcular quality score
        total_issues = duplicates_removed + sum(
            n["null_count"] for n in nulls_report if n["strategy_applied"] != "sin_nulls"
        )
        quality_score = max(0.0, min(1.0, 1.0 - (total_issues / max(original_row_count, 1))))

        cleaned_row_count = len(df)

        # 12. Guardar resumen en el state del pipeline
        result = {
            "file_id": file_id,
            "org_id": org_id,
            "original_row_count": original_row_count,
            "cleaned_row_count": cleaned_row_count,
            "duplicates_removed": duplicates_removed,
            "nulls_report": nulls_report,
            "outliers_report": outliers_report,
            "quality_score": round(quality_score, 3),
            "columns_detected": columns_detected,
            "date_columns": date_columns,
            "numeric_columns": list(set(numeric_columns)),
            "currency_columns": currency_columns,
            "warnings": [],
        }

        if quality_score < 0.5:
            result["warnings"].append(
                "La calidad de los datos es baja. Revise el archivo original."
            )

        # Guardar en state para el siguiente agente
        tool_context.state["cleaner_output"] = result

        return result

    except Exception as e:
        logger.error(f"Error en clean_data: {e}", exc_info=True)
        return {"error": f"Error al limpiar datos: {str(e)}"}


# ---------------------------------------------------------------------------
# Definicion del agente
# ---------------------------------------------------------------------------
data_cleaner_agent = LlmAgent(
    model=GEMINI_MODEL,
    name="DataCleanerAgent",
    description="Agente especializado en limpieza y normalizacion de datos empresariales.",
    instruction="""Eres un especialista en limpieza de datos para PYMES colombianas.
Tu tarea es validar, limpiar y normalizar los datos del archivo subido por el usuario.

Proceso obligatorio:
1. Usa la herramienta clean_data con el file_id y org_id proporcionados en el mensaje.
2. La herramienta se encarga de: eliminar duplicados, manejar nulos, normalizar fechas
   y montos, detectar outliers.
3. Analiza el resumen que retorna la herramienta y comunica los resultados al usuario.

Reglas:
- Siempre responde en Espanol.
- No inventes datos. Solo reporta lo que la herramienta encontro.
- Si hay advertencias (quality_score < 0.5), mencionalas claramente.
- Sé conciso: reporta las metricas clave (filas antes/despues, duplicados, nulos, calidad).
""",
    tools=[clean_data],
    output_key="cleaner_output",
    generate_content_config={
        "temperature": AGENT_TEMPERATURES["data_cleaner"],
    },
)
