"""Agent Tools — Superpoderes del Asistente IA.

Herramientas que Gemini puede invocar para responder preguntas sobre los datos:
1. query_data: Ejecutar SQL sobre los datos de la org
2. analyze_table: Análisis estadístico de una tabla
3. create_chart: Generar config de gráfico Recharts
4. manage_data: CRUD de tablas y registros
"""

import json
import logging
from typing import Any

from app.config import get_settings
from app.database import get_org_pool, get_main_pool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool: Query Data (SQL sobre org_data_rows)
# ---------------------------------------------------------------------------

async def query_data(org_id: str, question: str) -> dict:
    """Busca datos relevantes en todas las tablas de la org."""
    pool = await get_org_pool(org_id)

    async with pool.acquire() as conn:
        tables = await conn.fetch(
            "SELECT id, table_name, display_name, row_count, columns_definition FROM org_data_tables"
        )

    # Buscar en todas las tablas con datos
    results = {}
    question_lower = question.lower()

    for t in tables:
        if (t["row_count"] or 0) == 0:
            continue

        cols = t["columns_definition"]
        if isinstance(cols, str):
            cols = json.loads(cols)

        # Determinar si esta tabla es relevante a la pregunta
        table_keywords = [t["table_name"], t["display_name"].lower()]
        for c in cols:
            table_keywords.append(c["name"])

        is_relevant = any(kw in question_lower for kw in table_keywords)
        if not is_relevant and len([t2 for t2 in tables if (t2["row_count"] or 0) > 0]) <= 4:
            is_relevant = True  # Si pocas tablas, buscar en todas

        if not is_relevant:
            continue

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT data FROM org_data_rows WHERE table_id = $1 LIMIT 1000",
                t["id"],
            )

        data = []
        for r in rows:
            d = r["data"]
            if isinstance(d, str):
                try:
                    d = json.loads(d)
                except (json.JSONDecodeError, TypeError):
                    continue
            if isinstance(d, dict):
                data.append(d)

        results[t["display_name"]] = {
            "table_name": t["table_name"],
            "row_count": len(data),
            "columns": [c["name"] for c in cols],
            "data": data,
        }

    return results


# ---------------------------------------------------------------------------
# Tool: Analyze Table
# ---------------------------------------------------------------------------

async def analyze_table(org_id: str, table_name: str = None) -> dict:
    """Análisis estadístico completo de una o todas las tablas."""
    pool = await get_org_pool(org_id)

    async with pool.acquire() as conn:
        if table_name:
            tables = await conn.fetch(
                "SELECT id, table_name, display_name, row_count, columns_definition FROM org_data_tables WHERE table_name = $1",
                table_name,
            )
        else:
            tables = await conn.fetch(
                "SELECT id, table_name, display_name, row_count, columns_definition FROM org_data_tables WHERE row_count > 0"
            )

    analysis = {}
    for t in tables:
        cols = t["columns_definition"]
        if isinstance(cols, str):
            cols = json.loads(cols)

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT data FROM org_data_rows WHERE table_id = $1", t["id"],
            )

        data = []
        for r in rows:
            d = r["data"]
            if isinstance(d, str):
                d = json.loads(d)
            data.append(d)

        if not data:
            continue

        stats = {"total_rows": len(data), "columns": {}}
        for col in cols:
            col_name = col["name"]
            col_type = col.get("type", "text")
            values = [row.get(col_name) for row in data if row.get(col_name) is not None]

            col_stats = {"non_null": len(values), "unique": len(set(str(v) for v in values))}

            if col_type in ("number", "integer", "float") and values:
                nums = []
                for v in values:
                    try:
                        nums.append(float(v))
                    except (ValueError, TypeError):
                        pass
                if nums:
                    col_stats.update({
                        "min": min(nums),
                        "max": max(nums),
                        "avg": round(sum(nums) / len(nums), 2),
                        "sum": round(sum(nums), 2),
                    })

            if col_type == "text" and values:
                counts = {}
                for v in values:
                    k = str(v)[:50]
                    counts[k] = counts.get(k, 0) + 1
                top5 = sorted(counts.items(), key=lambda x: -x[1])[:5]
                col_stats["top_values"] = [{"value": k, "count": v} for k, v in top5]

            stats["columns"][col_name] = col_stats

        analysis[t["display_name"]] = stats

    return analysis


# ---------------------------------------------------------------------------
# Tool: Create Chart Config
# ---------------------------------------------------------------------------

