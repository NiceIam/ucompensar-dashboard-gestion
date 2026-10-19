"""Especificaciones declarativas de graficos y cifras (KPI) de un tablero — PI0320251.

Un widget de tablero NO guarda datos: guarda una ESPECIFICACION (tabla, tipo, x, y, filtros, top) que el motor
de consultas (data_query_engine) valida contra el catalogo de la organizacion y calcula en SQL sobre TODAS las
filas cada vez que se abre el tablero. Lo comparten la herramienta `create_dashboard` del chat, las sugerencias
y la ruta que calcula el tablero (`/execute`).

Reglas de seguridad:
- El modelo (o quien escriba por REST) nunca aporta SQL, ids, colores ni posiciones: solo las claves de
  SPEC_KEYS, validadas con el motor (lista blanca contra el catalogo).
- Lo que se guarda es lo que el motor reconoce (nombre canonico de tabla, etiqueta canonica de la clave y del
  agregado); al leer se vuelve a validar completo: la API REST permite escribir cualquier `data_source_query`.
- Los titulos de tablero pasan por `sanitize_title` (lista blanca de caracteres).
"""

import asyncio
import hashlib
import json
import logging
import math
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from app.services import data_query_engine as engine

logger = logging.getLogger(__name__)

SPEC_VERSION = 1
KINDS = ("bar", "line", "pie", "kpi")
CHART_KINDS = ("bar", "line", "pie")
WIDGET_TYPE = {"bar": "bar_chart", "line": "line_chart", "pie": "pie_chart", "kpi": "kpi_card"}
KIND_OF_WIDGET = {v: k for k, v in WIDGET_TYPE.items()}
# Claves que el modelo puede mandar por grafico. Nada de ids, colores, posiciones ni titulos libres.
SPEC_KEYS = ("table", "chart_type", "x", "y", "filters", "top")
_STORED_KEYS = frozenset({"v", "by", "fp", "sig", "table", "x", "y", "filters", "top"})
MAX_SPEC_BYTES = 2048          # tamano serializado de UN grafico recibido del modelo
MAX_STORED_BYTES = 4096        # tamano maximo tolerado al LEER un widget guardado (puede venir de REST)
MAX_TOP = 20
MAX_PREVIEW_POINTS = 12

CHART_COLORS = {"bar": "#3b82f6", "line": "#10b981", "pie": "#8b5cf6"}
CHART_MAX_POINTS = {"bar": 20, "line": 60, "pie": 10}
# Una torta muestra partes de un total: solo con agregados que se suman, y si hay mas categorias que
# porciones, las sobrantes van a "Otros" (recortarlas haria que las porciones visibles sumaran 100%).
PIE_AGGS = ("count", "sum")
KPI_AGGS = ("count", "count_distinct", "sum", "avg", "min", "max")
AGG_TITLES = {
    "count": "Cantidad", "count_distinct": "Distintos de {c}", "sum": "Suma de {c}",
    "avg": "Promedio de {c}", "min": "Mínimo de {c}", "max": "Máximo de {c}",
}
BUCKET_TITLES = {"day": "día", "week": "semana", "month": "mes", "year": "año"}


# ---------------------------------------------------------------------------
# Nombres: dinero, identificadores, titulos saneados
# ---------------------------------------------------------------------------

def _tokens(name: str) -> list[str]:
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    return [t for t in re.split(r"[^a-z0-9]+", text) if t]


MONEY_WORDS = frozenset({
    "precio", "precios", "valor", "valores", "costo", "costos", "monto", "montos", "ingreso", "ingresos",
    "venta", "ventas", "salario", "salarios", "pago", "pagos", "subtotal", "total", "totales", "iva",
    "descuento", "descuentos", "tarifa", "tarifas", "saldo", "deuda", "abono", "abonos", "utilidad",
    "ganancia", "ganancias", "gasto", "gastos", "presupuesto", "facturado", "recaudo",
})
_ID_WORDS = frozenset({
    "id", "uuid", "codigo", "cod", "nit", "cedula", "cc", "documento", "doc", "telefono", "tel", "celular",
    "movil", "email", "correo", "mail", "numero", "nro", "num", "no", "sku", "ean", "referencia", "ref",
    "consecutivo", "radicado", "placa", "serial", "url", "link", "index", "idx", "unnamed", "rownum", "rowid",
    "factura",
})
_FREE_TEXT_WORDS = frozenset({
    "descripcion", "detalle", "observacion", "observaciones", "comentario", "comentarios", "nota", "notas",
    "direccion", "mensaje", "texto",
})
_CATEGORY_HINTS = (
    "region", "ciudad", "departamento", "municipio", "sede", "sucursal", "zona", "pais", "barrio", "categoria",
    "linea", "marca", "producto", "servicio", "plato", "cliente", "proveedor", "vendedor", "asesor", "canal",
    "tipo", "estado", "metodo", "medio", "area", "cargo", "segmento", "mesa", "bodega",
)


