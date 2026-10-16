"""Motor de consultas declarativas sobre las tablas virtuales de una organizacion — PI0320251.

Lo usan las herramientas del chat (agent_tools_service). El modelo NUNCA escribe SQL: manda una
especificacion (tabla, columnas, filtros, agrupacion, agregados, orden, limite) que aqui se valida contra
el catalogo de la org (org_data_tables) y se compila a UNA consulta parametrizada:
- Tabla y columnas solo de la lista blanca del catalogo. Los nombres de columna viajan como PARAMETROS
  (data->>$n), nunca interpolados; operadores, funciones y buckets salen de listas blancas fijas.
- Valores siempre como parametros con cast explicito; limites numericos acotados.
- Casteo tolerante por celda: un numero guardado como texto ("300") cuenta; uno no numerico ("n/a") o con
  mas de 200 caracteres se ignora y se informa, sin tumbar la consulta. Nada de esto puede lanzar un error de
  Postgres por una celda mala.
- Fechas de celda: AAAA-MM-DD[hora], AAAA/M/D, D/M/AAAA[hora], D/M/AA, AAAA-MM (dia 1) y AAAAMMDD; con
  '-', '/' o '.'. Siempre DIA/MES (formato colombiano): 03/15/2026 NO se lee como 15 de marzo. Año de 2
  digitos: ventana deslizante sobre el año actual (ver two_digit_window) y SIEMPRE una nota con cuantas
  fechas se interpretaron asi y con que ventana (un 55 -> 2055 silencioso es peor que una ilegible). Una celda con valor que
  no se puede leer (15-mar-2026, "March 15, 2026", 2026-02-30) queda "sin fecha" y SIEMPRE se informa al
  modelo cuantas hubo ("N valores de fecha ilegibles"), para que un 0 no parezca una respuesta real.
- Mismo criterio para filtrar y agrupar: '=' / 'in' ignoran mayusculas y espacios en los extremos, y
  group_by / count_distinct agrupan igual (etiqueta = la variante original menor en orden de bytes).
  Columnas numericas se agrupan por valor (100 = 100.0) y las de fecha por dia. Las columnas si/no (tipo
  boolean en el catalogo) se agrupan por valor logico con etiqueta "sí"/"no": true, "SI", 1, "verdadero"...
  van juntos, igual que en el filtro '= true'. Solo si el catalogo dice boolean: una columna numerica de
  0/1 (cantidades, codigos) o un texto con "si"/"no" se siguen tratando como numero o texto, porque
  convertirlos cambiaria cifras que el usuario no pidio interpretar como logicas.
- Columna declarada texto con mayoria de valores numericos: min/max/orden son numericos (los no numericos
  se ignoran o van al final, con nota); si no hay mayoria, alfabeticos (con nota si habia numeros).
- Sin order_by, las filas salen en orden de carga (created_at y posicion fisica ctid): determinista, pero
  aproximado despues de borrados (Postgres puede reusar el espacio).
- REQUISITO DE LOCALE: lower()/ILIKE sobre texto no ASCII dependen del locale/proveedor de la BD. Con un
  locale "C" de libc, 'ÑANDÚ' no se iguala con 'ñandú'. Verificar en produccion:
  SELECT lower('ÑANDÚ') = 'ñandú'  -- debe dar true (probado con el proveedor builtin C.UTF-8 de PG 18).
- Se ejecuta en una transaccion de SOLO LECTURA con statement_timeout (defensa en profundidad).

`run_plans` es la unica funcion que toca la BD; los tests con la BD emulada la reemplazan por un oraculo
en pandas (tests/query_oracle.py) y los de Postgres real la ejecutan tal cual.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

# Tipos de columnas_definition -> clase de dato: t texto, n numero, f fecha, b si/no.
KIND_TEXT, KIND_NUM, KIND_DATE, KIND_BOOL = "t", "n", "f", "b"
_TYPE_KIND = {
    "number": KIND_NUM, "integer": KIND_NUM, "float": KIND_NUM, "numeric": KIND_NUM, "decimal": KIND_NUM,
    "date": KIND_DATE, "datetime": KIND_DATE, "timestamp": KIND_DATE,
    "boolean": KIND_BOOL, "bool": KIND_BOOL,
}

DEFAULT_LIMIT = 20
MAX_FILTERS = 10
MAX_KEYS = 4
MAX_AGGS = 8
MAX_SELECT = 12
MAX_ORDER = 3
MAX_IN_VALUES = 50
MAX_VALUE_CHARS = 200
STATEMENT_TIMEOUT_MS = 8000
_CELL_CHARS = 60
_RAW_DEFAULT_COLUMNS = 8

OPS = ("=", "!=", ">", ">=", "<", "<=", "in", "contains", "null", "notnull")
_OP_ALIASES = {
    "==": "=", "eq": "=", "<>": "!=", "ne": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<=",
    "like": "contains", "ilike": "contains", "is null": "null", "isnull": "null",
    "is not null": "notnull", "not null": "notnull",
}
BUCKETS = ("day", "week", "month", "year")
_BUCKET_ALIASES = {
    "day": "day", "dia": "day", "día": "day", "week": "week", "semana": "week",
    "month": "month", "mes": "month", "year": "year", "anio": "year", "año": "year", "ano": "year",
}
_AGG_ALIASES = {
    "count": "count", "count_distinct": "count_distinct", "countdistinct": "count_distinct",
    "distinct": "count_distinct", "sum": "sum", "avg": "avg", "mean": "avg", "min": "min", "max": "max",
}

# Mismas reglas en Python (validar valores de filtros) y en SQL (celdas). Solo [0-9]: \d aceptaria
# digitos Unicode que luego ::numeric rechazaria con error. Largo acotado: una celda de >131072 digitos haria
# fallar ::numeric y con el la consulta de TODA la columna (se cuenta como no numerica). Se acota con length()
# y no con {1,n} en la regex: la repeticion acotada hacia 7x mas lenta la regex de Postgres (medido).
_NUM_BODY = r"[ ]*[-+]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][-+]?[0-9]{1,3})?[ ]*"
_NUM_RE = re.compile(_NUM_BODY)
_NUM_SQL = f"'^{_NUM_BODY}$'"
MAX_NUMBER_CHARS = 200
# Fecha de celda; ramas mutuamente excluyentes (ninguna cadena encaja en dos):
#   1-3 AAAA-M-D[...]   4-6 D/M/AAAA[...]   7-9 D/M/AA[...]   10-11 AAAA-MM   12-14 AAAAMMDD
_DATE_SQL = (
    "'^[ ]*(?:([0-9]{4})[-/.]([0-9]{1,2})[-/.]([0-9]{1,2})"
    "|([0-9]{1,2})[-/.]([0-9]{1,2})[-/.]([0-9]{4})"
    "|([0-9]{1,2})[-/.]([0-9]{1,2})[-/.]([0-9]{2})(?![0-9])"
    "|([0-9]{4})[-/.]([0-9]{1,2})[ ]*$"
    "|([0-9]{4})([0-9]{2})([0-9]{2})[ ]*$)'"
)
# Año de 2 digitos: AA <= (año actual % 100) + margen -> siglo actual; si no, el anterior. En 2026:
# 00-31 -> 2000-2031 y 32-99 -> 1932-1999. El margen deja pasar fechas cercanas al futuro (vencimientos,
# contratos, cuotas) sin mandar al futuro nacimientos o fechas historicas (un pivote fijo de 68 convertia
# 15/03/55 en 2055). Ninguna ventana acierta siempre: por eso cada consulta informa cuantas uso.
TWO_DIGIT_YEAR_MARGIN = 5


def today() -> date:
    """Fecha de hoy para la ventana de años de 2 digitos (los tests la reemplazan para fijar el año)."""
    return date.today()


def two_digit_window(current_year: int) -> tuple[int, int]:
    """(pivote, siglo): AA <= pivote -> siglo + AA; si no -> siglo - 100 + AA."""
    return min(current_year % 100 + TWO_DIGIT_YEAR_MARGIN, 99), current_year // 100 * 100


def two_digit_rule(current_year: int) -> str:
    pivot, century = two_digit_window(current_year)
    rule = f"00-{pivot:02d} -> {century:04d}-{century + pivot:04d}"
    if pivot < 99:
        rule += f", {pivot + 1:02d}-99 -> {century - 100 + pivot + 1:04d}-{century - 1:04d}"
    return rule
# Camino rapido para el caso comun (ISO canonico): `~` + substr cuesta ~8x menos que regexp_match.
_ISO_FAST_SQL = "'^[ ]*[0-9]{4}-[0-9]{2}-[0-9]{2}'"
_TRUE_WORDS = ("true", "t", "1", "si", "sí", "yes", "verdadero")
_FALSE_WORDS = ("false", "f", "0", "no", "falso")

_CALL_RE = re.compile(r"^\s*([^\W\d]\w*)\s*\((.*)\)\s*$", re.S)
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f  ]+")


class QueryError(ValueError):
    """Especificacion invalida. El mensaje es CORTO y accionable: se devuelve tal cual al modelo."""


# ---------------------------------------------------------------------------
# Catalogo
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Column:
    name: str
    kind: str


@dataclass(frozen=True)
class Table:
    id: Any
    name: str
    display: str
    rows: int
    columns: tuple[Column, ...]

    def column(self, name: str) -> Column | None:
        for c in self.columns:
            if c.name == name:
                return c
        folded = fold_name(name)
        return next((c for c in self.columns if fold_name(c.name) == folded), None)


def fold_name(name: str) -> str:
    return re.sub(r"[\s_]+", "_", name.strip()).casefold()


def build_catalog(records) -> dict[str, Table]:
    """Filas de org_data_tables -> {table_name: Table}, ordenado por nombre (prompt estable).

    Tolera columns_definition como texto JSON o lista, y entradas mal formadas (se omiten).
    """
    catalog: dict[str, Table] = {}
    for r in records:
        cols = r["columns_definition"]
        if isinstance(cols, str):
            try:
                cols = json.loads(cols)
            except (json.JSONDecodeError, TypeError):
                cols = []
        columns, seen = [], set()
        for c in cols if isinstance(cols, list) else []:
            name = c.get("name") if isinstance(c, dict) else None
            if not isinstance(name, str) or not name or name in seen:
                continue
            seen.add(name)
            kind = _TYPE_KIND.get(str(c.get("type") or "").lower(), KIND_TEXT)
            columns.append(Column(name, kind))
        catalog[r["table_name"]] = Table(
            id=r["id"], name=r["table_name"], display=r["display_name"] or r["table_name"],
            rows=r["row_count"] or 0, columns=tuple(columns),
        )
    return dict(sorted(catalog.items()))


def resolve_table(catalog: dict[str, Table], name) -> Table:
    if not isinstance(name, str) or not name.strip():
        raise QueryError("falta 'table'")
    key = name.strip()
    table = catalog.get(key)
    if table is None:
        folded = fold_name(key)
        table = next(
            (t for t in catalog.values() if folded in (fold_name(t.name), fold_name(t.display))), None
        )
    if table is None:
        raise QueryError(f"la tabla '{one_line(key)}' no existe; tablas: {_names(list(catalog))}")
    return table


def _resolve_column(table: Table, name) -> Column:
    if not isinstance(name, str) or not name.strip():
        raise QueryError("falta un nombre de columna")
    col = table.column(name)
    if col is None:
        raise QueryError(
            f"la columna '{one_line(name.strip())}' no existe en {one_line(table.name, 60)}; "
            f"columnas: {_names([c.name for c in table.columns])}"
        )
    return col


def one_line(text: str, limit: int = 40) -> str:
    text = _CONTROL.sub(" ", str(text)[: limit * 2]).strip()
    return text[:limit] + "…" if len(text) > limit else text


def _names(names: list[str], limit: int = 30) -> str:
    shown = ", ".join(one_line(n) for n in names[:limit])
    return shown + (f" (+{len(names) - limit})" if len(names) > limit else "") if names else "(ninguna)"


# ---------------------------------------------------------------------------
# Plan validado
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Key:
    """Columna de salida que no es agregado: columna de agrupacion o de seleccion, con bucket opcional."""
    label: str
    col: Column
    bucket: str | None = None


@dataclass(frozen=True)
class Agg:
    label: str
    fn: str                # count | count_distinct | sum | avg | min | max
    col: Column | None     # None solo para count(*)
    mode: str | None = None  # n numerico, f fecha, t texto (min/max/sum/avg); None para count


@dataclass(frozen=True)
class Filter:
    col: Column
    op: str
    mode: str              # n, f, b, t (comparacion) o k (null/notnull)
    values: tuple


@dataclass(frozen=True)
class Order:
    index: int             # posicion en las columnas de salida (keys + aggs)
    desc: bool
    by: str                # out (valor de salida), n (numerico), f (fecha), tn (texto: numerico si la mayoria
                           # de sus valores son numeros, si no alfabetico)


@dataclass(frozen=True)
class Plan:
    table_id: Any
    keys: tuple[Key, ...]
    aggs: tuple[Agg, ...]
    filters: tuple[Filter, ...]
    order: tuple[Order, ...]
    limit: int
    # Año con el que se interpretan los años de 2 digitos (viaja como parametro del SQL, no interpolado).
    current_year: int = field(default_factory=lambda: today().year)

    @property
    def aggregate(self) -> bool:
        return bool(self.aggs)

    @property
    def labels(self) -> list[str]:
        return [k.label for k in self.keys] + [a.label for a in self.aggs]

    def text_compared_columns(self) -> list["Column"]:
        """Columnas de texto con min/max u orden: se comparan como numero si la mayoria de sus valores lo son."""
        cols = [a.col for a in self.aggs if a.fn in ("min", "max") and a.col is not None and a.col.kind == KIND_TEXT]
        cols += [self.order_col(o) for o in self.order if o.by == "tn"]
        return [c for c in self.columns() if c in cols]

    def normalized_columns(self) -> list["Column"]:
        """Columnas agrupadas (group_by sin bucket) o con count_distinct: se comparan normalizadas."""
        cols = [k.col for k in self.keys if not k.bucket] if self.aggregate else []
        cols += [a.col for a in self.aggs if a.fn == "count_distinct"]
        return [c for c in self.columns() if c in cols]

    def order_col(self, o: "Order") -> "Column":
        return self.keys[o.index].col if o.index < len(self.keys) else self.aggs[o.index - len(self.keys)].col

    def date_columns(self) -> list["Column"]:
        """Columnas leidas como fecha (bucket, min/max de fecha, filtro u orden por fecha)."""
        cols = [k.col for k in self.keys if k.bucket] + [a.col for a in self.aggs if a.mode == KIND_DATE]
        cols += [f.col for f in self.filters if f.mode == KIND_DATE]
        cols += [self.keys[o.index].col for o in self.order if o.by == KIND_DATE]
        return [c for c in self.columns() if c in cols]

    def columns(self) -> list[Column]:
        """Columnas referenciadas, sin repetir, en orden de aparicion."""
        out: list[Column] = []
        for c in [k.col for k in self.keys] + [a.col for a in self.aggs if a.col] + [f.col for f in self.filters]:
            if c not in out:
                out.append(c)
        return out


@dataclass
class PlanResult:
    rows: list[tuple]
    total: int                 # filas (o grupos) que cumplen los filtros, antes del LIMIT
    bad: dict[str, int]        # columna -> celdas no numericas ignoradas por agregados numericos
    # columna -> celdas con valor que no se pudieron leer como fecha, entre las filas que cumplen los filtros
    # que NO son de fecha (las ilegibles nunca pasan un filtro de fecha: contarlas despues daria siempre 0).
    bad_dates: dict[str, int] = field(default_factory=dict)
    # columna de texto comparada -> (valores numericos, valores con dato) entre las filas filtradas
    text_numeric: dict[str, tuple[int, int]] = field(default_factory=dict)
    # columna -> fechas leidas con año de 2 digitos (mismas filas que bad_dates)
    two_digit: dict[str, int] = field(default_factory=dict)
    current_year: int | None = None


def _as_list(value, arg: str, max_items: int) -> list:
    if value is None or value == "":
        return []
    if isinstance(value, (str, int, float)):
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise QueryError(f"'{arg}' debe ser una lista")
    if len(value) > max_items:
        raise QueryError(f"'{arg}' admite máximo {max_items} elementos")
    return list(value)


def _parse_key(table: Table, expr) -> Key:
    if not isinstance(expr, str) or not expr.strip():
        raise QueryError("falta un nombre de columna")
    col = table.column(expr)
    if col is not None:
        return Key(col.name, col)
    m = _CALL_RE.match(expr)
    if m:
        bucket = _BUCKET_ALIASES.get(m.group(1).lower())
        if bucket is None:
            raise QueryError(f"'{one_line(expr)}' no válido; agrupaciones de fecha: day, week, month, year (col)")
        col = _resolve_column(table, m.group(2))
        return Key(f"{bucket}({col.name})", col, bucket)
    col = _resolve_column(table, expr)  # no existe: lanza QueryError con las columnas validas
    return Key(col.name, col)


def _parse_agg(table: Table, expr) -> Agg:
    if not isinstance(expr, str) or not expr.strip():
        raise QueryError("agregado vacío")
    text = expr.strip()
    if re.fullmatch(r"(?i)count\s*(\(\s*\*?\s*\))?", text):
        return Agg("count", "count", None)
    m = _CALL_RE.match(text)
    fn = _AGG_ALIASES.get(m.group(1).lower()) if m else None
    if fn is None:
        raise QueryError(
            f"agregado '{one_line(text)}' no válido; usa count, count(col), count_distinct(col), sum|avg|min|max(col)"
        )
    inner = m.group(2).strip()
    if fn == "count" and inner.lower().startswith("distinct "):
        fn, inner = "count_distinct", inner[9:].strip()
    if fn == "count" and inner in ("", "*"):
        return Agg("count", "count", None)
    col = _resolve_column(table, inner)
    if fn in ("sum", "avg"):
        mode = KIND_NUM
    elif fn in ("min", "max"):
        mode = col.kind if col.kind in (KIND_NUM, KIND_DATE) else KIND_TEXT
    else:
        mode = None
    return Agg(f"{fn}({col.name})", fn, col, mode)


def parse_number(value) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value)) if value == value and abs(value) != float("inf") else None
    if isinstance(value, str) and len(value) <= MAX_NUMBER_CHARS and _NUM_RE.fullmatch(value):
        try:
            return Decimal(value.strip(" "))
        except InvalidOperation:
            return None
    return None


def parse_date_range(value) -> tuple[date, date] | None:
    """'2026' / '2026-03' / '2026-03-15[...]' / '15/03/2026' -> [inicio, fin) del periodo; None si no es fecha."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    try:
        if m := re.fullmatch(r"(\d{4})", text, re.A):
            y = int(m.group(1))
            return date(y, 1, 1), date(y + 1, 1, 1)
        if m := re.fullmatch(r"(\d{4})[-/.](\d{1,2})", text, re.A):
            y, mo = int(m.group(1)), int(m.group(2))
            start = date(y, mo, 1)
            return start, date(y + (mo == 12), mo % 12 + 1, 1)
        m = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[T ].*)?$", text, re.A)
        if m:
            day = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        elif m := re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", text, re.A):
            day = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        else:
            return None
        return day, day + timedelta(days=1)
    except (ValueError, OverflowError):
        return None


