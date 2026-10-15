"""Agent Tools — Superpoderes del Asistente IA.

Herramientas que Gemini puede invocar para responder preguntas sobre los datos:
1. query_data: Ejecutar SQL sobre los datos de la org
2. analyze_table: Análisis estadístico de una tabla
3. create_chart: Generar config de gráfico Recharts
4. manage_data: CRUD de tablas y registros
"""

import asyncio
import json
import logging
import math
import re
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

        # El LIMIT trunca las filas devueltas; si se alcanzo, el total real es el de la tabla.
        truncated = len(rows) >= 1000
        results[t["display_name"]] = {
            "table_name": t["table_name"],
            "row_count": max(t["row_count"] or 0, len(data)) if truncated else len(data),
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
# Fallback cuando Gemini falla
# ---------------------------------------------------------------------------

class _GeminiUnusableResponse(Exception):
    """Gemini respondio sin error pero sin texto util (vacia o bloqueada)."""

    def __init__(self, kind: str):
        super().__init__(f"respuesta de Gemini sin texto ({kind})")
        self.kind = kind


# causa -> (por que fallo, que puede hacer el usuario)
_FAILURE_MESSAGES = {
    "quota": (
        "se agotó la cuota de uso del servicio de IA",
        "Intenta de nuevo en unos minutos; si persiste, avisa al administrador.",
    ),
    "unavailable": (
        "el servicio de IA no está disponible en este momento",
        "Intenta de nuevo en unos minutos.",
    ),
    "timeout": (
        "el servicio de IA tardó demasiado en responder",
        "Intenta de nuevo; si la pregunta es muy amplia, prueba con una más específica.",
    ),
    "auth": (
        "el servicio de IA no está configurado correctamente",
        "Avisa al administrador para que revise la configuración.",
    ),
    "blocked": (
        "la IA bloqueó esta pregunta con sus filtros de seguridad",
        "Intenta reformular la pregunta.",
    ),
    "truncated": (
        "la respuesta de la IA se cortó antes de generar texto",
        "Prueba con una pregunta más específica.",
    ),
    "empty": (
        "la IA no devolvió una respuesta",
        "Intenta de nuevo o reformula la pregunta.",
    ),
    "unknown": (
        "ocurrió un error inesperado con el servicio de IA",
        "Intenta de nuevo; si el problema continúa, avisa al administrador.",
    ),
}

_BLOCKED_FINISH_REASONS = {
    "SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII",
    "IMAGE_SAFETY", "IMAGE_PROHIBITED_CONTENT", "IMAGE_RECITATION",
}

_NUMERIC_TYPES = ("number", "integer", "float")

_DEFAULT_GEMINI_TIMEOUT_SECONDS = 25.0


def _empty_response_kind(response) -> str:
    """'blocked' si Gemini filtro el prompt o la respuesta; 'empty' si solo vino vacia."""
    block_reason = getattr(getattr(response, "prompt_feedback", None), "block_reason", None)
    if block_reason is not None and not getattr(block_reason, "name", str(block_reason)).endswith("UNSPECIFIED"):
        return "blocked"
    for candidate in getattr(response, "candidates", None) or []:
        reason = getattr(candidate, "finish_reason", None)
        if reason is not None and getattr(reason, "name", str(reason)) in _BLOCKED_FINISH_REASONS:
            return "blocked"
        if reason is not None and getattr(reason, "name", str(reason)) == "MAX_TOKENS":
            return "truncated"
    return "empty"


def _classify_gemini_failure(exc: BaseException) -> str:
    """Clasifica la falla en una clave de _FAILURE_MESSAGES. Nunca lanza: corre dentro de un `except`."""
    try:
        return _classify(exc)
    except Exception:
        return "unknown"


def _classify(exc: BaseException) -> str:
    import httpx
    from google.genai import errors as genai_errors

    if isinstance(exc, _GeminiUnusableResponse):
        return exc.kind
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return "timeout"
    if isinstance(exc, genai_errors.APIError):
        code = exc.code or 0
        status = (exc.status or "").upper()
        message = (exc.message or "").lower()
        if code == 429 or status == "RESOURCE_EXHAUSTED":
            return "quota"
        if code in (401, 403) or status in ("UNAUTHENTICATED", "PERMISSION_DENIED") or "api key" in message:
            return "auth"
        if code == 504 or status == "DEADLINE_EXCEEDED":
            return "timeout"
        if code >= 500:
            return "unavailable"
        return "unknown"
    if isinstance(exc, (ConnectionError, OSError, httpx.TransportError)):
        return "unavailable"
    if isinstance(exc, ValueError) and "api key" in str(exc).lower():
        return "auth"  # el SDK lanza ValueError('No API key was provided...') si GOOGLE_API_KEY esta vacia
    return "unknown"


def _gemini_timeout_seconds(settings) -> float:
    value = settings.GEMINI_TIMEOUT_SECONDS
    return value if value and value > 0 else _DEFAULT_GEMINI_TIMEOUT_SECONDS


def _redact(text: str, api_key: str | None) -> str:
    """Quita la API key (exacta o con forma de clave de Google) y acota el largo para logs."""
    if api_key:
        text = text.replace(api_key, "***")
    return re.sub(r"AIza[\w-]{10,}", "***", text)[:500]


def _fmt_number(value: float):
    """Numero legible: entero si lo es, 2 decimales, cientifico si es enorme, sin lanzar nunca."""
    if not math.isfinite(value):
        return "no calculable"
    if abs(value) >= 1e15:
        return f"{value:.3e}"
    return int(value) if value == int(value) else round(value, 2)


_MAX_CELL_CHARS = 80
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]+")