def is_money_name(name: str) -> bool:
    return any(t in MONEY_WORDS for t in _tokens(name))


def is_id_name(name: str) -> bool:
    tokens = _tokens(name)
    if re.fullmatch(r"\s*(#+|n\s*[°º]|nro\.?|[ií]ndice)\s*", str(name), re.I):
        return True
    return bool(tokens) and any(t in _ID_WORDS for t in tokens) and not any(
        t in MONEY_WORDS and t != "iva" for t in tokens
    )


def is_free_text_name(name: str) -> bool:
    return any(t in _FREE_TEXT_WORDS for t in _tokens(name))


def category_score(name: str) -> int:
    """Que tan buena categoria para agrupar es una columna de texto por su NOMBRE (0 = no sirve)."""
    if is_id_name(name) or is_free_text_name(name):
        return 0
    tokens = _tokens(name)
    for i, hint in enumerate(_CATEGORY_HINTS):
        if hint in tokens:
            return 100 - i
    return 5 if "nombre" in tokens else 10


_TITLE_ALLOWED = re.compile(r"[^\w .,:;()\-/&%$#+°]", re.U)


def sanitize_title(text, limit: int = 80, default: str = "Tablero del asistente") -> str:
    """Titulo seguro para guardar, mostrar y volver a mandar al modelo: una linea, lista blanca de caracteres.

    Quita control y Unicode de separacion, y reemplaza por espacio todo lo que no sea letra, digito, espacio o
    `.,:;()-_/&%$#+°` (comillas, backticks, `<>`, `\\` y marcas bidireccionales incluidos)."""
    if not isinstance(text, str):
        return default
    clean = engine.one_line(text, limit * 3)
    clean = "".join(ch if unicodedata.category(ch)[0] != "C" else " " for ch in clean)
    clean = _TITLE_ALLOWED.sub(" ", clean)
    clean = re.sub(r"\s+", " ", clean).strip(" .,:;-_/")
    if len(clean) > limit:
        clean = clean[:limit].rstrip(" .,:;-_/(")
    return clean if re.search(r"[^\W_]", clean) else default


# ---------------------------------------------------------------------------
# Especificacion
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Spec:
    table: str                      # nombre canonico de la tabla (table.name): sobrevive a recargas de la tabla
    kind: str                       # bar | line | pie | kpi
    x: str | None                   # etiqueta canonica de la clave ("producto", "month(fecha)"); None en kpi
    y: str                          # etiqueta canonica del agregado ("sum(total)", "count")
    filters: tuple = ()             # ((col, op, valor...), ...) como los valido el motor
    top: int | None = None

    @property
    def widget_type(self) -> str:
        return WIDGET_TYPE[self.kind]

    def stored(self, **extra) -> dict:
        """`data_source_query` del widget. `extra`: by, fp, sig."""
        out = {"v": SPEC_VERSION, **{k: v for k, v in extra.items() if v}, "table": self.table, "y": self.y}
        if self.x:
            out["x"] = self.x
        if self.filters:
            out["filters"] = [list(f) for f in self.filters]
        if self.top:
            out["top"] = self.top
        return out

    def canonical(self) -> list:
        return [self.table, self.kind, self.x, self.y, [list(f) for f in self.filters], self.top]


def fingerprint(specs: list[Spec]) -> str:
    """Huella del CONTENIDO de un tablero (no del titulo): mismas especificaciones, misma huella."""
    parts = sorted(json.dumps(s.canonical(), sort_keys=True, ensure_ascii=False) for s in specs)
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def _size(obj) -> int:
    return len(json.dumps(obj, ensure_ascii=False, default=str))