def _parse_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE_WORDS:
        return True
    if text in _FALSE_WORDS:
        return False
    return None


def _check_value(value):
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return value
    if not isinstance(value, str):
        raise QueryError("los valores de filtros deben ser texto o número")
    if len(value) > MAX_VALUE_CHARS:
        raise QueryError(f"valor de filtro demasiado largo (máx. {MAX_VALUE_CHARS})")
    if "\x00" in value:
        raise QueryError("un valor de filtro no puede contener el carácter nulo")
    return value


def _parse_filter(table: Table, raw) -> Filter:
    if isinstance(raw, dict):
        col_name = raw.get("col", raw.get("column"))
        op = raw.get("op")
        vals = raw.get("values", raw.get("value", raw.get("val")))
        vals = [] if vals is None else (list(vals) if isinstance(vals, (list, tuple)) else [vals])
    elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
        col_name, op, vals = raw[0], raw[1], list(raw[2:])
    else:
        raise QueryError("cada filtro es [columna, operador, valor...]")
    op_text = str(op).strip().lower()
    op = _OP_ALIASES.get(op_text, op_text)
    if op not in OPS:
        raise QueryError(f"operador '{one_line(op_text)}' no válido; usa: {' '.join(OPS)}")
    col = _resolve_column(table, col_name)
    if len(vals) == 1 and isinstance(vals[0], (list, tuple)):
        vals = list(vals[0])
    vals = [_check_value(v) for v in vals]

    if op in ("null", "notnull"):
        return Filter(col, op, "k", ())
    if not vals:
        raise QueryError(f"falta el valor del filtro sobre '{one_line(col.name)}'")
    if op == "in":
        if len(vals) > MAX_IN_VALUES:
            raise QueryError(f"'in' admite máximo {MAX_IN_VALUES} valores")
    elif len(vals) > 1:
        raise QueryError(f"'{op}' lleva un solo valor; para varios usa 'in'")
    if op == "contains":
        return Filter(col, op, KIND_TEXT, (str(vals[0]),))

    mode = col.kind
    if mode == KIND_TEXT and op in (">", ">=", "<", "<="):
        # Columna declarada texto: si el valor es numero o fecha se compara como tal (catalogo mal tipado).
        if parse_number(vals[0]) is not None:
            mode = KIND_NUM
        elif parse_date_range(vals[0]) is not None:
            mode = KIND_DATE
    if mode == KIND_BOOL and op in (">", ">=", "<", "<="):
        raise QueryError(f"'{one_line(col.name)}' es sí/no; usa = o !=")

    if mode == KIND_NUM:
        parsed = [parse_number(v) for v in vals]
        if any(p is None for p in parsed):
            raise QueryError(f"'{one_line(col.name)}' es numérica; usa números simples (ej. 1500.5)")
    elif mode == KIND_DATE:
        parsed = [parse_date_range(v) for v in vals]
        if any(p is None for p in parsed):
            raise QueryError(f"'{one_line(col.name)}' es fecha; usa AAAA, AAAA-MM o AAAA-MM-DD")
    elif mode == KIND_BOOL:
        parsed = [_parse_bool(v) for v in vals]
        if any(p is None for p in parsed):
            raise QueryError(f"'{one_line(col.name)}' es sí/no; usa true o false")
    else:
        parsed = [str(v) for v in vals]
    return Filter(col, op, mode, tuple(parsed))


