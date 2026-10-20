"""Filtros GLOBALES de lectura de un tablero (periodo + categorias) — PI0320251.

El duenio "juega" con el tablero: elige un periodo ("ultimos 30 dias", "este mes", un rango) y una o varias
categorias (producto, cliente, forma de pago...) y TODOS los graficos y cifras se recalculan con el motor.
Nada de esto se guarda ni modifica el tablero: los filtros se COMBINAN con los propios de cada widget solo al
calcular (`apply`).

Forma que recibe la API (todo opcional):
  {"period": {"preset": "last_30"} | {"from": "2026-09-01", "to": "2026-09-30"},
   "where":  [{"key": "producto", "values": ["Cemento Argos 50kg", ...]}, ...]}

Reglas de seguridad y tolerancia:
- Fechas estrictas AAAA-MM-DD reales; el periodo se interpreta en hora de Colombia (UTC-5, sin horario de verano).
- `key` de una categoria = su ROL ("producto", "cliente"...) o, sin rol, el nombre canonico de la columna. Se
  valida contra el catalogo de la organizacion: una clave que no existe en NINGUNA hoja del tablero es un error
  (422); una que existe en otras hojas pero no en la de un widget NO rompe a ese widget: se calcula sin ese
  filtro y se le avisa con una nota discreta.
- Nunca SQL del cliente: se traducen a filtros del motor (parametrizados y validados contra el catalogo).
"""

import re
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone

from app.services import data_labels as labels
from app.services import data_query_engine as engine

PRESETS = {
    "last_7": "Últimos 7 días", "last_30": "Últimos 30 días", "last_90": "Últimos 90 días",
    "this_month": "Este mes", "last_month": "Mes anterior", "this_year": "Este año", "all": "Todo",
}
MAX_WHERE = 3                    # categorias activas a la vez
MAX_VALUES = 25                  # valores elegidos por categoria
MAX_OPTION_VALUES = 25           # valores mas frecuentes que se ofrecen por categoria
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}", re.A)
_KEY = re.compile(r"[\w .\-/()%$#°]{1,60}", re.U)
_MIN_YEAR, _MAX_YEAR = 1900, 2100
_COLOMBIA = timezone(timedelta(hours=-5))
# Hojas por rol equivalentes: la misma categoria en hojas de distinto tipo.
_ROLE_ALIAS = {"producto_nombre": "producto"}
_DATE_ROLES = ("fecha", "fecha_emision", "fecha_vencimiento")


class FilterError(ValueError):
    """Filtro invalido. Mensaje corto y en lenguaje llano: se devuelve tal cual al usuario (422)."""


def today_co() -> date:
    """Hoy en Colombia (los tests lo reemplazan para fijar la fecha)."""
    return datetime.now(_COLOMBIA).date()


# ---------------------------------------------------------------------------
# Forma validada
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GlobalFilters:
    date_from: date | None = None
    date_to: date | None = None
    preset: str | None = None
    where: tuple[tuple[str, tuple[str, ...]], ...] = ()

    @property
    def has_period(self) -> bool:
        return self.date_from is not None or self.date_to is not None

    @property
    def active(self) -> bool:
        return self.has_period or bool(self.where)

    def as_dict(self) -> dict:
        out: dict = {}
        if self.has_period:
            out["period"] = {
                "preset": self.preset,
                "label": PRESETS.get(self.preset or "", None),
                "from": self.date_from.isoformat() if self.date_from else None,
                "to": self.date_to.isoformat() if self.date_to else None,
            }
        if self.where:
            out["where"] = [{"key": k, "values": list(v)} for k, v in self.where]
        return out


NO_FILTERS = GlobalFilters()


def _iso_date(value, name: str) -> date:
    if not isinstance(value, str) or not _ISO.fullmatch(value.strip()):
        raise FilterError(f"La fecha «{engine.one_line(str(value), 20)}» no es válida; usa el formato AAAA-MM-DD.")
    try:
        d = date.fromisoformat(value.strip())
    except ValueError:
        raise FilterError(f"La fecha «{engine.one_line(str(value), 20)}» no existe en el calendario.")
    if not _MIN_YEAR <= d.year <= _MAX_YEAR:
        raise FilterError(f"La fecha «{value}» está fuera de rango (años {_MIN_YEAR} a {_MAX_YEAR}).")
    return d


