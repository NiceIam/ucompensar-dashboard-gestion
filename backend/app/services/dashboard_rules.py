"""Regla DETERMINISTA de tableros sugeridos (sin IA) — PI0320251.

Con solo los TIPOS del catalogo (fecha, medida, categoria) arma tableros utiles: no gasta tokens, es
reproducible y sirve cuando no hay clave de Gemini, no hay cupo o el modelo fallo.

  fecha + medida     -> serie por mes (o dia/año segun el rango de fechas) de la suma de la medida
  categoria + medida -> top 10 de la categoria por suma de la medida
  segunda categoria  -> torta (pocas categorias) o barras de cantidad
  siempre            -> cifras: suma de la medida y cantidad de registros

La medida se elige por nombre (dinero primero, nunca un identificador) y la categoria por nombre y por
cuantos valores distintos tiene (una columna con un valor por fila no agrupa nada).
"""

import logging
from dataclasses import dataclass
from datetime import date

from app.services import chart_specs as cs
from app.services import data_query_engine as engine

logger = logging.getLogger(__name__)

MAX_DASHBOARDS = 3
MAX_WIDGETS = 6
_STATS_COLUMNS = 6
_STATS_TABLES = 4
_PIE_MAX_DISTINCT = 8


@dataclass(frozen=True)
class PlannedDashboard:
    title: str
    widgets: list   # especificaciones como las manda el modelo: {table, chart_type, x, y, filters?, top?}


def _bucket(column) -> str:
    """Granularidad de la serie segun el rango de fechas del catalogo (si no hay rango, por mes)."""
    if column.range:
        try:
            lo, hi = (date.fromisoformat(v) for v in column.range)
        except ValueError:
            return "month"
        days = (hi - lo).days
        if days <= 62:
            return "day"
        if days > 365 * 6:
            return "year"
    return "month"


# Que medida mostrar primero: lo que "se suma" (total, ventas, ingresos...) antes que un precio unitario, y el
# dinero antes que otros numeros (stock, cantidad).
_MEASURE_PRIORITY = (
    "total", "totales", "ingreso", "ingresos", "venta", "ventas", "monto", "montos", "valor", "valores",
    "facturado", "recaudo", "subtotal", "utilidad", "ganancia", "ganancias", "salario", "salarios", "pago",
    "pagos", "gasto", "gastos", "presupuesto", "saldo",
)


def _measure_rank(name: str) -> int:
    tokens = cs._tokens(name)
    for i, word in enumerate(_MEASURE_PRIORITY):
        if word in tokens:
            return i
    return len(_MEASURE_PRIORITY) if cs.is_money_name(name) else len(_MEASURE_PRIORITY) + 1


def _measure(table):
    nums = [c for c in table.columns if c.kind == engine.KIND_NUM and not cs.is_id_name(c.name)]
    return min(nums, key=lambda c: _measure_rank(c.name)) if nums else None


def _categories(table, stats: dict | None) -> list:
    """Columnas buenas para agrupar, de mejor a peor. `stats`: {columna: valores distintos} (opcional)."""
    scored = []
    for i, c in enumerate(table.columns):
        if c.kind == engine.KIND_BOOL:
            score = 3
        elif c.kind == engine.KIND_TEXT:
            score = cs.category_score(c.name)
        else:
            continue
        if score <= 0:
            continue
        distinct = (stats or {}).get(c.name)
        # Sirve para agrupar si tiene 2 o mas valores y NO es casi un valor por fila (nombres, codigos...).
        if distinct is not None and not (distinct >= 2 and (distinct <= 25 or distinct <= table.rows * 0.8)):
            continue
        scored.append((-score, i, c, distinct))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [(c, distinct) for _, _, c, distinct in scored]


_UNIT_PRICE_WORDS = frozenset({"precio", "precios", "costo", "costos", "tarifa", "tarifas"})


def _aggregate(measure) -> str:
    """Un precio unitario no se suma: se promedia. Lo demas (total, ventas, stock...) se suma."""
    if measure is None:
        return "count"
    fn = "avg" if any(t in _UNIT_PRICE_WORDS for t in cs._tokens(measure.name)) else "sum"
    return f"{fn}({measure.name})"