def _norm_label(text: str) -> str:
    return re.sub(r"\s+", "", text).casefold()


def build_plan(
    table: Table,
    *,
    select=None,
    filters=None,
    group_by=None,
    aggregates=None,
    order_by=None,
    limit=None,
    max_rows: int = 50,
) -> Plan:
    """Valida la especificacion del modelo contra el catalogo. Lanza QueryError con un mensaje corto."""
    filters_ = [_parse_filter(table, f) for f in _filter_list(filters)]
    keys = [_parse_key(table, k) for k in _as_list(group_by, "group_by", MAX_KEYS)]
    aggs = [_parse_agg(table, a) for a in _as_list(aggregates, "aggregates", MAX_AGGS)]
    selected = _as_list(select, "select", MAX_SELECT)

    if keys and not aggs:
        aggs = [Agg("count", "count", None)]
    if aggs:
        extra = [s for s in selected if _norm_label(str(s)) not in {_norm_label(k.label) for k in keys}]
        if extra:
            raise QueryError("con group_by/aggregates no se usa select; pon las columnas en group_by")
    else:
        keys = [_parse_key(table, s) for s in selected] or [
            Key(c.name, c) for c in table.columns[:_RAW_DEFAULT_COLUMNS]
        ]
        if not keys:
            raise QueryError(f"la tabla {one_line(table.name, 60)} no tiene columnas")

    order_items = []
    for item in _as_list(order_by, "order_by", MAX_ORDER):
        if not isinstance(item, str) or not item.strip():
            raise QueryError("order_by: usa el nombre de una salida, con '-' delante para desc")
        text, desc = item.strip(), False
        if text.startswith("-"):
            text, desc = text[1:].strip(), True
        elif re.search(r"(?i)\s+desc$", text):
            text, desc = re.sub(r"(?i)\s+desc$", "", text), True
        else:
            text = re.sub(r"(?i)\s+asc$", "", text)
        order_items.append((text, desc))

    labels = lambda: [k.label for k in keys] + [a.label for a in aggs]  # noqa: E731
    order: list[Order] = []
    for text, desc in order_items:
        index = next((i for i, lab in enumerate(labels()) if _norm_label(lab) == _norm_label(text)), None)
        if index is None and aggs and _norm_label(text) in ("count(*)", "count()"):
            index = next((i for i, lab in enumerate(labels()) if lab == "count"), None)
        if index is None:
            # Ordenar por algo que no esta en la salida: se agrega a la salida en vez de gastar otra ronda.
            if aggs:
                if len(aggs) >= MAX_AGGS:
                    raise QueryError(f"order_by '{one_line(text)}' debe estar en aggregates")
                aggs.append(_parse_agg(table, text))
            else:
                if len(keys) >= MAX_SELECT:
                    raise QueryError(f"order_by '{one_line(text)}' debe estar en select")
                keys.append(_parse_key(table, text))
            index = len(labels()) - 1
        order.append(Order(index, desc, _order_by_kind(keys, aggs, index)))

    if not order and aggs and keys:
        buckets = [i for i, k in enumerate(keys) if k.bucket]
        if buckets:
            order = [Order(i, False, "out") for i in buckets]
        else:
            order = [Order(len(keys), True, "out")]

    limit_ = _limit(limit, max_rows)
    return Plan(table.id, tuple(keys), tuple(aggs), tuple(filters_), tuple(order), limit_)