def resolve_preset(preset: str, today: date) -> tuple[date | None, date | None]:
    """Atajo -> (desde, hasta) inclusivos; (None, None) para 'todo'."""
    if preset == "all":
        return None, None
    if preset in ("last_7", "last_30", "last_90"):
        days = int(preset.split("_")[1])
        return today - timedelta(days=days - 1), today
    if preset == "this_month":
        first = today.replace(day=1)
        return first, _month_end(first)
    if preset == "last_month":
        last = today.replace(day=1) - timedelta(days=1)
        return last.replace(day=1), last
    if preset == "this_year":
        return date(today.year, 1, 1), date(today.year, 12, 31)
    raise FilterError("Ese atajo de período no existe.")


def _month_end(first: date) -> date:
    nxt = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def parse_filters(raw, today: date | None = None) -> GlobalFilters:
    """Valida lo que manda el cliente. Lanza FilterError con un mensaje en lenguaje llano."""
    if raw is None or raw == {} or raw == "":
        return NO_FILTERS
    if not isinstance(raw, dict):
        raise FilterError("Los filtros deben ser un objeto con period y where.")
    unknown = [k for k in raw if k not in ("period", "where")]
    if unknown:
        raise FilterError(f"Filtro desconocido «{engine.one_line(str(unknown[0]), 30)}».")
    today = today or today_co()

    lo = hi = None
    preset = None
    period = raw.get("period")
    if period not in (None, {}):
        if not isinstance(period, dict) or any(k not in ("preset", "from", "to") for k in period):
            raise FilterError("El período debe traer un atajo o un rango (from, to).")
        if period.get("preset") not in (None, ""):
            if period.get("from") or period.get("to"):
                raise FilterError("Elige un atajo de período o un rango de fechas, no los dos.")
            preset = period["preset"]
            if not isinstance(preset, str) or preset not in PRESETS:
                raise FilterError("Ese atajo de período no existe.")
            lo, hi = resolve_preset(preset, today)
        else:
            lo = _iso_date(period["from"], "from") if period.get("from") else None
            hi = _iso_date(period["to"], "to") if period.get("to") else None
            if lo and hi and lo > hi:
                raise FilterError("La fecha inicial es posterior a la final.")

    where = raw.get("where")
    out_where: list[tuple[str, tuple[str, ...]]] = []
    if where not in (None, [], {}):
        if not isinstance(where, list):
            raise FilterError("where debe ser una lista de categorías.")
        if len(where) > MAX_WHERE:
            raise FilterError(f"Puedes filtrar por máximo {MAX_WHERE} categorías a la vez.")
        seen = set()
        for item in where:
            if not isinstance(item, dict) or set(item) - {"key", "values"}:
                raise FilterError("Cada filtro de categoría trae key y values.")
            key = item.get("key")
            if not isinstance(key, str) or not _KEY.fullmatch(key.strip()):
                raise FilterError("El nombre de la categoría a filtrar no es válido.")
            key = _norm_key(key)
            if key in seen:
                raise FilterError(f"La categoría «{engine.one_line(key, 30)}» está repetida.")
            seen.add(key)
            values = item.get("values")
            if not isinstance(values, list) or not values:
                raise FilterError("Elige al menos un valor para cada categoría.")
            if len(values) > MAX_VALUES:
                raise FilterError(f"Puedes elegir máximo {MAX_VALUES} valores por categoría.")
            clean = []
            for v in values:
                if isinstance(v, bool) or not isinstance(v, (str, int, float)):
                    raise FilterError("Los valores de un filtro son texto o número.")
                v = str(v).strip()
                if not v or len(v) > engine.MAX_VALUE_CHARS or "\x00" in v:
                    raise FilterError("Un valor de filtro es demasiado largo o no es válido.")
                if v not in clean:
                    clean.append(v)
            out_where.append((key, tuple(clean)))
    return GlobalFilters(lo, hi, preset, tuple(out_where))


def _norm_key(key: str) -> str:
    key = key.strip()
    folded = engine.fold_name(key)
    return _ROLE_ALIAS.get(folded, folded)


# ---------------------------------------------------------------------------
# Dimensiones y columna de fecha de una hoja
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Dimension:
    key: str                 # clave estable del filtro: rol ("producto") o nombre canonico plegado
    label: str               # "Producto", "Forma de pago"
    column: engine.Column
    rank: int                # menor = mas util para desglosar / filtrar