async def create_chart(org_id: str, table_name: str, chart_type: str, x_col: str, y_col: str, title: str = "") -> dict:
    """Genera config de gráfico Recharts a partir de datos reales."""
    pool = await get_org_pool(org_id)

    async with pool.acquire() as conn:
        table = await conn.fetchrow(
            "SELECT id, display_name FROM org_data_tables WHERE table_name = $1", table_name,
        )
        if not table:
            return {"error": f"Tabla '{table_name}' no encontrada"}

        rows = await conn.fetch(
            "SELECT data FROM org_data_rows WHERE table_id = $1 LIMIT 500", table["id"],
        )

    data = []
    for r in rows:
        d = r["data"]
        if isinstance(d, str):
            d = json.loads(d)
        data.append(d)

    if not data:
        return {"error": "La tabla no tiene datos"}

    # Agregar datos según tipo
    if y_col == "count":
        agg = {}
        for row in data:
            key = str(row.get(x_col, "Otro"))[:30]
            agg[key] = agg.get(key, 0) + 1
        chart_data = [{"name": k, "value": v} for k, v in sorted(agg.items(), key=lambda x: -x[1])[:15]]
    else:
        agg = {}
        for row in data:
            key = str(row.get(x_col, "Otro"))[:30]
            try:
                val = float(row.get(y_col, 0))
            except (ValueError, TypeError):
                val = 0
            agg[key] = agg.get(key, 0) + val
        chart_data = [{"name": k, "value": round(v)} for k, v in sorted(agg.items(), key=lambda x: -x[1])[:15]]

    colors = {"bar": "#3b82f6", "line": "#10b981", "pie": "#8b5cf6", "area": "#f59e0b"}

    return {
        "type": chart_type,
        "title": title or f"{table['display_name']} por {x_col}",
        "data": chart_data,
        "x": "name",
        "y": "value",
        "color": colors.get(chart_type, "#3b82f6"),
    }


# ---------------------------------------------------------------------------
# Tool: Manage Data (CRUD)
# ---------------------------------------------------------------------------

async def manage_data(org_id: str, action: str, **kwargs) -> dict:
    """CRUD de tablas y datos.

    Actions:
        create_table: Crea nueva tabla (name, display_name, columns)
        delete_table: Elimina tabla (table_name)
        insert_row: Inserta fila (table_name, data)
        delete_rows: Elimina filas (table_name, condition)
        clear_table: Limpia todos los datos de una tabla (table_name)
    """
    from app.services.schema_agent_service import create_table, delete_table

    pool = await get_org_pool(org_id)

    if action == "create_table":
        cols = [{"name": c["name"], "type": c.get("type", "text")} for c in kwargs.get("columns", [])]
        result = await create_table(org_id, kwargs["name"], kwargs.get("display_name", kwargs["name"]), cols)
        return result

    elif action == "insert_row":
        table_name = kwargs["table_name"]
        row_data = kwargs["data"]
        async with pool.acquire() as conn:
            table = await conn.fetchrow(
                "SELECT id FROM org_data_tables WHERE table_name = $1", table_name,
            )
            if not table:
                return {"error": f"Tabla '{table_name}' no encontrada"}

            await conn.execute(
                "INSERT INTO org_data_rows (table_id, data) VALUES ($1, $2::jsonb)",
                table["id"], json.dumps(row_data, ensure_ascii=False),
            )
            count = await conn.fetchval(
                "SELECT count(*) FROM org_data_rows WHERE table_id = $1", table["id"],
            )
            await conn.execute(
                "UPDATE org_data_tables SET row_count = $1 WHERE id = $2", count, table["id"],
            )
        return {"inserted": True, "table": table_name, "new_count": count}

    elif action == "clear_table":
        table_name = kwargs["table_name"]
        async with pool.acquire() as conn:
            table = await conn.fetchrow(
                "SELECT id, display_name FROM org_data_tables WHERE table_name = $1", table_name,
            )
            if not table:
                return {"error": f"Tabla '{table_name}' no encontrada"}

            # Postgres no permite funciones de agregacion (count(*)) dentro de
            # RETURNING -- se cuenta en Python sobre las filas devueltas.
            deleted_ids = await conn.fetch(
                "DELETE FROM org_data_rows WHERE table_id = $1 RETURNING id", table["id"],
            )
            deleted = len(deleted_ids)
            await conn.execute(
                "UPDATE org_data_tables SET row_count = 0 WHERE id = $1", table["id"],
            )
        return {"cleared": True, "table": table_name, "rows_deleted": deleted}

    return {"error": f"Acción desconocida: {action}"}