def _norm_filters(table, filters) -> tuple:
    """Filtros validados por el motor y reescritos en forma canonica: (columna canonica, operador, valores...)."""
    out = []
    for raw in engine._filter_list(filters):
        parsed = engine._parse_filter(table, raw)
        if isinstance(raw, dict):
            vals = raw.get("values", raw.get("value", raw.get("val")))
            vals = [] if vals is None else (list(vals) if isinstance(vals, (list, tuple)) else [vals])
        else:
            vals = list(raw[2:])
        if len(vals) == 1 and isinstance(vals[0], (list, tuple)):
            vals = list(vals[0])
        out.append(tuple([parsed.col.name, parsed.op, *([] if parsed.op in ("null", "notnull") else vals)]))
    return tuple(out)


def _top(value, kind: str) -> int | None:
    if value is None or value == "" or kind in ("line", "kpi"):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise engine.QueryError("top debe ser un número entero entre 1 y %d" % MAX_TOP)
    try:
        n = int(float(value))
    except (TypeError, ValueError, OverflowError):
        raise engine.QueryError("top debe ser un número entero entre 1 y %d" % MAX_TOP)
    return max(1, min(n, MAX_TOP))


def _plan_args(kind: str, x, y: str, filters, top: int | None) -> tuple[dict, int]:
    points = min(CHART_MAX_POINTS.get(kind, 1), top) if top else CHART_MAX_POINTS.get(kind, 1)
    spec = {"filters": filters, "aggregates": [y or "count"], "limit": points, "max_rows": points}
    if kind != "kpi":
        spec["group_by"] = [x]
    else:
        spec["limit"] = spec["max_rows"] = 1
    return spec, points


def parse_spec(catalog: dict, raw) -> Spec:
    """Valida UN grafico recibido (del modelo o de un widget guardado) y lo devuelve en forma canonica.

    Lanza engine.QueryError con un mensaje corto y accionable. No ejecuta ninguna consulta."""
    if not isinstance(raw, dict):
        raise engine.QueryError("cada gráfico debe ser un objeto con table, chart_type, x, y")
    unknown = [k for k in raw if k not in SPEC_KEYS]
    if unknown:
        raise engine.QueryError(f"argumento no válido '{engine.one_line(str(unknown[0]), 40)}' en un gráfico; válidos: {', '.join(SPEC_KEYS)}")
    if _size(raw) > MAX_SPEC_BYTES:
        raise engine.QueryError(f"un gráfico no puede pesar más de {MAX_SPEC_BYTES} caracteres")
    kind = raw.get("chart_type")
    kind = kind.strip().lower() if isinstance(kind, str) else ""
    if kind not in KINDS:
        raise engine.QueryError("chart_type debe ser bar, line, pie o kpi")
    for key in ("x", "y"):
        if raw.get(key) is not None and not isinstance(raw.get(key), str):
            raise engine.QueryError(f"'{key}' debe ser texto")
    table = engine.resolve_table(catalog, raw.get("table"))
    y = (raw.get("y") or "count").strip() or "count"
    x = raw.get("x")
    if kind == "kpi":
        x = None
    elif not isinstance(x, str) or not x.strip():
        raise engine.QueryError("falta 'x' (la columna por la que agrupar)")
    top = _top(raw.get("top"), kind)
    filters = _norm_filters(table, raw.get("filters"))

    args, _ = _plan_args(kind, x, y, [list(f) for f in filters], top)
    plan = engine.build_plan(table, **args)
    agg = plan.aggs[0]
    if agg.mode in (engine.KIND_TEXT, engine.KIND_DATE):
        raise engine.QueryError("y debe ser numérico: count o sum|avg|min|max de una columna numérica")
    if kind == "pie" and agg.fn not in PIE_AGGS:
        raise engine.QueryError("pie solo con count o sum (partes de un total); usa bar")
    if kind == "kpi" and agg.fn not in KPI_AGGS:
        raise engine.QueryError("kpi: usa count o sum|avg|min|max de una columna numérica")
    key = plan.keys[0].label if plan.keys else None
    return Spec(table.name, kind, key, agg.label, filters, top)