def dimension_key(col: engine.Column) -> str:
    if col.role and col.role in labels.CATEGORY_ROLES:
        return _ROLE_ALIAS.get(col.role, col.role)
    return engine.fold_name(col.name)


def _rank(col: engine.Column) -> int:
    from app.services import chart_specs as cs

    if col.role in labels.CATEGORY_ROLES:
        return labels.CATEGORY_ROLES.index(col.role)
    tokens = cs._tokens(col.name) + (cs._tokens(col.label) if col.label else [])
    for i, word in enumerate(labels.NAME_ORDER):
        if word in tokens:
            return 20 + i
    return 100


def table_dimensions(table: engine.Table) -> list[Dimension]:
    """Columnas categoricas utiles para filtrar o desglosar: texto o si/no, sin identificadores ni texto libre
    (salvo que su ROL confirmado diga que son una categoria del negocio)."""
    from app.services import chart_specs as cs

    out: dict[str, Dimension] = {}
    for col in table.columns:
        if col.kind not in (engine.KIND_TEXT, engine.KIND_BOOL):
            continue
        if col.role:
            if col.role not in labels.CATEGORY_ROLES:
                continue              # codigo, nombre, contacto, telefono...: identifican, no agrupan
        elif cs.category_score(col.name) <= 0 or cs.is_id_name(col.name) or (col.label and cs.is_id_name(col.label)):
            continue
        key = dimension_key(col)
        if key not in out:
            out[key] = Dimension(key, labels.dim_label(col), col, _rank(col))
    return sorted(out.values(), key=lambda d: (d.rank, list(table.columns).index(d.column)))


def date_column(table: engine.Table, key: engine.Key | None = None) -> engine.Column | None:
    """La fecha con la que se filtra el periodo de un widget: la del propio eje X si es una fecha agrupada; si no,
    la fecha del negocio (rol), y si no hay roles, la primera columna de fecha. None si la hoja no tiene fechas."""
    if key is not None and key.bucket:
        return key.col
    dates = [c for c in table.columns if c.kind == engine.KIND_DATE]
    for role in _DATE_ROLES:
        hit = next((c for c in dates if c.role == role), None)
        if hit:
            return hit
    return dates[0] if dates else None


# ---------------------------------------------------------------------------
# Aplicar a un widget
# ---------------------------------------------------------------------------

def valid_keys(tables) -> set[str]:
    return {d.key for t in tables for d in table_dimensions(t)}


def check_keys(gf: GlobalFilters, tables) -> None:
    """Toda categoria del filtro debe existir en alguna hoja del tablero (validacion contra el catalogo)."""
    keys = valid_keys(tables)
    for key, _ in gf.where:
        if key not in keys:
            raise FilterError(
                f"No puedo filtrar por «{engine.one_line(key, 30)}» en este tablero; las categorías disponibles son: "
                + (", ".join(sorted(keys)) or "ninguna") + "."
            )


NOTE_NO_DATE = "no_date"
NOTE_NO_DIMENSION = "no_dimension"


def apply(spec, table: engine.Table, gf: GlobalFilters) -> tuple:
    """(spec con los filtros globales sumados, notas). No toca el original. Una hoja sin la fecha o sin la
    categoria pedida se calcula SIN ese filtro y la nota lo dice."""
    if not gf.active:
        return spec, []
    key = engine._parse_key(table, spec.x) if spec.x else None
    extra: list[tuple] = []
    notes: list[dict] = []
    if gf.has_period:
        col = date_column(table, key)
        if col is None:
            notes.append({"code": NOTE_NO_DATE, "message": "Este gráfico no tiene fecha: se muestra completo, sin el filtro de período."})
        else:
            if gf.date_from:
                extra.append((col.name, ">=", gf.date_from.isoformat()))
            if gf.date_to:
                extra.append((col.name, "<=", gf.date_to.isoformat()))
    dims = {d.key: d for d in table_dimensions(table)}
    for dim_key, values in gf.where:
        dim = dims.get(dim_key)
        if dim is None:
            label = labels.capitalize(dim_key.replace("_", " "))
            notes.append({"code": NOTE_NO_DIMENSION, "message": f"Este gráfico no tiene «{label}»: se muestra sin ese filtro."})
            continue
        extra.append((dim.column.name, "=" if len(values) == 1 else "in", *values))
    if not extra:
        return spec, notes
    return replace(spec, filters=tuple(spec.filters) + tuple(extra)), notes