def _plan_table(table, stats: dict | None, max_widgets: int):
    measure = _measure(table)
    dates = [c for c in table.columns if c.kind == engine.KIND_DATE]
    cats = _categories(table, stats)
    value = _aggregate(measure)
    widgets = []
    if measure:
        widgets.append({"table": table.name, "chart_type": "kpi", "y": value})
    widgets.append({"table": table.name, "chart_type": "kpi", "y": "count"})
    if dates:
        widgets.append({
            "table": table.name, "chart_type": "line", "x": f"{_bucket(dates[0])}({dates[0].name})", "y": value,
        })
    if cats:
        widgets.append({"table": table.name, "chart_type": "bar", "x": cats[0][0].name, "y": value, "top": 10})
    if len(cats) > 1:
        # Una torta solo con pocas categorias (se sabe por las estadisticas); si no, barras de la siguiente.
        rest = cats[1:]
        pie = next(((c, d) for c, d in rest if d is not None and d <= _PIE_MAX_DISTINCT), None)
        if pie:
            widgets.append({"table": table.name, "chart_type": "pie", "x": pie[0].name, "y": "count"})
        else:
            widgets.append({"table": table.name, "chart_type": "bar", "x": rest[0][0].name, "y": "count", "top": 10})
    elif not cats and not dates and not measure:
        # Hoja solo de texto: lo unico que se puede mostrar es una distribucion por la primera columna de texto.
        first = next((c for c in table.columns if c.kind == engine.KIND_TEXT and not cs.is_id_name(c.name)), None)
        if first:
            widgets.append({"table": table.name, "chart_type": "bar", "x": first.name, "y": "count", "top": 10})
    return widgets[:max_widgets]


def _interest(table) -> tuple:
    """Orden de las hojas: primero las que tienen fecha y medida, luego por cantidad de filas."""
    has_measure = _measure(table) is not None
    has_date = any(c.kind == engine.KIND_DATE for c in table.columns)
    return (-(has_measure + has_date), -table.rows, table.name)


def plan_dashboards(catalog: dict, stats: dict | None = None, *, max_dashboards: int = MAX_DASHBOARDS,
                    max_widgets: int = MAX_WIDGETS) -> list[PlannedDashboard]:
    """Hasta `max_dashboards` tableros (uno por hoja con datos). `stats`: {hoja: {columna: distintos}}."""
    tables = sorted((t for t in catalog.values() if t.rows > 0 and t.columns), key=_interest)
    out = []
    for table in tables[:max_dashboards]:
        widgets = _plan_table(table, (stats or {}).get(table.name), max_widgets)
        if widgets:
            out.append(PlannedDashboard(cs.sanitize_title(f"Resumen de {table.display}", 80, "Resumen"), widgets))
    return out


def default_specs(catalog: dict, limit: int = 12) -> list[cs.Spec]:
    """Widgets por defecto de un tablero SIN especificaciones guardadas (los hechos antes de esta funcion):
    la misma regla, sin consultas previas, calculada con el motor sobre todas las filas."""
    specs: list[cs.Spec] = []
    for planned in plan_dashboards(catalog, max_dashboards=3, max_widgets=4):
        for raw in planned.widgets:
            if raw["chart_type"] == "kpi":
                continue                 # las cifras por hoja salen del catalogo (filas), sin consultas
            try:
                specs.append(cs.parse_spec(catalog, raw))
            except engine.QueryError:
                continue
    return specs[:limit]


async def gather_stats(pool, catalog: dict) -> dict:
    """Valores distintos de las columnas candidatas a categoria (UNA consulta por hoja). Es opcional: si falla,
    la regla sigue sin ese dato."""
    stats: dict = {}
    tables = sorted((t for t in catalog.values() if t.rows > 0 and t.columns), key=_interest)[:_STATS_TABLES]
    for table in tables:
        candidates = [c for c, _ in _categories(table, None)][:_STATS_COLUMNS]
        if not candidates:
            continue
        try:
            plan = engine.build_plan(
                table, aggregates=[f"count_distinct({c.name})" for c in candidates], max_rows=1,
            )
            (result,) = await engine.run_plans(pool, [plan])
        except Exception as exc:
            logger.warning("No se pudieron contar valores distintos: %s", type(exc).__name__)
            continue
        if result.rows:
            stats[table.name] = {
                c.name: int(v) for c, v in zip(candidates, result.rows[0]) if v is not None
            }
    return stats