def parse_stored(catalog: dict, dsq, widget_type: str) -> Spec:
    """Valida el `data_source_query` de un widget guardado. NO es de confianza: cualquier usuario autenticado de
    la organizacion puede escribirlo por REST (forma, tamano, version y contenido se comprueban otra vez)."""
    if isinstance(dsq, str):
        try:
            dsq = json.loads(dsq)
        except (TypeError, ValueError):
            raise engine.QueryError("el gráfico guardado no se puede leer")
    if not isinstance(dsq, dict) or dsq.get("v") != SPEC_VERSION:
        raise engine.QueryError("este gráfico no tiene una consulta guardada")
    if _size(dsq) > MAX_STORED_BYTES or any(k not in _STORED_KEYS for k in dsq):
        raise engine.QueryError("la consulta guardada de este gráfico no es válida")
    kind = KIND_OF_WIDGET.get(widget_type)
    if kind is None:
        raise engine.QueryError("tipo de gráfico no compatible")
    return parse_spec(catalog, {
        "table": dsq.get("table"), "chart_type": kind, "x": dsq.get("x"), "y": dsq.get("y"),
        "filters": dsq.get("filters"), "top": dsq.get("top"),
    })


# ---------------------------------------------------------------------------
# Calculo (motor) -> grafico o cifra
# ---------------------------------------------------------------------------

def chart_number(value) -> int | float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number):
        return None
    if isinstance(value, Decimal) and value == value.to_integral_value() and abs(number) < 1e15:
        return int(value)
    return int(number) if number == int(number) and abs(number) < 1e15 else round(number, 2)


def chart_title(key, agg) -> str:
    what = AGG_TITLES[agg.fn].format(c=agg.col.name if agg.col else "")
    by = f"{BUCKET_TITLES[key.bucket]} de {key.col.name}" if key.bucket else key.col.name
    return f"{what} por {by}"


def unit_of(agg) -> str:
    """Unidad de la cifra: 'count' (conteos), 'money' si la columna medida tiene nombre de dinero, 'number'."""
    if agg.fn in ("count", "count_distinct") or agg.col is None:
        return "count"
    return "money" if is_money_name(agg.col.name) else "number"


async def build_chart(pool, table, kind: str, x: str, y: str, filters, title=None, top: int | None = None) -> tuple[dict, dict]:
    """Datos del grafico con el mismo motor de query_table. Devuelve (grafico para el frontend, respuesta al modelo)."""
    spec, points = _plan_args(kind, x, y, filters, top)
    plan = engine.build_plan(table, **spec)
    key, agg = plan.keys[0], plan.aggs[0]
    if agg.mode in (engine.KIND_TEXT, engine.KIND_DATE):
        raise engine.QueryError("y debe ser numérico: count o sum|avg|min|max de una columna numérica")
    if kind == "line" and not key.bucket:
        plan = engine.build_plan(table, **spec, order_by=[key.label])     # una linea va en orden de x
    plans = [plan]
    if kind == "pie":
        if agg.fn not in PIE_AGGS:
            raise engine.QueryError("pie solo con count o sum (partes de un total); usa bar")
        plans.append(engine.build_plan(table, filters=filters, aggregates=[y or "count"], max_rows=1))
        if agg.fn == "sum":
            # El menor valor de TODOS los grupos: un negativo escondido en "Otros" tambien invalida la torta.
            plans.append(engine.build_plan(table, filters=filters, group_by=[x], aggregates=[y],
                                           order_by=[agg.label], limit=1, max_rows=1))
    results = await engine.run_plans(pool, plans)
    if kind == "pie" and agg.fn == "sum" and results[2].rows and (results[2].rows[0][1] or 0) < 0:
        raise engine.QueryError("pie no admite valores negativos; usa bar")
    result = results[0]
    rows = result.rows
    others = None
    if kind == "pie" and result.total > len(rows):
        rows = rows[: points - 1]
        grand = results[1].rows[0][0] if results[1].rows else None
        shown = sum((v for _, v in rows if v is not None), 0)
        others = (grand or 0) - shown
    data = []
    for label, value in rows:
        number = chart_number(value)
        if number is not None:
            data.append({"name": engine.cell(label, 30) if label is not None else "(sin dato)", "value": number})
    if others is not None and chart_number(others):
        data.append({"name": f"Otros ({result.total - len(rows)})", "value": chart_number(others)})
    if not data:
        raise engine.QueryError("sin datos para graficar con esos filtros")
    if kind == "pie" and any(point["value"] < 0 for point in data):
        raise engine.QueryError("pie no admite valores negativos; usa bar")
    chart = {
        "type": kind,
        "title": engine.cell(title if isinstance(title, str) and title.strip() else chart_title(key, agg), 80),
        "data": data,
        "x": "name",
        "y": "value",
        "color": CHART_COLORS[kind],
        "unit": unit_of(agg),
    }
    out = {"ok": True, "puntos": len(data)}
    if result.total > len(result.rows) or others is not None:
        out["de"] = result.total
    return chart, out


