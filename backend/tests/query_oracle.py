"""Oraculo en pandas del motor de consultas del chat (data_query_engine) — PI0320251.

Reimplementa la SEMANTICA de un Plan sin SQL, sobre las filas en memoria (dicts como los que guarda la
ingesta en org_data_rows.data). Se usa para:
1. Reemplazar data_query_engine.run_plans en los tests con la BD emulada (fake_org_db no ejecuta SQL).
2. Comparar contra Postgres real (test_chat_tools_pg.py): mismo Plan, mismas filas -> mismo resultado.

Las reglas de celda (numero tolerante, fechas, si/no, texto de data->>) se escriben aqui OTRA VEZ a
proposito, sin importarlas del motor: si el motor tuviera un error en esas reglas, el oraculo no lo copia.
"""

import asyncio
import functools
import json
import re
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd

from app.services.data_query_engine import PlanResult

_NUM = re.compile(r"[ ]*[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]{1,3})?[ ]*")
_NUM_MAX_CHARS = 200
_ISO = re.compile(r"[ ]*([0-9]{4})[-/.]([0-9]{1,2})[-/.]([0-9]{1,2})")          # prefijo: admite hora
_DMY = re.compile(r"[ ]*([0-9]{1,2})[-/.]([0-9]{1,2})[-/.]([0-9]{4})")          # prefijo
_DMY2 = re.compile(r"[ ]*([0-9]{1,2})[-/.]([0-9]{1,2})[-/.]([0-9]{2})(?![0-9])")  # prefijo, año de 2 digitos
_YM = re.compile(r"[ ]*([0-9]{4})[-/.]([0-9]{1,2})[ ]*")                        # completo
_COMPACT = re.compile(r"[ ]*([0-9]{4})([0-9]{2})([0-9]{2})[ ]*")                 # completo
_TRUE = {"true", "t", "1", "si", "sí", "yes", "verdadero"}
_FALSE = {"false", "f", "0", "no", "falso"}


def raw_text(row, col: str):
    """Lo que devuelve Postgres para data->>'col' (texto de jsonb)."""
    if not isinstance(row, dict) or col not in row or row[col] is None:
        return None
    v = row[col]
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return format(Decimal(json.dumps(v)), "f")   # jsonb guarda numeric: sin notacion cientifica
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False)


def key_of(raw):
    if raw is None:
        return None
    text = raw.strip(" ")
    return text or None


def num_of(raw):
    if raw is None or len(raw) > _NUM_MAX_CHARS or not _NUM.fullmatch(raw):
        return None
    return Decimal(raw.strip(" "))


_YEAR = [date.today().year]   # run_plan lo fija con plan.current_year (ventana de años de 2 digitos)


def date_of(raw):
    return date_parts(raw)[0]


def date_parts(raw):
    """(fecha o None, si el año venia con 2 digitos)."""
    if raw is None:
        return None, False
    two_digit = False
    if m := _ISO.match(raw):
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
    elif m := _DMY.match(raw):
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
    elif m := _DMY2.match(raw):
        d, mo, yy = int(m[1]), int(m[2]), int(m[3])
        pivot = min(_YEAR[0] % 100 + 5, 99)              # ventana: hasta 5 años en el futuro
        century = _YEAR[0] // 100 * 100
        y = century + yy if yy <= pivot else century - 100 + yy
        two_digit = True
    elif m := _YM.fullmatch(raw):
        y, mo, d = int(m[1]), int(m[2]), 1
    elif m := _COMPACT.fullmatch(raw):
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
    else:
        return None, False
    try:
        return date(y, mo, d), two_digit
    except ValueError:
        return None, False


def bool_of(raw):
    k = key_of(raw)
    if k is None:
        return None
    k = k.lower()
    return True if k in _TRUE else False if k in _FALSE else None


def bucket_of(raw, bucket: str):
    d = date_of(raw)
    if d is None:
        return None
    if bucket == "day":
        return d.isoformat()
    if bucket == "week":
        return (d - timedelta(days=d.weekday())).isoformat()
    if bucket == "month":
        return f"{d.year:04d}-{d.month:02d}"
    return f"{d.year:04d}"