def _filter_list(filters) -> list:
    if filters is None or filters == "" or filters == []:
        return []
    if isinstance(filters, dict):
        filters = [filters]
    if not isinstance(filters, (list, tuple)):
        raise QueryError("'filters' debe ser una lista de [columna, operador, valor]")
    if filters and isinstance(filters[0], str):
        filters = [filters]  # un solo filtro sin anidar: ["total", ">", "100"]
    if len(filters) > MAX_FILTERS:
        raise QueryError(f"máximo {MAX_FILTERS} filtros")
    return list(filters)


def _order_by_kind(keys: list[Key], aggs: list[Agg], index: int) -> str:
    if index >= len(keys):
        agg = aggs[index - len(keys)]
        return "tn" if agg.fn in ("min", "max") and agg.col is not None and agg.col.kind == KIND_TEXT else "out"
    if keys[index].bucket:
        return "out"
    kind = keys[index].col.kind
    return kind if kind in (KIND_NUM, KIND_DATE) else "tn" if kind == KIND_TEXT else "out"


def _limit(value, max_rows: int) -> int:
    if value is None or value == "":
        return min(DEFAULT_LIMIT, max_rows)
    try:
        n = int(float(value))
    except (TypeError, ValueError, OverflowError):
        raise QueryError(f"'limit' debe ser un entero entre 1 y {max_rows}")
    return max(1, min(n, max_rows))


