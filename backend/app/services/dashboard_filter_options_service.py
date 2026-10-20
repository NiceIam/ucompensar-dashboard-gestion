"""Opciones de filtro de un tablero (`GET /dashboards/{id}/filter-options`) — PI0320251.

Que puede elegir el duenio para "jugar" con el tablero, calculado con el motor sobre los datos de ESTE momento:
- el rango de fechas de los datos (para el selector de periodo y sus atajos);
- por cada categoria util (producto, cliente, forma de pago...), sus valores MAS FRECUENTES (tope 25) con
  cuantas filas tiene cada uno y cuantos valores mas hay ("y 38 mas"); con `q` se buscan los valores que
  contienen ese texto (el selector con busqueda), sobre TODOS los valores y no solo los 25 de arriba.

Las categorias son las de las hojas que usan los graficos del tablero; la misma categoria en varias hojas
(`cliente` en ventas y en cartera) se une en una sola.
"""

import asyncio
import logging

from fastapi import status

from app.services import dashboard_filters as dfilters
from app.services import dashboard_render_service as render
from app.services import data_labels as labels
from app.services import data_query_engine as engine
from app.services.dashboard_drill_service import DrillError

logger = logging.getLogger(__name__)
MAX_DIMENSIONS = 8          # categorias que se ofrecen por hoja
MAX_SEARCH_CHARS = 60
_QUERY_CANCELED = "57014"


def _board_tables(catalog: dict, entries: list[dict]) -> list[engine.Table]:
    seen: dict[str, engine.Table] = {}
    for e in entries:
        if e["spec"] is not None:
            seen.setdefault(e["spec"].table, render._table_of(catalog, e["spec"]))
    return list(seen.values())


async def filter_options(org_id: str, dashboard_id: str, *, key: str | None = None, q: str | None = None) -> dict:
    pool, _dashboard, widgets, catalog = await render.load_board(org_id, dashboard_id)
    tables = _board_tables(catalog, render.board_entries(widgets, catalog))
    if q is not None:
        q = q.strip()[:MAX_SEARCH_CHARS]
    if key is not None:
        key = dfilters._norm_key(key) if isinstance(key, str) and key.strip() else None

    plans, meta = [], []           # meta: ("dim", Dimension, table) | ("date", Column, table)
    for table in tables:
        for dim in dfilters.table_dimensions(table)[:MAX_DIMENSIONS]:
            if key is not None and dim.key != key:
                continue
            # Sin celdas vacias: "(sin dato)" no es un valor que se pueda elegir (y no cuenta como valor distinto).
            filters = [[dim.column.name, "contains", q]] if q else [[dim.column.name, "notnull"]]
            plans.append(engine.build_plan(
                table, filters=filters, group_by=[dim.column.name], aggregates=["count"],
                limit=dfilters.MAX_OPTION_VALUES, max_rows=dfilters.MAX_OPTION_VALUES,
            ))
            meta.append(("dim", dim, table))
        col = dfilters.date_column(table)
        if key is None and col is not None:
            plans.append(engine.build_plan(
                table, aggregates=[f"min({col.name})", f"max({col.name})"], max_rows=1))
            meta.append(("date", col, table))
    if key is not None and not any(m[0] == "dim" for m in meta):
        raise DrillError("Esa categoría no existe en este tablero.")

    results = await _run(pool, plans) if plans else []

    merged: dict[str, dict] = {}
    date_info = None
    for (what, obj, table), result in zip(meta, results):
        if what == "date":
            row = result.rows[0] if result.rows else (None, None)
            lo, hi = row
            if lo is not None and hi is not None:
                lo, hi = str(lo)[:10], str(hi)[:10]
                if date_info is None:
                    date_info = {"column": obj.name, "label": labels.column_label(obj, table), "min": lo, "max": hi,
                                 "tables": [table.name]}
                else:
                    date_info["min"], date_info["max"] = min(date_info["min"], lo), max(date_info["max"], hi)
                    date_info["tables"].append(table.name)
            continue
        entry = merged.setdefault(obj.key, {"key": obj.key, "label": obj.label, "rank": obj.rank, "values": {},
                                            "distinct": 0, "tables": []})
        entry["tables"].append(table.name)
        entry["distinct"] = max(entry["distinct"], result.total)
        for label, count in result.rows:
            if label is None:
                continue
            folded = engine.fold_name(str(label))
            hit = entry["values"].setdefault(folded, [str(label), 0])
            hit[1] += int(count or 0)

    dimensions = []
    for entry in sorted(merged.values(), key=lambda e: (e["rank"], e["label"])):
        ordered = sorted(entry["values"].values(), key=lambda v: (-v[1], v[0].casefold()))
        shown = ordered[:dfilters.MAX_OPTION_VALUES]
        if q is None and entry["distinct"] < 2:
            continue                  # con un solo valor no hay nada que elegir
        dimensions.append({
            "key": entry["key"], "label": entry["label"], "tables": entry["tables"],
            "values": [{"value": engine.cell(v, 80), "count": c} for v, c in shown],
            "distinct": entry["distinct"], "more": max(0, entry["distinct"] - len(shown)),
        })
    return {
        "today": dfilters.today_co().isoformat(),
        "presets": [{"id": k, "label": v} for k, v in dfilters.PRESETS.items()],
        "date": date_info,
        "dimensions": dimensions,
    }


async def _run(pool, plans):
    try:
        return await engine.run_plans(pool, plans)
    except engine.QueryError:
        raise
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if getattr(exc, "sqlstate", None) == _QUERY_CANCELED:
            raise DrillError("Esto tardó demasiado en calcularse.", status.HTTP_504_GATEWAY_TIMEOUT)
        logger.error("Opciones de filtro no calculables: %s (sqlstate=%s)", type(exc).__name__, getattr(exc, "sqlstate", None))
        raise DrillError("No se pudieron calcular las opciones de filtro.", status.HTTP_500_INTERNAL_SERVER_ERROR)