_KPI_ICONS = {"count": "Database", "money": "DollarSign", "number": "TrendingUp"}


async def build_kpi(pool, table, y: str, filters, title=None) -> dict:
    """Una cifra (agregado sin agrupar) calculada sobre TODAS las filas, con su unidad explicita."""
    args, _ = _plan_args("kpi", None, y, filters, None)
    plan = engine.build_plan(table, **args)
    agg = plan.aggs[0]
    if agg.mode in (engine.KIND_TEXT, engine.KIND_DATE):
        raise engine.QueryError("y debe ser numérico: count o sum|avg|min|max de una columna numérica")
    if agg.fn not in KPI_AGGS:
        raise engine.QueryError("kpi: usa count o sum|avg|min|max de una columna numérica")
    (result,) = await engine.run_plans(pool, [plan])
    value = chart_number(result.rows[0][0]) if result.rows else None
    if value is None:
        raise engine.QueryError("sin datos para calcular esta cifra con esos filtros")
    unit = unit_of(agg)
    if title:
        label = engine.cell(title, 80)
    elif agg.fn == "count":
        label = f"Registros de {engine.cell(table.display, 40)}"
    else:
        label = engine.cell(AGG_TITLES[agg.fn].format(c=agg.col.name if agg.col else ""), 80)
    kpi = {"label": label, "value": value, "unit": unit, "icon": _KPI_ICONS[unit]}
    if agg.col is not None:
        kpi["column"] = engine.cell(agg.col.name, 60)
    return kpi


async def run_spec(pool, catalog: dict, spec: Spec, title=None) -> dict:
    """Calcula un widget y devuelve {"kind": "chart"|"kpi", "chart"|"kpi": ...}. Lanza engine.QueryError."""
    table = engine.resolve_table(catalog, spec.table)
    filters = [list(f) for f in spec.filters]
    if spec.kind == "kpi":
        return {"kind": "kpi", "kpi": await build_kpi(pool, table, spec.y, filters, title)}
    chart, _ = await build_chart(pool, table, spec.kind, spec.x, spec.y, filters, title, spec.top)
    return {"kind": "chart", "chart": chart}


def preview_of(chart: dict) -> dict:
    """Solo NUMEROS (nunca texto de celdas) para la vista previa de la tarjeta del tablero."""
    points = [p["value"] for p in chart["data"] if isinstance(p.get("value"), (int, float))]
    return {"type": chart["type"], "points": points[:MAX_PREVIEW_POINTS]}


_QUERY_CANCELED = "57014"   # SQLSTATE query_canceled (statement_timeout)
_ERR_TIMEOUT = "este gráfico tardó demasiado en calcularse"
_ERR_INTERNAL = "no se pudo calcular este gráfico"


async def run_many(pool, catalog: dict, specs: list[Spec], titles: list | None = None, *,
                   timeout: float, concurrency: int = 3) -> list[dict]:
    """Calcula varios widgets con el motor, con el error AISLADO por widget y un tope de tiempo global.

    Devuelve, en el mismo orden, {"ok": True, "kind": "chart"|"kpi", "chart"|"kpi": ...} o
    {"ok": False, "error": "mensaje corto"}. Nunca lanza: un widget roto o lento no tumba a los demas."""
    titles = titles or [None] * len(specs)
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def one(i: int) -> dict:
        async with semaphore:
            try:
                return {"ok": True, **await run_spec(pool, catalog, specs[i], titles[i])}
            except engine.QueryError as exc:
                return {"ok": False, "error": engine.one_line(str(exc), 200)}
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if getattr(exc, "sqlstate", None) == _QUERY_CANCELED:
                    return {"ok": False, "error": _ERR_TIMEOUT}
                # Sin el mensaje: un error de la BD puede citar valores de celdas (datos del usuario).
                logger.error("Widget no calculable: %s (sqlstate=%s)", type(exc).__name__, getattr(exc, "sqlstate", None))
                return {"ok": False, "error": _ERR_INTERNAL}

    tasks = [asyncio.ensure_future(one(i)) for i in range(len(specs))]
    if not tasks:
        return []
    _done, pending = await asyncio.wait(tasks, timeout=max(0.1, timeout))
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    return [t.result() if t not in pending else {"ok": False, "error": _ERR_TIMEOUT} for t in tasks]