# ---------------------------------------------------------------------------
# Compilacion a SQL (parametrizado)
# ---------------------------------------------------------------------------

def _date_parts_sql(t: str) -> str:
    """Texto -> text[] con [anio, mes, dia] (ISO) o [.., .., .., dia, mes, anio] (D/M/AAAA); NULL si no es fecha."""
    return (
        f"CASE WHEN {t} ~ {_ISO_FAST_SQL} THEN ARRAY[substr(btrim({t}), 1, 4), substr(btrim({t}), 6, 2), "
        f"substr(btrim({t}), 9, 2)] ELSE regexp_match({t}, {_DATE_SQL}) END"
    )


def _date_sql(i: int) -> str:
    """Partes -> date o NULL, sin lanzar nunca: rango y dias del mes se validan antes de make_date (CASE
    evalua sus ramas en orden, y p es una subconsulta con barrera, no una expresion que se reordene)."""
    y, m, d = f"p.y{i}", f"p.m{i}", f"p.d{i}"
    return (
        f"CASE WHEN {y} IS NULL OR {y} < 1 OR {m} NOT BETWEEN 1 AND 12 OR {d} < 1 THEN NULL "
        f"WHEN {d} > extract(day FROM make_date({y}, {m}, 1) + interval '1 month - 1 day') THEN NULL "
        f"ELSE make_date({y}, {m}, {d}) END"
    )


_BUCKET_SQL = {
    "day": "to_char({d}, 'YYYY-MM-DD')",
    "week": "to_char(date_trunc('week', {d})::date, 'YYYY-MM-DD')",
    "month": "to_char({d}, 'YYYY-MM')",
    "year": "to_char({d}, 'YYYY')",
}
_CMP = {"=": "=", "!=": "<>", ">": ">", ">=": ">=", "<": "<", "<=": "<="}