# ---------------------------------------------------------------------------
# Gemini + Tools orchestrator
# ---------------------------------------------------------------------------

async def process_with_gemini(
    org_id: str,
    user_message: str,
    chat_history: list[dict] = None,
) -> dict:
    """Procesa mensaje del usuario con Gemini + tools.

    Retorna: {
        "text": str (respuesta del agente),
        "charts": list[dict] (gráficos Recharts opcionales),
        "actions": list[str] (acciones realizadas),
    }
    """
    settings = get_settings()

    # Obtener contexto de la org
    main_pool = await get_main_pool()
    import uuid
    try:
        org_uuid = uuid.UUID(org_id)
    except ValueError:
        org_uuid = org_id

    async with main_pool.acquire() as conn:
        org = await conn.fetchrow(
            "SELECT name, sector, city FROM organizations WHERE id = $1", org_uuid,
        )
    org_name = org["name"] if org else "tu empresa"

    pool = await get_org_pool(org_id)
    async with pool.acquire() as conn:
        tables = await conn.fetch(
            "SELECT table_name, display_name, row_count, columns_definition FROM org_data_tables"
        )

    tables_context = []
    for t in tables:
        cols = t["columns_definition"]
        if isinstance(cols, str):
            cols = json.loads(cols)
        col_names = [c["name"] for c in cols] if cols else []
        tables_context.append(
            f"- {t['display_name']} ({t['table_name']}): {t['row_count'] or 0} filas. Columnas: {', '.join(col_names)}"
        )

    # Obtener datos relevantes
    query_results = await query_data(org_id, user_message)

    # Construir contexto con datos reales
    data_context = ""
    for table_display, info in query_results.items():
        if info["data"]:
            sample = json.dumps(info["data"][:10], ensure_ascii=False, default=str)
            data_context += f"\n\nDatos de {table_display} ({info['row_count']} filas):\n{sample}"

    system_prompt = f"""Eres el asistente de datos de la empresa "{org_name}".
Tu rol es analizar los datos, responder preguntas con números exactos, y ayudar a gestionar la información.

TABLAS DISPONIBLES:
{chr(10).join(tables_context)}

{data_context}

REGLAS:
- Responde SIEMPRE en español
- Usa los DATOS REALES proporcionados, no inventes números
- Si necesitas hacer cálculos (sumas, promedios, conteos), hazlos con los datos dados
- Si te piden un gráfico, genera un bloque ```chart con JSON válido
- Formato de gráfico: ```chart\n{{"type":"bar|line|pie","title":"titulo","data":[{{"name":"x","value":123}}],"x":"name","y":"value","color":"#3b82f6"}}\n```
- Si te piden crear/eliminar datos, indica qué acción se realizaría
- Sé conciso pero preciso con los números
- Usa formato markdown para resaltar datos importantes
"""

    try:
        from google import genai
        from google.genai import types as genai_types

        client = genai.Client(api_key=settings.GOOGLE_API_KEY)

        # Construir historial
        history = []
        if chat_history:
            for msg in chat_history[-6:]:
                role = "user" if msg.get("role") == "user" else "model"
                history.append(
                    genai_types.Content(
                        role=role,
                        parts=[genai_types.Part(text=msg["content"])],
                    )
                )

        chat = client.chats.create(
            model=settings.GEMINI_MODEL,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=2048,
                temperature=0.3,
            ),
            history=history,
        )

        response = chat.send_message(user_message)

        text = response.text or "No pude generar una respuesta."

        # Extraer charts del texto
        charts = []
        import re
        chart_pattern = r"```chart\s*\n(.*?)\n```"
        for match in re.finditer(chart_pattern, text, re.DOTALL):
            try:
                chart_json = json.loads(match.group(1))
                charts.append(chart_json)
            except json.JSONDecodeError:
                pass

        # Limpiar bloques chart del texto
        clean_text = re.sub(chart_pattern, "", text, flags=re.DOTALL).strip()

        return {
            "text": clean_text,
            "charts": charts,
            "actions": [],
        }

    except Exception as exc:
        logger.error(f"Gemini error: {exc}")
        # Fallback a respuesta local
        return {
            "text": f"Error con Gemini: {str(exc)[:200]}. Usando datos locales.",
            "charts": [],
            "actions": [],
        }