def _cmp(a, b, op: str) -> bool:
    return {"=": a == b, "!=": a != b, ">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b}[op]


def _date_match(d, op, ranges) -> bool:
    if d is None:
        return False
    if op == "in":
        return any(s <= d < e for s, e in ranges)
    s, e = ranges[0]
    return {"=": s <= d < e, "!=": d < s or d >= e, ">": d >= e, ">=": d >= s, "<": d < s, "<=": d < e}[op]


def filter_matches(f, row) -> bool:
    raw = raw_text(row, f.col.name)
    k = key_of(raw)
    if f.op == "null":
        return k is None
    if f.op == "notnull":
        return k is not None
    if f.op == "contains":
        return k is not None and f.values[0].lower() in k.lower()
    if f.mode == "n":
        v = num_of(raw)
        return v is not None and (v in f.values if f.op == "in" else _cmp(v, f.values[0], f.op))
    if f.mode == "b":
        v = bool_of(raw)
        return v is not None and (v in f.values if f.op == "in" else _cmp(v, f.values[0], f.op))
    if f.mode == "f":
        return _date_match(date_of(raw), f.op, f.values)
    if k is None:
        return False
    if f.op == "in":
        return k.lower() in {v.lower() for v in f.values}
    if f.op in ("=", "!="):
        return _cmp(k.lower(), f.values[0].lower(), f.op)
    return _cmp(k, f.values[0], f.op)


def norm_of(raw, kind: str):
    """Criterio de agrupacion (el mismo de '=' / 'in'): numero por valor, fecha por dia, texto sin mayusculas."""
    k = key_of(raw)
    if k is None:
        return None
    if kind == "n" and (n := num_of(raw)) is not None:
        if n == 0:
            return "0"
        text = format(n, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    if kind == "f" and (d := date_of(raw)) is not None:
        return d.isoformat()
    if kind == "b" and (v := bool_of(raw)) is not None:
        return "sí" if v else "no"
    return k.lower()


def _key_value(k, row):
    raw = raw_text(row, k.col.name)
    return bucket_of(raw, k.bucket) if k.bucket else key_of(raw)


def _agg_input(a, row, numeric_text=frozenset()):
    if a.col is None:
        return 1
    raw = raw_text(row, a.col.name)
    if a.fn == "count_distinct":
        return norm_of(raw, a.col.kind)
    if a.fn == "count":
        return key_of(raw)
    if a.mode == "n" or (a.fn in ("min", "max") and a.col.name in numeric_text):
        return num_of(raw)
    if a.mode == "f":
        return date_of(raw)
    return key_of(raw)


def _aggregate(a, values: list):
    present = [v for v in values if v is not None]
    if a.fn == "count":
        return len(values) if a.col is None else len(present)
    if a.fn == "count_distinct":
        return len(set(present))
    if not present:
        return None
    if a.fn == "sum":
        return sum(present, Decimal(0))
    if a.fn == "avg":
        return sum(present, Decimal(0)) / len(present)
    return min(present) if a.fn == "min" else max(present)


def _order_value(plan, o, out_row, member_rows, numeric_text=frozenset()):
    if o.by == "out":
        return out_row[o.index]
    if o.by == "tn":
        # columna de texto: si la mayoria de sus valores son numeros, se ordena por el numero
        if o.index >= len(plan.keys):
            return out_row[o.index]                      # min/max ya calculado como numero o como texto
        col = plan.keys[o.index].col.name
        if col not in numeric_text:
            return out_row[o.index]
        values = [num_of(raw_text(r, col)) for r in member_rows]
        values = [v for v in values if v is not None]
        return min(values) if values else None
    col = plan.keys[o.index].col.name
    parse = num_of if o.by == "n" else date_of
    values = [parse(raw_text(r, col)) for r in member_rows]
    values = [v for v in values if v is not None]
    return min(values) if values else None


def _sorted(items, sort_keys):
    """items: lista de (fila_salida, valores_de_orden); NULLS LAST tanto en ASC como en DESC."""

    def cmp(a, b):
        for (va, vb), desc in zip(zip(a[1], b[1]), sort_keys):
            if va is None and vb is None:
                continue
            if va is None:
                return 1
            if vb is None:
                return -1
            if va == vb:
                continue
            r = -1 if va < vb else 1
            return -r if desc else r
        return 0

    return sorted(items, key=functools.cmp_to_key(cmp))


_NULL = object()


def _date_columns(plan) -> list[str]:
    used = {k.col.name for k in plan.keys if k.bucket} | {a.col.name for a in plan.aggs if a.mode == "f"}
    used |= {f.col.name for f in plan.filters if f.mode == "f"}
    used |= {plan.keys[o.index].col.name for o in plan.order if o.by == "f"}
    return sorted(used)


def _text_compared(plan) -> list[str]:
    cols = {a.col.name for a in plan.aggs if a.fn in ("min", "max") and a.col is not None and a.col.kind == "t"}
    for o in plan.order:
        if o.by == "tn":
            cols.add(plan.keys[o.index].col.name if o.index < len(plan.keys) else plan.aggs[o.index - len(plan.keys)].col.name)
    return sorted(cols)


def run_plan(rows: list, plan) -> PlanResult:
    _YEAR[0] = plan.current_year
    selected = [r for r in rows if all(filter_matches(f, r) for f in plan.filters)]
    text_numeric = {
        col: (sum(1 for r in selected if num_of(raw_text(r, col)) is not None),
              sum(1 for r in selected if key_of(raw_text(r, col)) is not None))
        for col in _text_compared(plan)
    } if selected else {}
    numeric_text = frozenset(col for col, (n, k) in text_numeric.items() if n * 2 > k)
    # Las fechas ilegibles se cuentan entre las filas que pasan los filtros que NO son de fecha.
    candidates = [r for r in rows if all(filter_matches(f, r) for f in plan.filters if f.mode != "f")]
    bad_dates = {
        col: sum(1 for r in candidates if key_of(raw_text(r, col)) is not None and date_of(raw_text(r, col)) is None)
        for col in _date_columns(plan)
    }
    two_digit = {
        col: sum(1 for r in candidates if (parts := date_parts(raw_text(r, col)))[0] is not None and parts[1])
        for col in _date_columns(plan)
    }
    bad = {}
    for a in plan.aggs:
        if a.mode == "n" or (a.fn in ("min", "max") and a.col is not None and a.col.name in numeric_text):
            col = a.col.name
            bad[col] = sum(
                1 for r in selected
                if key_of(raw_text(r, col)) is not None and num_of(raw_text(r, col)) is None
            )

    if not plan.aggregate:
        items = []
        for r in selected:
            out = tuple(_key_value(k, r) for k in plan.keys)
            items.append((out, tuple(_order_value(plan, o, out, [r], numeric_text) for o in plan.order)))
        ordered = _sorted(items, [o.desc for o in plan.order])
        return PlanResult([o for o, _ in ordered][: plan.limit], len(selected), bad, bad_dates, text_numeric, two_digit, plan.current_year)

    def group_value(k, r):
        return _key_value(k, r) if k.bucket else norm_of(raw_text(r, k.col.name), k.col.kind)

    frame = pd.DataFrame({
        **{f"k{j}": [group_value(k, r) for r in selected] for j, k in enumerate(plan.keys)},
        "row": selected,
    })
    groups: list[tuple[tuple, list]] = []
    if plan.keys:
        # dropna=False conserva el grupo "sin valor"; el centinela evita que pandas mezcle None y NaN.
        cols = [f"k{j}" for j in range(len(plan.keys))]
        frame[cols] = frame[cols].map(lambda v: _NULL if v is None else v)
        for gkey, g in frame.groupby(cols, sort=False, dropna=False):
            gkey = gkey if isinstance(gkey, tuple) else (gkey,)
            groups.append((tuple(None if v is _NULL else v for v in gkey), list(g["row"])))
    else:
        groups.append(((), selected))

    items = []
    for gkey, members in groups:
        # etiqueta: la variante original menor (orden de bytes) entre las filas del grupo
        gkey = tuple(
            value if k.bucket or k.col.kind == "b"           # si/no: etiqueta canonica "sí"/"no"
            else min((v for v in (key_of(raw_text(r, k.col.name)) for r in members) if v is not None), default=None)
            for k, value in zip(plan.keys, gkey)
        )
        out = gkey + tuple(_aggregate(a, [_agg_input(a, r, numeric_text) for r in members]) for a in plan.aggs)
        order_vals = tuple(_order_value(plan, o, out, members, numeric_text) for o in plan.order)
        items.append((out, order_vals + tuple(gkey)))
    sort_keys = [o.desc for o in plan.order] + [False] * len(plan.keys)
    ordered = _sorted(items, sort_keys) if plan.keys else items
    return PlanResult([o for o, _ in ordered][: plan.limit], len(items), bad, bad_dates, text_numeric, two_digit, plan.current_year)


def fake_run_plans(log: list | None = None):
    """Reemplazo de data_query_engine.run_plans para la BD emulada: usa las filas de FakeOrgDB."""

    async def run_plans(pool, plans):
        if log is not None:
            log.extend(plans)
        await asyncio.sleep(0)   # como la BD real, cede el control: sin esto las carreras entre llamadas no se ven
        return [run_plan(pool.db.rows_of(p.table_id), p) for p in plans]

    return run_plans


def fake_run_plan_on():
    """Reemplazo de data_query_engine.run_plan_on (lo usa el rango de fechas al cargar datos) para FakeConn."""

    async def run_plan_on(conn, plan):
        return run_plan(conn.db.rows_of(plan.table_id), plan)

    return run_plan_on
