"""Servicio de analisis avanzado — puente entre FastAPI y AnalyticalAgent."""

import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone

from app.database import get_org_pool

logger = logging.getLogger(__name__)


async def process_analytical_query(
    org_id: str,
    user_id: str,
    query: str,
    report_type: str = "",
) -> dict:
    """Procesa una consulta analitica a traves del AnalyticalAgent.

    Intenta el pipeline ADK primero. Si no esta disponible, cae al
    fallback directo con Gemini.
    """
    pool = await get_org_pool(org_id)
    now = datetime.now(timezone.utc)
    user_msg_id = str(uuid.uuid4())

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO chat_messages (id, user_id, role, content, created_at)
            VALUES ($1, $2, 'user', $3, $4)
            """,
            user_msg_id,
            user_id,
            query,
            now,
        )

    try:
        agents_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "agents")
        )
        if agents_path not in sys.path:
            sys.path.insert(0, agents_path)

        from pipeline import run_analytical  # type: ignore[import]

        result = await run_analytical(
            message=query,
            org_id=org_id,
            user_id=user_id,
        )
        ai_response: str = result.get("response", "No se pudo generar el analisis.")
    except ImportError:
        ai_response = await _fallback_analysis(org_id, query, report_type)
    except Exception as exc:
        logger.error("Error en analytical pipeline: %s", exc)
        ai_response = await _fallback_analysis(org_id, query, report_type)

    assistant_msg_id = str(uuid.uuid4())
    completed_at = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO chat_messages (id, user_id, role, content, created_at)
            VALUES ($1, $2, 'assistant', $3, $4)
            """,
            assistant_msg_id,
            user_id,
            ai_response,
            completed_at,
        )

    return {
        "message_id": assistant_msg_id,
        "role": "assistant",
        "content": ai_response,
        "created_at": completed_at.isoformat(),
    }


