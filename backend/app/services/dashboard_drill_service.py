"""Detalle al tocar un dato de un grafico del tablero (drill-down) — PI0320251.

`POST /api/v1/dashboards/{id}/widgets/{widget_id}/drill`. Sin IA, solo lectura, todo con el motor de consultas:

  1. La especificacion del widget SE LEE DE LA BD (nunca del cliente) y se valida otra vez contra el catalogo.
  2. El cliente solo manda el VALOR tocado (la categoria o el periodo del eje X), opcionalmente `by` (la dimension
     de detalle, que debe estar en la lista blanca que el servidor calcula) y los filtros globales activos.
  3. Se arma un plan que filtra por ese valor y agrupa por la dimension de detalle; si el eje X es una fecha con
     bucket (dia/mes/ano) el valor se interpreta como el PERIODO completo.
  4. Se devuelve una tabla compacta (ordenada por la medida, con total y porcentaje, tope de filas con aviso) y
     las dimensiones alternativas para "Ver por".

Nada de SQL, columnas ni ids del cliente: lo que llega se compara con la lista blanca o se enlaza como parametro.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta

import asyncio
import logging

from fastapi import HTTPException, status

from app.services import chart_specs as cs
from app.services import dashboard_filters as dfilters
from app.services import dashboard_render_service as render
from app.services import dashboard_rules as rules
from app.services import data_labels as labels
from app.services import data_query_engine as engine

DRILL_ROWS = 20            # filas que se muestran por defecto
DRILL_MAX_ROWS = 50        # tope duro de filas que se pueden pedir
_AUTO_STATS = 6            # columnas candidatas cuyo numero de valores distintos se cuenta para elegir el detalle
_WEEK_DAYS = 7
logger = logging.getLogger(__name__)
_QUERY_CANCELED = "57014"   # SQLSTATE query_canceled (statement_timeout)
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_BUCKET_VALUE = {
    "day": re.compile(r"\d{4}-\d{2}-\d{2}", re.A),
    "week": re.compile(r"\d{4}-\d{2}-\d{2}", re.A),
    "month": re.compile(r"\d{4}-\d{2}", re.A),
    "year": re.compile(r"\d{4}", re.A),
}
_FINER = {"year": "month", "month": "day", "week": "day"}


class DrillError(Exception):
    """Peticion de detalle no valida (422/404). El mensaje es corto y en lenguaje llano."""

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class DrillDim:
    by: str                  # lo que se manda en `by` y entiende el motor ("producto", "month(fecha)")
    label: str               # "Producto", "Mes"
    kind: str                # category | period
    column: engine.Column
    rank: int


# ---------------------------------------------------------------------------
# Valor tocado -> filtros del motor
# ---------------------------------------------------------------------------

def _bucket_value(bucket: str, value) -> str:
    if not isinstance(value, str) or not _BUCKET_VALUE[bucket].fullmatch(value.strip()):
        raise DrillError("Ese período no es válido para este gráfico.")
    text = value.strip()
    try:
        if bucket in ("day", "week"):
            d = date.fromisoformat(text)
            if bucket == "week" and d.weekday() != 0:
                raise DrillError("Ese período no es válido para este gráfico.")
            year = d.year
        elif bucket == "month":
            year, month = int(text[:4]), int(text[5:7])
            if not 1 <= month <= 12:
                raise ValueError
        else:
            year = int(text)
    except ValueError:
        raise DrillError("Ese período no es válido para este gráfico.")
    if not 1900 <= year <= 2100:
        raise DrillError("Ese período está fuera de rango.")
    return text


def slice_filters(key: engine.Key, value, empty: bool) -> list[list]:
    """Filtros del motor que dejan solo las filas del dato tocado."""
    col = key.col
    if key.bucket:
        if empty or value is None:
            raise DrillError("Ese punto agrupa filas sin fecha legible: no hay detalle por fecha para mostrar.")
        text = _bucket_value(key.bucket, value)
        if key.bucket == "week":
            end = date.fromisoformat(text) + timedelta(days=_WEEK_DAYS)
            return [[col.name, ">=", text], [col.name, "<", end.isoformat()]]
        return [[col.name, "=", text]]
    if empty or value is None:
        return [[col.name, "null"]]
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise DrillError("El valor tocado debe ser texto o número.")
    text = str(value).strip()          # el motor ignora espacios en los extremos de la CELDA, no del valor pedido
    if not text or len(text) > engine.MAX_VALUE_CHARS or "\x00" in text:
        raise DrillError("El valor tocado no es válido.")
    return [[col.name, "=", text]]


# ---------------------------------------------------------------------------
# Dimensiones de detalle
# ---------------------------------------------------------------------------

def candidate_dims(table: engine.Table, key: engine.Key) -> list[DrillDim]:
    """Lista BLANCA de dimensiones por las que se puede desglosar el dato tocado: categorias utiles distintas del
    eje X y, si la hoja tiene fecha, un periodo mas fino (mes -> dia) o el mes (si el eje X es una categoria)."""
    dims = [
        DrillDim(d.column.name, d.label, "category", d.column, d.rank)
        for d in dfilters.table_dimensions(table)
        if key.bucket or d.column != key.col
    ]
    date_col = key.col if key.bucket else dfilters.date_column(table, None)
    if date_col is not None:
        bucket = _FINER.get(key.bucket) if key.bucket else ("day" if rules._bucket(date_col) == "day" else "month")
        if bucket:
            dims.append(DrillDim(f"{bucket}({date_col.name})", labels.capitalize(labels.BUCKET_WORD[bucket]),
                                 "period", date_col, 1000))
    return dims


def _pick_by(dims: list[DrillDim], distinct: dict, rows: int) -> DrillDim | None:
    cats = [d for d in dims if d.kind == "category"]
    usable = [
        d for d in cats
        if (distinct.get(d.by) or 0) >= 2 and not ((distinct.get(d.by) or 0) > 25 and (distinct.get(d.by) or 0) > rows * 0.8)
    ]
    if usable:
        return min(usable, key=lambda d: (d.rank, distinct.get(d.by) or 0))
    if cats:
        return min(cats, key=lambda d: d.rank)
    return next((d for d in dims if d.kind == "period"), None)


# ---------------------------------------------------------------------------
# Servicio
# ---------------------------------------------------------------------------

async def _run(pool, plans):
    """Ejecuta los planes; un fallo de la BD nunca llega al cliente con datos de celdas."""
    try:
        return await engine.run_plans(pool, plans)
    except engine.QueryError:
        raise
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if getattr(exc, "sqlstate", None) == _QUERY_CANCELED:
            raise DrillError("Este detalle tardó demasiado en calcularse. Prueba con un período más corto.",
                             status.HTTP_504_GATEWAY_TIMEOUT)
        logger.error("Detalle no calculable: %s (sqlstate=%s)", type(exc).__name__, getattr(exc, "sqlstate", None))
        raise DrillError("No se pudo calcular este detalle.", status.HTTP_500_INTERNAL_SERVER_ERROR)


def _num(value):
    return cs.chart_number(value) if value is not None else None


def _strip_note(note: str) -> str:
    return note[6:] if note.startswith("nota: ") else note


def _noun(agg, table) -> str:
    if agg.fn in ("sum", "count", "count_distinct") or agg.col is None:
        return labels.agg_noun(agg, table)
    return labels.agg_title(agg, table)


async def drill(org_id: str, dashboard_id: str, widget_id: str, body: dict) -> dict:
    if not isinstance(widget_id, str) or not _UUID.fullmatch(widget_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gráfico no encontrado.")
    if not isinstance(body, dict):
        raise DrillError("La petición no es válida.")
    pool, _dashboard, widgets, catalog = await render.load_board(org_id, dashboard_id)
    entries = render.board_entries(widgets, catalog)
    entry = next((e for e in entries if e["id"] == widget_id.lower()), None)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gráfico no encontrado.")
    if entry["spec"] is None:
        raise DrillError(entry["error"] or "Este gráfico no se puede calcular, así que no tiene detalle.")
    spec = entry["spec"]
    if spec.kind not in cs.CHART_KINDS:
        raise DrillError("Las cifras no tienen detalle; toca un gráfico.")

    table = engine.resolve_table(catalog, spec.table)
    plan_args, points = cs._plan_args(spec.kind, spec.x, spec.y, [], spec.top)
    base_plan = engine.build_plan(table, **plan_args)
    key, agg = base_plan.keys[0], base_plan.aggs[0]

    gf = dfilters.parse_filters(body.get("filters"))
    if gf.where:
        dfilters.check_keys(gf, [render._table_of(catalog, e["spec"]) for e in entries if e["spec"] is not None])
    applied, notes = dfilters.apply(spec, table, gf)
    base_filters = [list(f) for f in applied.filters]

    other = body.get("other") is True
    if body.get("other") not in (None, True, False):
        raise DrillError("La petición no es válida.")
    if not other and "value" not in body:
        raise DrillError("Falta el valor del dato tocado.")
    value = body.get("value")
    empty = value is None
    by_raw = body.get("by")
    if by_raw is not None and not isinstance(by_raw, str):
        raise DrillError("La dimensión de detalle no es válida.")
    limit = body.get("limit")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise DrillError("El tope de filas no es válido.")
    limit = min(limit or DRILL_ROWS, DRILL_MAX_ROWS)

    dims = candidate_dims(table, key)
    y = spec.y
    labels_out = {"x": {"label": labels.key_label(key), "bucket": key.bucket}}
    measure = {"label": _noun(agg, table), "fn": agg.fn, "unit": cs.unit_of(agg)}
    additive = agg.fn in cs.PIE_AGGS

    if other:
        return await _drill_other(pool, entry, table, spec, key, agg, points, base_filters, measure, additive, notes, gf,
                                  labels_out)

    slice_f = slice_filters(key, value, empty)
    filters = base_filters + slice_f

    by: DrillDim | None = None
    if by_raw is not None and by_raw.strip():
        wanted = by_raw.strip()
        by = next((d for d in dims if d.by == wanted or engine.fold_name(d.by) == engine.fold_name(wanted)), None)
        if by is None:
            raise DrillError("No se puede ver el detalle por esa columna en este gráfico.")

    count_distinct = [f"count_distinct({d.column.name})" for d in dims if d.kind == "category"][:_AUTO_STATS] if by is None else []
    aggregates = list(dict.fromkeys([y, "count", *count_distinct]))
    totals_plan = engine.build_plan(table, filters=filters, aggregates=aggregates, max_rows=1)

    def detail_plan(dim: DrillDim):
        rows_cap = DRILL_MAX_ROWS if dim.kind == "period" else limit
        return engine.build_plan(table, filters=filters, group_by=[dim.by], aggregates=[y], limit=rows_cap,
                                 max_rows=DRILL_MAX_ROWS)

    if by is not None:
        totals, detail = await _run(pool, [totals_plan, detail_plan(by)])
    else:
        (totals,) = await _run(pool, [totals_plan])
        row = dict(zip(totals_plan.labels, totals.rows[0])) if totals.rows else {}
        distinct = {d.by: row.get(f"count_distinct({d.column.name})") for d in dims if d.kind == "category"}
        by = _pick_by(dims, distinct, int(row.get("count") or 0))
        detail = None
        if by is not None:
            (detail,) = await _run(pool, [detail_plan(by)])

    row = dict(zip(totals_plan.labels, totals.rows[0])) if totals.rows else {}
    records = int(row.get("count") or 0)
    total_value = _num(row.get(agg.label))
    if agg.fn in ("sum", "count", "count_distinct") and total_value is None and records == 0:
        total_value = 0

    rows_out, groups = [], 0
    if detail is not None:
        groups = detail.total
        shown_values = [v for _, v in detail.rows if v is not None]
        share_ok = additive and total_value is not None and total_value > 0 and all(v >= 0 for v in shown_values)
        for label, v in detail.rows:
            n = _num(v)
            if n is None:
                continue
            item = {"name": engine.cell(label, 60) if label is not None else "(sin dato)", "value": n,
                    "share": round(n / total_value, 4) if share_ok else None}
            rows_out.append(item)

    truncated = groups > len(rows_out)
    out = {
        "title": labels.slice_title(_noun(agg, table), key, value, empty=empty),
        "widget": {"id": entry["id"], "title": entry["title"] or cs.chart_title(key, agg, table)},
        **labels_out,
        "measure": measure,
        "total": total_value,
        "records": records,
        "additive": additive,
        "by": {"by": by.by, "label": by.label, "kind": by.kind} if by else None,
        "dimensions": [{"by": d.by, "label": d.label, "kind": d.kind} for d in dims],
        "rows": rows_out,
        "groups": groups,
        "shown": len(rows_out),
        "truncated": truncated,
        "message": f"Mostrando {len(rows_out)} de {groups}" if truncated else None,
        "order": "period" if by is not None and by.kind == "period" else "value",
        "notes": [n["message"] for n in notes],
        "empty": records == 0,
    }
    if truncated and additive and total_value is not None:
        rest = total_value - sum(r["value"] for r in rows_out)
        out["rest"] = {"groups": groups - len(rows_out), "value": _num(rest)}
    data_notes = []
    for result, plan in ((totals, totals_plan), *(((detail, detail_plan(by)),) if detail is not None and by else ())):
        data_notes += [_strip_note(n) for n in engine.result_notes(result, plan)]
    out["notes"] += list(dict.fromkeys(data_notes))
    if gf.active:
        out["filters"] = gf.as_dict()
    out["question"] = _question(out["title"], by)
    return out


async def _drill_other(pool, entry, table, spec, key, agg, points, base_filters, measure, additive, notes, gf, labels_out):
    """La porcion "Otros (n)" de un pastel: las categorias que no entraron en las porciones visibles."""
    if spec.kind != "pie":
        raise DrillError("Solo la porción «Otros» de un pastel agrupa varias categorías.")
    keep = points - 1
    aggs = list(dict.fromkeys([spec.y, "count"]))
    plan = engine.build_plan(table, filters=base_filters, group_by=[spec.x], aggregates=aggs,
                             limit=keep + DRILL_MAX_ROWS, max_rows=keep + DRILL_MAX_ROWS)
    count_at = plan.labels.index("count")
    grand_plan = engine.build_plan(table, filters=base_filters, aggregates=[spec.y, "count"] if spec.y != "count" else ["count"],
                                   max_rows=1)
    result, grand = await _run(pool, [plan, grand_plan])
    grand_row = dict(zip(grand_plan.labels, grand.rows[0])) if grand.rows else {}
    top, rest = result.rows[:keep], result.rows[keep:]
    value_at = plan.labels.index(agg.label)
    groups = max(0, result.total - keep)
    total_value = _num((grand_row.get(agg.label) or 0) - sum((row[value_at] or 0) for row in top))
    records = int(grand_row.get("count") or 0) - sum(int(row[count_at] or 0) for row in top)
    share_ok = additive and total_value and total_value > 0 and all((row[value_at] or 0) >= 0 for row in rest)
    rows = [
        {"name": engine.cell(row[0], 60) if row[0] is not None else "(sin dato)", "value": _num(row[value_at]),
         "share": round(_num(row[value_at]) / total_value, 4) if share_ok and _num(row[value_at]) is not None else None}
        for row in rest[:DRILL_MAX_ROWS] if row[value_at] is not None
    ]
    title = labels.slice_title(measure["label"], key, None, other=groups)
    out = {
        "title": title, "widget": {"id": entry["id"], "title": cs.chart_title(key, agg, table)}, **labels_out,
        "measure": measure, "total": total_value, "records": records, "additive": additive,
        "by": {"by": key.col.name, "label": labels.dim_label(key.col), "kind": "category"}, "dimensions": [],
        "rows": rows, "groups": groups, "shown": len(rows), "truncated": groups > len(rows),
        "message": f"Mostrando {len(rows)} de {groups}" if groups > len(rows) else None, "order": "value",
        "notes": [n["message"] for n in notes], "empty": groups == 0,
    }
    if gf.active:
        out["filters"] = gf.as_dict()
    out["question"] = _question(title, None)
    return out


def _question(title: str, by: DrillDim | None) -> str:
    tail = f" ¿Qué destaca en el detalle por {by.label.lower()}?" if by else " ¿Qué destaca?"
    return f"Cuéntame más sobre «{title}».{tail}"