def _clean_cell(value) -> str:
    """Valor apto para mostrar en una linea de markdown: sin saltos ni control, acotado."""
    text = _CONTROL_CHARS.sub(" ", str(value)[: _MAX_CELL_CHARS * 2]).strip()
    return text[:_MAX_CELL_CHARS] + "…" if len(text) > _MAX_CELL_CHARS else text


def _build_fallback_text(kind: str, tables, query_results: dict, numeric_cols: dict) -> str:
    """Mensaje amable + resumen determinista de los datos reales (sin LLM)."""
    cause, hint = _FAILURE_MESSAGES[kind]
    parts = [f"No pude consultar al asistente de IA porque {cause}. {hint}"]

    with_data = [t for t in tables if (t["row_count"] or 0) > 0]
    if not with_data:
        parts.append(
            "Además, aún no hay datos cargados en tu organización. "
            "Sube un archivo CSV o Excel para empezar a analizarlos."
        )
        return "\n\n".join(parts)

    summary = ["Mientras tanto, este es el resumen de tus datos:"]
    summary += [f"- **{t['display_name']}**: {t['row_count']} filas" for t in with_data]
    parts.append("\n".join(summary))

    for display, info in query_results.items():
        data = info["data"]
        if not data:
            continue
        block = [f"**{display}** (calculado sobre {len(data)} filas):"]
        for col in numeric_cols.get(display, [])[:3]:
            nums = []
            for row in data:
                raw = row.get(col)
                if isinstance(raw, bool):
                    continue
                try:
                    value = float(raw)
                except (ValueError, TypeError, OverflowError):
                    continue
                if math.isfinite(value):
                    nums.append(value)
            if nums:
                block.append(
                    f"- {_clean_cell(col)}: suma {_fmt_number(sum(nums))}, promedio {_fmt_number(sum(nums) / len(nums))}, "
                    f"mínimo {_fmt_number(min(nums))}, máximo {_fmt_number(max(nums))}"
                )
        for row in data[:3]:
            block.append(
                "- Ejemplo: " + ", ".join(f"{_clean_cell(k)}: {_clean_cell(v)}" for k, v in list(row.items())[:4])
            )
        parts.append("\n".join(block))

    return "\n\n".join(parts)


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
    numeric_cols = {}
    for t in tables:
        cols = t["columns_definition"]
        if isinstance(cols, str):
            cols = json.loads(cols)
        col_names = [c["name"] for c in cols] if cols else []
        numeric_cols[t["display_name"]] = [
            c["name"] for c in (cols or []) if c.get("type") in _NUMERIC_TYPES
        ]
        tables_context.append(
            f"- {t['display_name']} ({t['table_name']}): {t['row_count'] or 0} filas. Columnas: {', '.join(col_names)}"
        )

    # Obtener datos relevantes
    query_results = await query_data(org_id, user_message)

    # Construir contexto con datos reales
    data_context = ""
    for table_display, info in query_results.items():
        if info["data"]:
            shown = info["data"][:10]
            sample = json.dumps(shown, ensure_ascii=False, default=str)
            if len(shown) < info["row_count"]:
                label = f"MUESTRA de las primeras {len(shown)} de {info['row_count']} filas"
            else:
                label = f"{info['row_count']} filas"
            data_context += f"\n\nDatos de {table_display} ({label}):\n{sample}"

    system_prompt = f"""Eres el asistente de datos de la empresa "{org_name}".
Tu rol es analizar los datos, responder preguntas con números exactos, y ayudar a gestionar la información.

TABLAS DISPONIBLES:
{chr(10).join(tables_context)}

{data_context}

REGLAS:
- Responde SIEMPRE en español
- Usa los DATOS REALES proporcionados, no inventes números
- Si necesitas hacer cálculos (sumas, promedios, conteos), hazlos con los datos dados. Si los datos son una MUESTRA, aclara que el resultado es aproximado y NO afirmes totales de la tabla completa (el número total de filas sí es exacto)
- Si te piden un gráfico, genera un bloque ```chart con JSON válido
- Formato de gráfico: ```chart\n{{"type":"bar|line|pie","title":"titulo","data":[{{"name":"x","value":123}}],"x":"name","y":"value","color":"#3b82f6"}}\n```
- Si te piden crear/eliminar datos, indica qué acción se realizaría
- Sé conciso pero preciso con los números
- Usa formato markdown para resaltar datos importantes
"""

    try:
        from google import genai
        from google.genai import types as genai_types

        timeout_s = _gemini_timeout_seconds(settings)
        # HttpOptions.timeout va en MILISEGUNDOS (verificado en google-genai 2.24).
        client = genai.Client(
            api_key=settings.GOOGLE_API_KEY,
            http_options=genai_types.HttpOptions(timeout=int(timeout_s * 1000)),
        )

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

        # API async del SDK: no bloquea el event loop mientras Gemini responde.
        aio = client.aio
        try:
            chat = aio.chats.create(
                model=settings.GEMINI_MODEL,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=2048,
                    temperature=0.3,
                ),
                history=history,
            )
            # wait_for es el tope duro: el timeout del SDK es por fase de la conexion, no total.
            response = await asyncio.wait_for(chat.send_message(user_message), timeout=timeout_s)
        finally:
            try:
                await aio.aclose()
            except Exception:
                logger.debug("No se pudo cerrar el cliente async de Gemini")

        text = response.text
        if not text or not text.strip():
            raise _GeminiUnusableResponse(_empty_response_kind(response))

        # Extraer charts del texto
        charts = []
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
        kind = _classify_gemini_failure(exc)
        # El detalle real solo va a logs (con la API key redactada), nunca al usuario.
        try:
            logger.error(
                "Gemini falló (causa=%s): %s: %s",
                kind, type(exc).__name__, _redact(str(exc), settings.GOOGLE_API_KEY),
            )
        except Exception:
            logger.error("Gemini falló (causa=%s): %s", kind, type(exc).__name__)
        try:
            fallback_text = _build_fallback_text(kind, tables, query_results, numeric_cols)
        except Exception:
            logger.exception("No se pudo armar el resumen local del fallback")
            fallback_text = _build_fallback_text(kind, [], {}, {})
        return {
            "text": fallback_text,
            "charts": [],
            "actions": [],
            "fallback_reason": kind,
        }
