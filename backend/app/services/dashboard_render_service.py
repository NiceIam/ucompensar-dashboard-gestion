"""Calculo de un tablero al abrirlo (`POST /dashboards/{id}/execute`) — PI0320251.

Cada widget guardado como especificacion (`data_source_query` v1) se recalcula con el MOTOR de consultas sobre
TODAS las filas (antes: `LIMIT 500` filas sin ORDER BY y suma en Python, con totales incorrectos en tablas
grandes). Garantias:
- Un widget que falla (columna renombrada, tabla borrada, consulta lenta, especificacion escrita a mano por
  REST) devuelve `error` SOLO en ese widget; el resto del tablero se calcula igual.
- La especificacion guardada NO es de confianza: se vuelve a validar completa en cada lectura.
- Tope de tiempo global (DASHBOARD_RENDER_TIMEOUT_SECONDS) y maximo de widgets leidos.
- Los tableros antiguos (sin ninguna especificacion) siguen funcionando: se calculan con la regla por defecto
  (dashboard_rules.default_specs) y las cifras por hoja salen del catalogo.

Forma de salida (la que ya consume el frontend, ampliada):
  {"charts": [{id, type, title, data[{name, value}], x, y, color, unit, error?}],
   "kpis":   [{id, label, value, unit, icon, column?, error?}],
   "legacy": bool}
"""

import logging

from fastapi import HTTPException, status

from app.config import get_settings
from app.database import get_org_pool
from app.services import chart_specs as cs
from app.services import dashboard_rules as rules
from app.services import data_query_engine as engine
from app.services.dashboard_service import _to_uuid

logger = logging.getLogger(__name__)

DASHBOARD_SQL = "SELECT id, name FROM dashboards WHERE id = $1 AND deleted_at IS NULL"
WIDGETS_SQL = (
    "SELECT id, title, widget_type, data_source_query FROM widgets WHERE dashboard_id = $1 "
    "ORDER BY position_y, position_x, created_at LIMIT 24"
)
CATALOG_SQL = "SELECT id, table_name, display_name, row_count, columns_definition FROM org_data_tables"
MAX_WIDGETS = 12


def _render_timeout(settings) -> float:
    try:
        return min(max(float(getattr(settings, "DASHBOARD_RENDER_TIMEOUT_SECONDS", 12.0)), 1.0), 60.0)
    except (TypeError, ValueError):
        return 12.0


def _chart_error(kind: str, title: str, message: str, widget_id: str | None) -> dict:
    return {
        "id": widget_id, "type": kind if kind in cs.CHART_KINDS else "bar", "title": engine.cell(title, 80),
        "data": [], "x": "name", "y": "value", "color": cs.CHART_COLORS.get(kind, cs.CHART_COLORS["bar"]),
        "unit": "number", "error": message,
    }


def _kpi_error(title: str, message: str, widget_id: str | None) -> dict:
    return {
        "id": widget_id, "label": engine.cell(title, 80), "value": None, "unit": "number", "icon": "TrendingUp",
        "error": message,
    }


def _legacy_kpis(catalog: dict) -> list[dict]:
    """Las cifras de siempre (filas por hoja y total), desde el catalogo: exactas, sin leer filas."""
    tables = list(catalog.values())
    kpis = [{
        "id": None, "label": "Registros totales", "value": sum(t.rows for t in tables), "unit": "count",
        "icon": "TrendingUp",
    }]
    kpis += [
        {"id": None, "label": f"Total {engine.cell(t.display, 60)}", "value": t.rows, "unit": "count", "icon": "Database"}
        for t in tables
    ]
    return kpis


async def render_dashboard(org_id: str, dashboard_id: str) -> dict:
    settings = get_settings()
    pool = await get_org_pool(org_id)
    did = _to_uuid(dashboard_id)
    async with pool.acquire() as conn:
        dashboard = await conn.fetchrow(DASHBOARD_SQL, did)
        if not dashboard:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard no encontrado.")
        widgets = await conn.fetch(WIDGETS_SQL, did)
        catalog = engine.build_catalog(await conn.fetch(CATALOG_SQL))

    entries: list[dict] = []     # {id, title, kind, spec|None, error|None}
    for w in list(widgets)[:MAX_WIDGETS]:
        dsq = w["data_source_query"]
        if dsq in (None, "", {}, []) or (isinstance(dsq, str) and dsq.strip() in ("null", "{}", "[]")):
            continue                     # widget sin especificacion (hecho a mano): no se puede calcular
        entry = {
            "id": str(w["id"]), "title": w["title"] or "", "kind": cs.KIND_OF_WIDGET.get(w["widget_type"], "bar"),
            "spec": None, "error": None,
        }
        try:
            entry["spec"] = cs.parse_stored(catalog, dsq, w["widget_type"])
        except engine.QueryError as exc:
            entry["error"] = engine.one_line(str(exc), 200)
        entries.append(entry)

    legacy = not entries
    if legacy:
        entries = [
            {"id": None, "title": "", "kind": spec.kind, "spec": spec, "error": None}
            for spec in rules.default_specs(catalog, MAX_WIDGETS)
        ]

    runnable = [e for e in entries if e["spec"] is not None]
    results = await cs.run_many(
        pool, catalog, [e["spec"] for e in runnable], timeout=_render_timeout(settings),
    )
    by_entry = {id(e): r for e, r in zip(runnable, results)}

    charts: list[dict] = []
    kpis: list[dict] = _legacy_kpis(catalog) if legacy else []
    for e in entries:
        result = by_entry.get(id(e))
        message = e["error"] or (result["error"] if result and not result["ok"] else None)
        if message:
            if e["kind"] == "kpi":
                kpis.append(_kpi_error(e["title"] or "Cifra", message, e["id"]))
            else:
                charts.append(_chart_error(e["kind"], e["title"] or "Gráfico", message, e["id"]))
        elif e["kind"] == "kpi":
            kpis.append({"id": e["id"], **result["kpi"]})
        else:
            charts.append({"id": e["id"], **result["chart"]})
    return {"charts": charts, "kpis": kpis, "legacy": legacy}