async def _fallback_analysis(
    org_id: str, query: str, report_type: str
) -> str:
    """Genera analisis local sin LLM, o usa Gemini si API key disponible."""
    from app.config import get_settings

    pool = await get_org_pool(org_id)
    settings = get_settings()

    async with pool.acquire() as conn:
        table_rows = await conn.fetch(
            "SELECT table_name, display_name, row_count FROM org_data_tables"
        )
        tables = [dict(r) for r in table_rows]
        total_records = sum((t.get("row_count") or 0) for t in tables)
        tables_with_data = [t for t in tables if (t.get("row_count") or 0) > 0]

        jobs = await conn.fetch(
            "SELECT status, rows_loaded, filename FROM etl_jobs ORDER BY created_at DESC LIMIT 10"
        )

    # Si hay API key, usar Gemini
    if settings.GOOGLE_API_KEY and settings.GOOGLE_API_KEY != "tu-google-api-key":
        try:
            from google import genai
            client = genai.Client(api_key=settings.GOOGLE_API_KEY)
            context = f"Tablas: {len(tables)}, Registros: {total_records}"
            prompt = f"Analista de datos PYME. Datos:\n{context}\nConsulta: {query}"
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
            )
            return response.text or "No se pudo generar respuesta."
        except Exception as exc:
            logger.error("Gemini error: %s", exc)

    # Respuesta local basada en tipo de analisis
    tables_info = "\n".join(f"- {t['display_name']}: {t.get('row_count', 0)} registros" for t in tables)
    query_lower = query.lower()

    if report_type == "resumen" or "resumen" in query_lower:
        return (
            f"**Resumen General de la Empresa**\n\n"
            f"Tablas configuradas: {len(tables)}\n"
            f"Tablas con datos: {len(tables_with_data)}\n"
            f"Total de registros: {total_records}\n"
            f"ETL jobs ejecutados: {len(jobs)}\n\n"
            f"**Detalle por tabla:**\n{tables_info}\n\n"
            f"{'Los datos estan listos para analisis.' if total_records > 0 else 'Aun no hay datos cargados. Suba archivos CSV/Excel para comenzar.'}"
        )

    if "venta" in query_lower:
        return (
            f"**Analisis de Ventas**\n\n"
            f"Estado actual de datos:\n{tables_info}\n\n"
            f"{'Para un analisis detallado de ventas, cargue datos de ventas via el ChatBot.' if total_records == 0 else f'Hay {total_records} registros disponibles para analizar.'}\n\n"
            "KPIs sugeridos para ventas:\n"
            "- Ventas totales por periodo\n"
            "- Producto mas vendido\n"
            "- Ticket promedio\n"
            "- Tendencia mensual"
        )

    if "anomal" in query_lower:
        return (
            f"**Deteccion de Anomalias**\n\n"
            f"Datos disponibles: {total_records} registros en {len(tables)} tablas\n\n"
            f"{'No se detectaron anomalias — no hay datos cargados aun.' if total_records == 0 else 'Analisis de anomalias requiere al menos 30 registros por tabla.'}\n\n"
            "Tipos de anomalias detectables:\n"
            "- Valores atipicos en precios/cantidades\n"
            "- Registros duplicados\n"
            "- Fechas inconsistentes\n"
            "- Datos faltantes criticos"
        )

    if "compar" in query_lower or "periodo" in query_lower:
        return (
            f"**Comparacion de Periodos**\n\n"
            f"Datos disponibles: {total_records} registros\n"
            f"Tablas: {len(tables)}\n\n"
            "Para comparar periodos necesitas datos con fechas. "
            "Carga ventas o transacciones con columna de fecha para habilitar esta funcion.\n\n"
            "Comparaciones disponibles:\n"
            "- Mes actual vs mes anterior\n"
            "- Trimestre actual vs anterior\n"
            "- Year-over-year"
        )

    if "reporte" in query_lower or "financ" in query_lower:
        return (
            f"**Reporte Financiero**\n\n"
            f"Empresa: Datos de {len(tables)} tablas\n"
            f"Registros totales: {total_records}\n"
            f"Ultima carga ETL: {'Ninguna' if not jobs else jobs[0].get('filename', 'N/A')}\n\n"
            "Secciones del reporte:\n"
            "1. Resumen ejecutivo\n"
            "2. Ingresos y gastos\n"
            "3. Productos/servicios principales\n"
            "4. Tendencias\n"
            "5. Recomendaciones\n\n"
            f"{'Cargue datos financieros para generar el reporte completo.' if total_records == 0 else 'Reporte basado en datos disponibles.'}"
        )

    # Default
    return (
        f"**Analisis: {query}**\n\n"
        f"Datos disponibles:\n{tables_info}\n"
        f"Total registros: {total_records}\n\n"
        "Para un analisis mas detallado, cargue datos y especifique el tipo de analisis deseado."
    )


async def get_org_analytics_summary(org_id: str) -> dict:
    """Genera un resumen analitico rapido de la org (sin LLM)."""
    pool = await get_org_pool(org_id)

    async with pool.acquire() as conn:
        table_rows = await conn.fetch(
            "SELECT id, table_name, display_name, row_count, columns_definition FROM org_data_tables"
        )
        tables = [dict(r) for r in table_rows]

        job_rows = await conn.fetch(
            """
            SELECT status, rows_loaded, completed_at
            FROM etl_jobs
            ORDER BY created_at DESC
            LIMIT 10
            """
        )
        jobs = [dict(r) for r in job_rows]

    total_records = sum((t.get("row_count") or 0) for t in tables)
    tables_with_data = [t for t in tables if (t.get("row_count") or 0) > 0]
    completed_jobs = [j for j in jobs if j["status"] == "completed"]

    return {
        "total_records": total_records,
        "total_tables": len(tables),
        "tables_with_data": len(tables_with_data),
        "tables": [
            {
                "name": t["table_name"],
                "display_name": t["display_name"],
                "row_count": t.get("row_count") or 0,
            }
            for t in tables
        ],
        "etl_jobs_completed": len(completed_jobs),
        "total_rows_loaded": sum(j.get("rows_loaded") or 0 for j in completed_jobs),
    }
