"""Tableros SUGERIDOS: que "Tableros" nunca este vacio — PI0320251.

Con los datos ya cargados se proponen 1-3 tableros y se crean (mismas validaciones y topes que los del chat):
1. Si hay clave, cupo y el catalogo es nuevo: UNA llamada pequena a Gemini con el catalogo compacto (nombres de
   hojas/columnas/tipos/rango de fechas; SIN datos) que devuelve JSON con especificaciones de widgets.
2. Si no (sin clave, sin cupo, catalogo ya sugerido, error del modelo, JSON invalido o ningun grafico valido):
   la regla determinista basada en tipos (dashboard_rules). Cero tokens.

Control de gasto (la API key es compartida):
- Cache por FIRMA del catalogo (estructura, no filas): el mismo catalogo no vuelve a llamar al modelo. La firma
  queda guardada en los widgets creados (`sig`), asi que vale entre instancias serverless; ademas hay una
  cache en memoria de las propuestas y una "cache negativa" de los fallos (un fallo no se reintenta en 1 h).
- Tope por organizacion y dia (DASHBOARD_SUGGEST_DAILY_CALLS, firmas distintas con sugerencia IA en 24 h) y un
  tope duro por proceso (_HARD_CALLS_PER_HOUR).
- max_output_tokens ajustado, razonamiento bajo, sin reintentos, un solo llamado por pedido.
- Modo `auto` (al terminar una carga o al abrir Tableros vacio): solo si la organizacion NO tiene tableros y
  esa firma no se sugirio antes (no se "resucita" un tablero que la persona borro).
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from collections import OrderedDict

from app.config import get_settings
from app.database import get_org_pool
from app.services import chart_specs as cs
from app.services import dashboard_builder_service as builder
from app.services import dashboard_rules as rules
from app.services import data_query_engine as engine

logger = logging.getLogger(__name__)

SIG_USED_SQL = (
    "SELECT d.id, d.name, d.deleted_at FROM dashboards d WHERE EXISTS "
    "(SELECT 1 FROM widgets w WHERE w.dashboard_id = d.id AND w.data_source_query->>'sig' = $1) "
    "ORDER BY d.created_at"
)
LLM_SIGS_SQL = (
    "SELECT count(DISTINCT w.data_source_query->>'sig') FROM widgets w "
    "WHERE w.data_source_query->>'by' = 'ai' AND w.created_at > now() - interval '24 hours'"
)
CATALOG_SQL = "SELECT id, table_name, display_name, row_count, columns_definition FROM org_data_tables"

_HARD_CALLS_PER_HOUR = 20          # por proceso: red de seguridad si la BD fallara o se saltara el tope diario
_FAIL_TTL_SECONDS = 3600
_CACHE_SIZE = 64

_SUGGEST_INSTRUCTIONS = (
    "Propón tableros para el dueño de una PYME colombiana. Responde SOLO JSON: "
    '{"dashboards":[{"title":str,"widgets":[{"table":str,"chart_type":"bar|line|pie|kpi","x":str,"y":str,'
    '"filters":[[col,op,valor]],"top":int}]}]}. Máximo 3 tableros de 3 a 5 gráficos. Usa SOLO tablas y columnas '
    "del catálogo (t texto, n número, f fecha). x: columna o month(fecha) (no en kpi); y: count o sum|avg|min|max"
    "(col numérica); pie solo count|sum con pocas categorías. Prefiere dinero, series por mes y top 10 por "
    "categoría; evita columnas de código o id. Títulos cortos en español."
)

_plan_cache: "OrderedDict[tuple, list]" = OrderedDict()
_failed: dict[tuple, float] = {}
_call_times: list[float] = []
_locks: dict[str, asyncio.Lock] = {}


# ---------------------------------------------------------------------------
# Firma del catalogo
# ---------------------------------------------------------------------------

def catalog_signature(catalog: dict) -> str:
    """Huella de la ESTRUCTURA (hojas con datos, columnas y tipos). No cambia al agregar filas ni al cambiar
    el rango de fechas: mas datos en la misma hoja no piden otra sugerencia."""
    parts = [
        [t.name, [[c.name, c.kind] for c in t.columns]]
        for t in sorted(catalog.values(), key=lambda t: t.name) if t.rows > 0
    ]
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def _cache_put(key: tuple, plans: list) -> None:
    _plan_cache[key] = plans
    _plan_cache.move_to_end(key)
    while len(_plan_cache) > _CACHE_SIZE:
        _plan_cache.popitem(last=False)


def reset_caches() -> None:
    """Solo para pruebas."""
    _plan_cache.clear()
    _failed.clear()
    _call_times.clear()
    _locks.clear()


# ---------------------------------------------------------------------------
# Llamada al modelo (una sola)
# ---------------------------------------------------------------------------

def _parse_model_json(text: str) -> list[rules.PlannedDashboard]:
    """JSON del modelo -> propuestas (sin validar contra el catalogo: eso lo hace el builder)."""
    text = (text or "").strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S | re.I)
    if fence:
        text = fence.group(1)
    data = json.loads(text)
    items = data.get("dashboards") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("el modelo no devolvió una lista de tableros")
    plans = []
    for item in items[: rules.MAX_DASHBOARDS]:
        if isinstance(item, dict) and isinstance(item.get("widgets"), list):
            plans.append(rules.PlannedDashboard(
                cs.sanitize_title(item.get("title"), 80, "Tablero sugerido"), item["widgets"][: rules.MAX_WIDGETS + 2],
            ))
    return plans


def _hard_cap_reached() -> bool:
    now = time.monotonic()
    _call_times[:] = [t for t in _call_times if now - t < 3600]
    return len(_call_times) >= _HARD_CALLS_PER_HOUR


async def _ask_model(settings, catalog: dict) -> tuple[list[rules.PlannedDashboard], dict]:
    """UNA llamada a Gemini con el catalogo compacto (sin datos). Devuelve (propuestas, uso de tokens)."""
    from google import genai
    from google.genai import types as genai_types

    from app.services.agent_tools_service import _catalog_prompt, _int_setting, _thinking_config

    timeout_s = float(getattr(settings, "DASHBOARD_SUGGEST_TIMEOUT_SECONDS", 12.0) or 12.0)
    client = genai.Client(
        api_key=settings.GOOGLE_API_KEY, http_options=genai_types.HttpOptions(timeout=int(timeout_s * 1000)),
    )
    thinking = _thinking_config(settings, genai_types) or genai_types.ThinkingConfig(thinking_level="LOW")
    config = genai_types.GenerateContentConfig(
        system_instruction=_SUGGEST_INSTRUCTIONS,
        response_mime_type="application/json",
        max_output_tokens=_int_setting(settings, "DASHBOARD_SUGGEST_MAX_OUTPUT_TOKENS", 900, 4096),
        temperature=0.2,
        thinking_config=thinking,
    )
    aio = client.aio
    _call_times.append(time.monotonic())
    try:
        response = await asyncio.wait_for(
            aio.models.generate_content(
                model=settings.GEMINI_MODEL, contents=_catalog_prompt("PYME", catalog), config=config,
            ),
            timeout=timeout_s,
        )
    finally:
        try:
            await aio.aclose()
        except Exception:
            logger.debug("No se pudo cerrar el cliente async de Gemini")
    meta = getattr(response, "usage_metadata", None)
    used = {
        key: int(getattr(meta, field, 0) or 0)
        for key, field in (("prompt", "prompt_token_count"), ("output", "candidates_token_count"),
                           ("thoughts", "thoughts_token_count"), ("total", "total_token_count"))
    }
    text = "".join(
        p.text for c in (getattr(response, "candidates", None) or [])[:1]
        for p in (getattr(getattr(c, "content", None), "parts", None) or []) if isinstance(p.text, str) and not p.thought
    )
    return _parse_model_json(text), used


# ---------------------------------------------------------------------------
# Orquestacion
# ---------------------------------------------------------------------------

async def _create_plans(pool, catalog: dict, plans: list, source: str, sig: str, limits) -> tuple[list[dict], list[str]]:
    created: list[dict] = []
    notes: list[str] = []
    for plan in plans[: rules.MAX_DASHBOARDS]:
        try:
            board, omitted = await builder.build_dashboard(
                pool, catalog, plan.title, plan.widgets, source=source, sig=sig, limits=limits,
            )
        except builder.DashboardLimitError as exc:
            notes.append(str(exc))
            break
        except engine.QueryError as exc:
            notes.append(engine.one_line(str(exc), 150))
            continue
        created.append(board)
    return created, notes


def _llm_allowed(settings) -> bool:
    return bool(
        getattr(settings, "DASHBOARD_SUGGEST_USE_LLM", False)
        and str(getattr(settings, "GOOGLE_API_KEY", "") or "").strip()
    )


async def suggest(org_id: str, *, auto: bool = False) -> dict:
    """Crea 1-3 tableros sugeridos. Devuelve {"status", "source", "dashboards": [{id, name, widgets, existing}],
    "notes": [...], "tokens": {...}}.

    status: created | exists (ya estaban) | no_data | has_dashboards (auto) | already_suggested (auto) | nothing
    auto=True: solo si la organizacion no tiene tableros y esa firma no se sugirio antes."""
    settings = get_settings()
    pool = await get_org_pool(org_id)
    lock = _locks.setdefault(org_id, asyncio.Lock())
    async with lock:
        async with pool.acquire() as conn:
            catalog = engine.build_catalog(await conn.fetch(CATALOG_SQL))
        if not any(t.rows > 0 and t.columns for t in catalog.values()):
            return {"status": "no_data", "source": None, "dashboards": [], "notes": []}
        sig = catalog_signature(catalog)
        limits = builder.limits_from_settings(settings)

        async with pool.acquire() as conn:
            live_total = int(await conn.fetchval(builder.TOTAL_COUNT_SQL) or 0)
            used = await conn.fetch(SIG_USED_SQL, sig)
            llm_sigs = int(await conn.fetchval(LLM_SIGS_SQL) or 0)
        if auto and live_total > 0:
            return {"status": "has_dashboards", "source": None, "dashboards": [], "notes": []}
        if auto and used:
            return {"status": "already_suggested", "source": None, "dashboards": [], "notes": []}
        live = [r for r in used if r["deleted_at"] is None]
        if live:
            return {
                "status": "exists", "source": None, "notes": [],
                "dashboards": [{"id": str(r["id"]), "name": r["name"], "widgets": None, "existing": True} for r in live],
            }

        key = (org_id, sig)
        tokens: dict = {}
        plans: list = []
        source = "rules"
        daily_cap = int(getattr(settings, "DASHBOARD_SUGGEST_DAILY_CALLS", 3) or 0)
        if key in _plan_cache:
            plans, source = _plan_cache[key], "ai"
            _plan_cache.move_to_end(key)
        elif (
            _llm_allowed(settings) and not used and llm_sigs < daily_cap and not _hard_cap_reached()
            and time.monotonic() - _failed.get(key, -_FAIL_TTL_SECONDS) >= _FAIL_TTL_SECONDS
        ):
            started = time.monotonic()
            try:
                plans, tokens = await _ask_model(settings, catalog)
                source = "ai"
                logger.info(
                    "Sugerencia IA: resultado=ok tokens prompt=%d salida=%d razonamiento=%d total=%d latencia_ms=%d",
                    tokens["prompt"], tokens["output"], tokens["thoughts"], tokens["total"],
                    int((time.monotonic() - started) * 1000),
                )
            except Exception as exc:
                _failed[key] = time.monotonic()
                logger.warning("Sugerencia IA: resultado=fallo causa=%s; se usa la regla determinista", type(exc).__name__)
                plans = []

        created: list[dict] = []
        notes: list[str] = []
        if plans:
            created, notes = await _create_plans(pool, catalog, plans, "ai", sig, limits)
            if created:
                _cache_put(key, plans)
            else:
                _failed[key] = time.monotonic()       # propuestas invalidas: no se vuelve a pagar por las mismas
                _plan_cache.pop(key, None)
        if not created:
            source = "rules"
            stats = await rules.gather_stats(pool, catalog)
            created, more = await _create_plans(
                pool, catalog, rules.plan_dashboards(catalog, stats), "rules", sig, limits,
            )
            notes += more
        return {
            "status": "created" if created else "nothing", "source": source if created else None,
            "dashboards": created, "notes": notes[:3], "tokens": tokens,
        }


async def auto_suggest_after_upload(org_id: str) -> None:
    """Gancho al terminar una carga. NUNCA lanza ni retrasa la carga mas que su tope de tiempo."""
    try:
        settings = get_settings()
        if not getattr(settings, "DASHBOARD_AUTO_SUGGEST", False):
            return
        timeout = float(getattr(settings, "DASHBOARD_SUGGEST_TIMEOUT_SECONDS", 12.0) or 12.0) + 6.0
        await asyncio.wait_for(suggest(org_id, auto=True), timeout=timeout)
    except Exception as exc:
        logger.warning("Sugerencia automatica tras la carga omitida: %s", type(exc).__name__)
