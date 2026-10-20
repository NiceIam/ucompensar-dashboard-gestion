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
from app.services import data_labels as labels
from app.services import dashboard_filters as dfilters
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


async def load_board(org_id: str, dashboard_id: str):
    """(pool, tablero, widgets, catalogo) de la organizacion del JWT. 404 si el tablero no existe o es de otra."""
    pool = await get_org_pool(org_id)
    did = _to_uuid(dashboard_id)
    async with pool.acquire() as conn:
        dashboard = await conn.fetchrow(DASHBOARD_SQL, did)
        if not dashboard:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard no encontrado.")
        widgets = await conn.fetch(WIDGETS_SQL, did)
        catalog = engine.build_catalog(await conn.fetch(CATALOG_SQL))
    return pool, dashboard, widgets, catalog


def board_entries(widgets, catalog: dict) -> list[dict]:
    """Un elemento por widget guardado: {id, title, kind, spec|None, error|None}. Un tablero sin especificaciones
    (hecho antes de existir esta funcion) devuelve los widgets de la regla por defecto, con id None."""
    entries: list[dict] = []
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
    if entries:
        return entries
    return [
        {"id": None, "title": "", "kind": spec.kind, "spec": spec, "error": None, "legacy": True}
        for spec in rules.default_specs(catalog, MAX_WIDGETS)
    ]


def _table_of(catalog: dict, spec):
    return engine.resolve_table(catalog, spec.table)


def _empty_chart(chart: dict, message: str) -> dict:
    """Sin filas con los filtros activos: no es un error, es una respuesta (grafico vacio con su explicacion)."""
    return {**chart, "data": [], "empty": True, "message": message}


async def render_dashboard(org_id: str, dashboard_id: str, filters: dict | None = None) -> dict:
    """Calcula el tablero. `filters` (opcional, solo lectura): periodo y categorias que se SUMAN a los filtros
    propios de cada widget (ver dashboard_filters). Lanza dfilters.FilterError (el router responde 422)."""
    settings = get_settings()
    pool, _dashboard, widgets, catalog = await load_board(org_id, dashboard_id)
    gf = dfilters.parse_filters(filters)

    entries = board_entries(widgets, catalog)
    legacy = not entries or all(e.get("legacy") for e in entries)
    runnable = [e for e in entries if e["spec"] is not None]
    if gf.where:
        dfilters.check_keys(gf, [_table_of(catalog, e["spec"]) for e in runnable] or list(catalog.values()))

    specs, notes_by_entry, spec_by_entry = [], {}, {}
    for e in runnable:
        spec, notes = dfilters.apply(e["spec"], _table_of(catalog, e["spec"]), gf)
        specs.append(spec)
        spec_by_entry[id(e)] = spec
        notes_by_entry[id(e)] = notes
    results = await cs.run_many(pool, catalog, specs, timeout=_render_timeout(settings))
    by_entry = {id(e): r for e, r in zip(runnable, results)}

    charts: list[dict] = []
    if legacy and gf.active:
        kpis: list[dict] = []        # las cifras por hoja salen del catalogo y no cambiarian con los filtros
    else:
        kpis = _legacy_kpis(catalog) if legacy else []
    for e in entries:
        result = by_entry.get(id(e))
        notes = notes_by_entry.get(id(e)) or []
        message = e["error"] or (result["error"] if result and not result["ok"] else None)
        empty = bool(result and not result["ok"] and result.get("empty") and gf.active and not e["error"])
        if empty:
            message = None
        if message:
            if e["kind"] == "kpi":
                kpis.append(_kpi_error(e["title"] or "Cifra", message, e["id"]))
            else:
                charts.append(_chart_error(e["kind"], e["title"] or "Gráfico", message, e["id"]))
            continue
        if e["kind"] == "kpi":
            if empty:
                spec = spec_by_entry[id(e)]
                table = _table_of(catalog, spec)
                agg = engine.build_plan(table, **cs._plan_args("kpi", None, spec.y, [], None)[0]).aggs[0]
                zero = agg.fn in ("count", "sum", "count_distinct")
                unit = cs.unit_of(agg)
                item = {"id": e["id"], "label": labels.agg_title(agg, table),
                        "value": 0 if zero else None, "unit": unit, "icon": cs._KPI_ICONS[unit], "empty": True,
                        "message": "Sin datos con estos filtros."}
                if agg.col is not None:
                    item["column"] = engine.cell(agg.col.name, 60)
            else:
                item = {"id": e["id"], **result["kpi"]}
            if notes:
                item["notes"] = notes
            kpis.append(item)
            continue
        if empty:
            spec = spec_by_entry[id(e)]
            item = _empty_chart(_chart_skeleton(catalog, spec, e), "Sin datos con estos filtros.")
        else:
            item = {"id": e["id"], **result["chart"]}
        if notes:
            item["notes"] = notes
        if e["id"] and not e.get("legacy"):
            item["drillable"] = True
        charts.append(item)

    out = {"charts": charts, "kpis": kpis, "legacy": legacy}
    if gf.active:
        out["filters"] = gf.as_dict()
    if legacy and gf.active:
        out["notes"] = [{"code": "legacy_filters", "message": "Las cifras por hoja no se muestran mientras hay filtros activos."}]
    return out


def _chart_skeleton(catalog: dict, spec, entry: dict) -> dict:
    """Grafico sin datos con titulo, unidad y ejes correctos (para el estado vacio con filtros)."""
    table = _table_of(catalog, spec)
    args, _ = cs._plan_args(spec.kind, spec.x, spec.y, [], spec.top)
    plan = engine.build_plan(table, **args)
    key, agg = plan.keys[0], plan.aggs[0]
    return {
        "id": entry["id"], "type": spec.kind, "title": engine.cell(cs.chart_title(key, agg, table), 80), "data": [],
        "x": "name", "y": "value", "color": cs.CHART_COLORS[spec.kind], "unit": cs.unit_of(agg),
        "x_label": labels.key_label(key), "y_label": labels.agg_noun(agg, table),
    }