def _like_pattern(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _ymd_sql(i: int, pivot: str, century: str) -> str:
    """text[] de _date_parts_sql -> anio, mes y dia enteros (NULL si la celda no tenia forma de fecha).
    pivot/century son parametros enlazados ($n::int) de la ventana de años de 2 digitos."""
    m = f"x.m{i}"
    return (
        f"COALESCE(COALESCE({m}[1], {m}[6], {m}[10], {m}[12])::int, CASE WHEN {m}[9] IS NULL THEN NULL "
        f"WHEN {m}[9]::int <= {pivot} THEN {century} + {m}[9]::int ELSE {century} - 100 + {m}[9]::int END) AS y{i}, "
        f"COALESCE({m}[2], {m}[5], {m}[8], {m}[11], {m}[13])::int AS m{i}, "
        f"COALESCE({m}[3], {m}[4], {m}[7], {m}[14], CASE WHEN {m}[10] IS NOT NULL THEN '1' END)::int AS d{i}"
    )


def _from_sql(plan: Plan, idx: dict, bind) -> tuple[str, list[str]]:
    """FROM + cadena de LATERAL que calcula UNA vez por fila el texto (k), numero (n), fecha (d) y si/no (b)
    de cada columna usada; mas las condiciones WHERE de tabla y filtros que no son de fecha."""
    need_num = {a.col for a in plan.aggs if a.mode == KIND_NUM} | {f.col for f in plan.filters if f.mode == KIND_NUM}
    need_num |= {plan.keys[o.index].col for o in plan.order if o.by == KIND_NUM}
    need_num |= set(plan.text_compared_columns())
    need_num |= {c for c in plan.normalized_columns() if c.kind == KIND_NUM}
    need_date = set(plan.date_columns()) | {c for c in plan.normalized_columns() if c.kind == KIND_DATE}
    need_bool = {f.col for f in plan.filters if f.mode == KIND_BOOL}

    typed = []
    for c, i in idx.items():
        typed.append(f"NULLIF(btrim(a.c{i}), '') AS k{i}")
        if c in need_num:
            typed.append(
                f"CASE WHEN length(a.c{i}) <= {MAX_NUMBER_CHARS} AND a.c{i} ~ {_NUM_SQL} "
                f"THEN btrim(a.c{i})::numeric END AS n{i}"
            )
        if c in need_date:
            typed.append(f"{_date_sql(i)} AS d{i}")
            typed.append(f"(x.m{i}[9] IS NOT NULL) AS yy{i}")   # año leido con 2 digitos
        if c in need_bool:
            typed.append(
                f"CASE WHEN lower(btrim(a.c{i})) IN {_sql_words(_TRUE_WORDS)} THEN true "
                f"WHEN lower(btrim(a.c{i})) IN {_sql_words(_FALSE_WORDS)} THEN false END AS b{i}"
            )

    # Cada valor de celda se calcula UNA vez por fila en una cadena de LATERAL con barrera (OFFSET 0): sin
    # ella Postgres "aplana" las subconsultas y repite la expresion en cada uso (medido: 9x mas lento).
    sql = "FROM org_data_rows r "
    if idx:
        raw = ", ".join(f"r.data->>({bind(c.name, 'text')}) AS c{i}" for c, i in idx.items())
        sql += f"CROSS JOIN LATERAL (SELECT {raw} OFFSET 0) a "
        dated = [i for c, i in idx.items() if c in need_date]
        if dated:
            parts = ", ".join(f"{_date_parts_sql(f'a.c{i}')} AS m{i}" for i in dated)
            pivot, century = two_digit_window(plan.current_year)
            pivot_sql, century_sql = bind(pivot, "int"), bind(century, "int")
            ymd = ", ".join(_ymd_sql(i, pivot_sql, century_sql) for i in dated)
            sql += f"CROSS JOIN LATERAL (SELECT {parts} OFFSET 0) x CROSS JOIN LATERAL (SELECT {ymd} OFFSET 0) p "
        sql += f"CROSS JOIN LATERAL (SELECT {', '.join(typed)} OFFSET 0) b "
    where = ["r.table_id = $1::uuid"] + [
        _filter_sql(f, idx[f.col], bind) for f in plan.filters if f.mode != KIND_DATE
    ]
    return sql, where


def _bad_date_sql(i: int) -> str:
    return f"count(*) FILTER (WHERE b.k{i} IS NOT NULL AND b.d{i} IS NULL)"


def _two_digit_sql(i: int) -> str:
    return f"count(*) FILTER (WHERE b.d{i} IS NOT NULL AND b.yy{i})"


def compile_plan(plan: Plan) -> tuple[str, list]:
    params: list = [plan.table_id]

    def bind(value, cast: str) -> str:
        params.append(value)
        return f"${len(params)}::{cast}"

    idx = {c: i for i, c in enumerate(plan.columns())}
    from_sql, where = _from_sql(plan, idx, bind)
    where += [_filter_sql(f, idx[f.col], bind) for f in plan.filters if f.mode == KIND_DATE]

    outputs = []
    group_by = []
    for j, k in enumerate(plan.keys):
        i = idx[k.col]
        if k.bucket:
            outputs.append(f'{_BUCKET_SQL[k.bucket].format(d=f"b.d{i}")} COLLATE "C"')
            group_by.append(str(j + 1))
        elif plan.aggregate:
            # Se agrupa con el mismo criterio que '=' / 'in' y se muestra una variante original estable
            # (si/no: la etiqueta canonica "sí"/"no").
            label = _norm_sql(k.col, i) if k.col.kind == KIND_BOOL else f"b.k{i}"
            outputs.append(f'min({label} COLLATE "C")')
            group_by.append(_norm_sql(k.col, i))
        else:
            outputs.append(f'b.k{i} COLLATE "C"')
    for a in plan.aggs:
        outputs.append(_agg_sql(a, idx))
    select = [f"{e} AS o{j}" for j, e in enumerate(outputs)] + ["count(*) OVER () AS total__"]
    bad_cols = sorted({idx[a.col] for a in plan.aggs if a.mode == KIND_NUM})
    select += [
        f"{_window(plan, f'count(*) FILTER (WHERE b.k{i} IS NOT NULL AND b.n{i} IS NULL)')} AS bad__{i}"
        for i in bad_cols
    ]
    if not any(f.mode == KIND_DATE for f in plan.filters):
        # Sin filtros de fecha, las filas del resultado son las mismas sobre las que se cuentan las ilegibles.
        select += [f"{_window(plan, _bad_date_sql(idx[c]))} AS bdate__{idx[c]}" for c in plan.date_columns()]
        select += [f"{_window(plan, _two_digit_sql(idx[c]))} AS yy2__{idx[c]}" for c in plan.date_columns()]
    text_cols = plan.text_compared_columns()
    for c in text_cols:
        i = idx[c]
        select += [f"{_window(plan, f'count(b.n{i})')} AS tnn__{i}", f"{_window(plan, f'count(b.k{i})')} AS tnk__{i}"]
    for j, a in enumerate(plan.aggs):
        if a.col in text_cols and a.fn in ("min", "max"):
            select.append(f"{a.fn}(b.n{idx[a.col]}) AS tnv__{j}")   # se usa si la columna resulta numerica

    order_sql = []
    for o in plan.order:
        direction = f"{'DESC' if o.desc else 'ASC'} NULLS LAST"
        if o.by == "out":
            order_sql.append(f"{o.index + 1} {direction}")
        elif o.by == "tn":
            # Numerico si la mayoria de los valores (de las filas filtradas) son numeros; si no, alfabetico.
            i = idx[plan.order_col(o)]
            majority = f"({_window(plan, f'count(b.n{i})')} * 2 > {_window(plan, f'count(b.k{i})')})"
            if o.index < len(plan.keys):
                number = f"min(b.n{i})" if plan.aggregate else f"b.n{i}"
            else:
                number = f"{plan.aggs[o.index - len(plan.keys)].fn}(b.n{i})"
            order_sql.append(f"CASE WHEN {majority} THEN {number} END {direction}")
            order_sql.append(f"CASE WHEN NOT {majority} THEN {outputs[o.index]} END {direction}")
        else:
            i = idx[plan.keys[o.index].col]
            col_expr = f"b.n{i}" if o.by == KIND_NUM else f"b.d{i}"
            expr = f"min({col_expr})" if plan.aggregate else col_expr
            order_sql.append(f"{expr} {direction}")
    if plan.aggregate:
        order_sql += [f"{j + 1} ASC NULLS LAST" for j in range(len(plan.keys))]
    else:
        order_sql += ["r.created_at ASC", "r.ctid ASC"]   # orden de carga (ver docstring del modulo)

    sql = f"SELECT {', '.join(select)} {from_sql}WHERE {' AND '.join(where)}"
    if plan.aggregate and plan.keys:
        sql += " GROUP BY " + ", ".join(group_by)
    if order_sql and (plan.keys or not plan.aggregate):
        sql += " ORDER BY " + ", ".join(order_sql)
    sql += f" LIMIT {bind(plan.limit, 'int')}"
    return sql, params


def _window(plan: Plan, expr: str) -> str:
    """Total de `expr` (un count FILTER) sobre todas las filas filtradas, repetido en cada fila del resultado."""
    return f"sum({expr}) OVER ()" if plan.aggregate else f"{expr} OVER ()"


def compile_date_check(plan: Plan) -> tuple[str, list] | None:
    """Con filtros de fecha: cuenta las fechas ilegibles en una consulta aparte, sobre las filas que cumplen
    los demas filtros (el filtro de fecha las descarta todas, y si no queda ninguna fila no habria donde leerlas)."""
    date_cols = plan.date_columns()
    if not date_cols or not any(f.mode == KIND_DATE for f in plan.filters):
        return None
    params: list = [plan.table_id]

    def bind(value, cast: str) -> str:
        params.append(value)
        return f"${len(params)}::{cast}"

    idx = {c: i for i, c in enumerate(plan.columns())}
    from_sql, where = _from_sql(plan, idx, bind)
    counts = ", ".join(
        f"{_bad_date_sql(idx[c])} AS bdate__{idx[c]}, {_two_digit_sql(idx[c])} AS yy2__{idx[c]}" for c in date_cols
    )
    return f"SELECT {counts} {from_sql}WHERE {' AND '.join(where)}", params


def _norm_sql(col: Column, i: int) -> str:
    """Valor con el que se agrupa y se cuentan distintos: el mismo criterio que usan los filtros.
    Texto/si-no: sin mayusculas ni espacios en los extremos. Numero: por valor (100 = 100.0 = " 100").
    Fecha: por dia (2026-03-15 = 15/03/2026). Lo que no se lee como numero/fecha cae al criterio de texto."""
    text = f"lower(b.k{i})"
    if col.kind == KIND_NUM:
        n = f"b.n{i}::text"
        canonical = f"CASE WHEN position('.' in {n}) > 0 THEN rtrim(rtrim({n}, '0'), '.') ELSE {n} END"
        return f"COALESCE({canonical}, {text})"
    if col.kind == KIND_DATE:
        return f"COALESCE(to_char(b.d{i}, 'YYYY-MM-DD'), {text})"
    if col.kind == KIND_BOOL:
        return (
            f"COALESCE(CASE WHEN {text} IN {_sql_words(_TRUE_WORDS)} THEN 'sí' "
            f"WHEN {text} IN {_sql_words(_FALSE_WORDS)} THEN 'no' END, {text})"
        )
    return text


def _sql_words(words) -> str:
    return "(" + ", ".join(f"'{w}'" for w in words) + ")"


def _agg_sql(a: Agg, idx: dict) -> str:
    if a.col is None:
        return "count(*)"
    i = idx[a.col]
    if a.fn == "count":
        return f"count(b.k{i})"
    if a.fn == "count_distinct":
        return f"count(DISTINCT {_norm_sql(a.col, i)})"
    if a.mode == KIND_NUM:
        return f"{a.fn}(b.n{i})"
    if a.mode == KIND_DATE:
        return f"{a.fn}(b.d{i})"
    return f'{a.fn}(b.k{i} COLLATE "C")'


def _filter_sql(f: Filter, i: int, bind) -> str:
    if f.op == "null":
        return f"b.k{i} IS NULL"
    if f.op == "notnull":
        return f"b.k{i} IS NOT NULL"
    if f.op == "contains":
        return f"b.k{i} ILIKE {bind(_like_pattern(f.values[0]), 'text')}"
    if f.mode == KIND_NUM:
        if f.op == "in":
            return f"b.n{i} = ANY({bind(list(f.values), 'numeric[]')})"
        return f"b.n{i} {_CMP[f.op]} {bind(f.values[0], 'numeric')}"
    if f.mode == KIND_BOOL:
        if f.op == "in":
            return f"b.b{i} = ANY({bind(list(f.values), 'boolean[]')})"
        return f"b.b{i} {_CMP[f.op]} {bind(f.values[0], 'boolean')}"
    if f.mode == KIND_DATE:
        # Cada valor es un periodo [inicio, fin): '2026-03' = todo marzo. Solo se enlaza el limite que se
        # usa (un parametro sin usar no tiene tipo y Postgres rechaza la consulta).
        d = f"b.d{i}"
        parts = []
        for start, end in f.values if f.op == "in" else f.values[:1]:
            if f.op in ("=", "in"):
                parts.append(f"({d} >= {bind(start, 'date')} AND {d} < {bind(end, 'date')})")
            elif f.op == "!=":
                parts.append(f"({d} < {bind(start, 'date')} OR {d} >= {bind(end, 'date')})")
            elif f.op in (">", "<="):
                parts.append(f"{d} {'>=' if f.op == '>' else '<'} {bind(end, 'date')}")
            else:
                parts.append(f"{d} {'>=' if f.op == '>=' else '<'} {bind(start, 'date')}")
        return "(" + " OR ".join(parts) + ")"
    if f.op == "in":
        return f"lower(b.k{i}) = ANY(ARRAY(SELECT lower(x) FROM unnest({bind(list(f.values), 'text[]')}) x))"
    if f.op in ("=", "!="):
        return f"lower(b.k{i}) {_CMP[f.op]} lower({bind(f.values[0], 'text')})"
    return f'b.k{i} COLLATE "C" {_CMP[f.op]} {bind(f.values[0], "text")}'


async def run_plans(pool, plans: list[Plan]) -> list[PlanResult]:
    """Ejecuta los planes en UNA transaccion de solo lectura con statement_timeout."""
    out = []
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            await conn.execute("SELECT set_config('statement_timeout', $1, true)", str(STATEMENT_TIMEOUT_MS))
            for plan in plans:
                sql, params = compile_plan(plan)
                records = await conn.fetch(sql, *params)
                n = len(plan.labels)
                rows = [tuple(r[f"o{j}"] for j in range(n)) for r in records]
                total = int(records[0]["total__"]) if records else 0
                idx = {c: i for i, c in enumerate(plan.columns())}
                bad, bad_dates = {}, {}
                if records:
                    for a in plan.aggs:
                        if a.mode == KIND_NUM:
                            bad[a.col.name] = int(records[0][f"bad__{idx[a.col]}"] or 0)
                check = compile_date_check(plan)
                counts = await conn.fetchrow(check[0], *check[1]) if check else (records[0] if records else None)
                two_digit = {}
                if counts is not None:
                    bad_dates = {c.name: int(counts[f"bdate__{idx[c]}"] or 0) for c in plan.date_columns()}
                    two_digit = {c.name: int(counts[f"yy2__{idx[c]}"] or 0) for c in plan.date_columns()}
                text_numeric = {}
                if records:
                    for c in plan.text_compared_columns():
                        i = idx[c]
                        text_numeric[c.name] = (int(records[0][f"tnn__{i}"] or 0), int(records[0][f"tnk__{i}"] or 0))
                    rows = _numeric_text_minmax(plan, rows, records, text_numeric, bad)
                out.append(PlanResult(rows, total, bad, bad_dates, text_numeric, two_digit, plan.current_year))
    return out


def mostly_numeric(counts: tuple[int, int]) -> bool:
    numeric, with_value = counts
    return numeric * 2 > with_value


def _numeric_text_minmax(plan: Plan, rows: list[tuple], records, text_numeric: dict, bad: dict) -> list[tuple]:
    """min/max de una columna de texto mayoritariamente numerica: el valor numerico (los demas, a la nota)."""
    keys = len(plan.keys)
    for j, a in enumerate(plan.aggs):
        counts = text_numeric.get(a.col.name) if a.col is not None and a.fn in ("min", "max") else None
        if counts and mostly_numeric(counts):
            rows = [row[: keys + j] + (rec[f"tnv__{j}"],) + row[keys + j + 1:] for row, rec in zip(rows, records)]
            bad[a.col.name] = counts[1] - counts[0]
    return rows


# ---------------------------------------------------------------------------
# Formato compacto para el modelo
# ---------------------------------------------------------------------------

def cell(value, limit: int = _CELL_CHARS) -> str:
    """Celda de una linea: sin control ni '|', acotada (datos de usuarios: nunca se confian)."""
    text = _CONTROL.sub(" ", str(value)[: limit * 2]).replace("|", "¦").strip()
    return text[:limit] + "…" if len(text) > limit else text


def fmt_number(value) -> str:
    try:
        d = value if isinstance(value, Decimal) else Decimal(repr(value) if isinstance(value, float) else value)
    except (InvalidOperation, ValueError, TypeError):
        return cell(value)
    if not d.is_finite():
        return "no calculable"
    if d == 0:
        return "0"
    if abs(d) >= Decimal("1e15"):
        return f"{d:.3e}"
    if abs(d) >= 1:
        text = format(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    return f"{d:.3g}"


def fmt_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, Decimal)):
        return fmt_number(value)
    if isinstance(value, date):
        return value.isoformat()
    return cell(value)


def format_rows(labels: list[str], rows: list[tuple], total: int, *, max_chars: int, unit: str = "filas",
                notes: list[str] = (), empty: str = "sin resultados", cell_chars: int = _CELL_CHARS) -> str:
    """Encabezado una sola vez + filas separadas por '|' + linea de truncado si aplica."""
    header = "|".join(cell(label) for label in labels)
    footer_reserve = 80 + sum(len(n) + 1 for n in notes)   # 80: la linea "(mostrando N de M ...)"
    budget = max(0, max_chars - len(header) - footer_reserve)
    kept, used = [], 0
    for row in rows:
        line = "|".join(cell(v, cell_chars) if isinstance(v, str) else fmt_value(v) for v in row)
        if used + len(line) + 1 > budget:
            break
        kept.append(line)
        used += len(line) + 1
    lines = [header] + kept
    if not rows:
        lines.append(empty)
    elif len(kept) < total:
        lines.append(f"(mostrando {len(kept)} de {total} {unit}; filtra, agrupa u ordena para ver otras)")
    lines += list(notes)
    return "\n".join(lines)[:max_chars]


def _count(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def result_notes(result: PlanResult, plan: Plan | None = None) -> list[str]:
    """Avisos que el modelo SIEMPRE recibe: sin ellos un 0 o una cifra parcial parecerian respuestas reales."""
    notes = [
        f"nota: {_count(n, 'valor no numérico ignorado', 'valores no numéricos ignorados')} en '{cell(col)}'"
        for col, n in result.bad.items() if n
    ]
    notes += [
        f"nota: {_count(n, 'valor de fecha ilegible', 'valores de fecha ilegibles')} en '{cell(col)}' "
        "(formato no reconocido; no entran en filtros ni grupos por fecha)"
        for col, n in result.bad_dates.items() if n
    ]
    notes += [
        f"nota: {_count(n, 'fecha', 'fechas')} con año de 2 dígitos en '{cell(col)}' "
        f"{'interpretada' if n == 1 else 'interpretadas'} con ventana {two_digit_rule(result.current_year)}"
        for col, n in result.two_digit.items() if n
    ]
    for col, counts in result.text_numeric.items():
        numeric, with_value = counts
        if mostly_numeric(counts):
            if with_value > numeric and _orders_text(plan, col):
                notes.append(
                    f"nota: '{cell(col)}' se ordenó como número; "
                    f"{_count(with_value - numeric, 'valor no numérico va', 'valores no numéricos van')} al final"
                )
        elif numeric:
            notes.append(
                f"nota: '{cell(col)}' es texto ({numeric} de {with_value} son números): orden y min/max alfabéticos"
            )
    return notes


def _orders_text(plan: Plan | None, col: str) -> bool:
    return plan is not None and any(o.by == "tn" and plan.order_col(o).name == col for o in plan.order)


def format_result(plan: Plan, result: PlanResult, *, max_chars: int) -> str:
    empty = "sin resultados con esos filtros (revisa valores con describe_table)" if plan.filters else "sin resultados"
    unit = "grupos" if plan.aggregate else "filas"
    return format_rows(plan.labels, result.rows, result.total, max_chars=max_chars, unit=unit,
                       notes=result_notes(result, plan), empty=empty)


# ---------------------------------------------------------------------------
# describe_table
# ---------------------------------------------------------------------------

DESCRIBE_MAX_COLUMNS = 12
_DESCRIBE_TOP_COLUMNS = 6
_DESCRIBE_TOP_VALUES = 4


async def describe(pool, table: Table, *, max_chars: int, max_columns: int = DESCRIBE_MAX_COLUMNS) -> str:
    """Perfil por columna con el mismo motor: con valor, distintos y rango (n/f) o valores frecuentes (t/b).

    Solo las primeras `max_columns` del catalogo: el costo crece con cada columna (leer numeros y fechas
    de cada fila, contar distintos); 40 columnas x 50k filas tardaban 5-8 s, al borde del statement_timeout."""
    cols = list(table.columns[:max_columns])
    if not cols:
        return f"{one_line(table.name, 60)}: sin columnas"
    aggs = [Agg("count", "count", None)]
    for c in cols:
        aggs += [Agg(f"count({c.name})", "count", c), Agg(f"count_distinct({c.name})", "count_distinct", c)]
        if c.kind in (KIND_NUM, KIND_DATE):
            aggs += [Agg(f"min({c.name})", "min", c, c.kind), Agg(f"max({c.name})", "max", c, c.kind)]
        if c.kind == KIND_NUM:
            aggs.append(Agg(f"avg({c.name})", "avg", c, KIND_NUM))
    stats_plan = Plan(table.id, (), tuple(aggs), (), (), 1)
    (stats,) = await run_plans(pool, [stats_plan])
    values = dict(zip(stats_plan.labels, stats.rows[0])) if stats.rows else {}

    top_cols = [
        c for c in cols
        if c.kind in (KIND_TEXT, KIND_BOOL) and 0 < (values.get(f"count_distinct({c.name})") or 0)
        < (values.get(f"count({c.name})") or 0)
    ][:_DESCRIBE_TOP_COLUMNS]
    top_plans = [
        Plan(table.id, (Key(c.name, c),), (Agg("count", "count", None),), (), (Order(1, True, "out"),),
             _DESCRIBE_TOP_VALUES)
        for c in top_cols
    ]
    tops = dict(zip(top_cols, await run_plans(pool, top_plans))) if top_plans else {}

    rows = []
    for c in cols:
        summary = ""
        unreadable = stats.bad_dates.get(c.name) if c.kind == KIND_DATE else 0
        if c.kind in (KIND_NUM, KIND_DATE) and values.get(f"min({c.name})") is not None:
            lo, hi = fmt_value(values[f"min({c.name})"]), fmt_value(values[f"max({c.name})"])
            summary = f"{lo} a {hi}"
            if c.kind == KIND_NUM:
                summary += f", prom {fmt_value(values[f'avg({c.name})'])}"
                bad = stats.bad.get(c.name)
                if bad:
                    summary += f"; {_count(bad, 'no numérico', 'no numéricos')}"
            if unreadable:
                summary += f"; {_count(unreadable, 'ilegible', 'ilegibles')}"
            two_digit = stats.two_digit.get(c.name) if c.kind == KIND_DATE else 0
            if two_digit:
                summary += f"; {_count(two_digit, 'fecha', 'fechas')} con año de 2 dígitos"
        elif unreadable:
            summary = f"{_count(unreadable, 'fecha ilegible', 'fechas ilegibles')} (formato no reconocido)"
        elif c in tops:
            summary = ", ".join(f"{cell(v, 30)} ({fmt_value(n)})" for v, n in tops[c].rows)
            if tops[c].total > len(tops[c].rows):
                summary += " …"
        rows.append((c.name, c.kind, values.get(f"count({c.name})"), values.get(f"count_distinct({c.name})"), summary))
    head = f"{one_line(table.name, 60)}: {fmt_value(values.get('count', table.rows))} filas; tipos t texto, n número, f fecha, b sí/no"
    extra = []
    if len(table.columns) > len(cols):
        extra.append(f"estadísticas de {len(cols)} de {len(table.columns)} columnas; usa query_table para el resto")
    if any(stats.two_digit.values()):
        extra.append(f"nota: años de 2 dígitos leídos con ventana {two_digit_rule(stats.current_year)}")
    body = format_rows(["columna", "tipo", "con_valor", "distintos", "resumen"], rows, len(rows),
                       max_chars=max_chars - len(head) - 1, unit="columnas", notes=extra, cell_chars=110)
    return f"{head}\n{body}"
