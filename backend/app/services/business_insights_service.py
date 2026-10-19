"""Hallazgos de negocio ("Esta semana en tu negocio") — PI0320251.

Calcula, de forma EXACTA y determinista (sin IA, sin Gemini, sin red), hallazgos de plata sobre los datos que la
organizacion ya subio. Todo es de solo lectura y sale de las tablas virtuales de la org (org_data_tables /
org_data_rows) a traves del motor declarativo del chat (data_query_engine): mismas reglas de numeros y fechas
tolerantes, mismo aislamiento por organizacion (el pool es el de la org del JWT), misma transaccion de SOLO
LECTURA con statement_timeout.

1. ROLES POR COLUMNAS (no por nombre de tabla). El duenio sube Excel con nombres arbitrarios: a cada tabla se le
   asigna un rol segun las columnas que se reconocen (sinonimos en español, sin acentos/mayusculas/guiones, con
   puntaje). `productos` necesita nombre y (costo o existencias); `ventas` necesita fecha, producto, cantidad y
   (total o precio unitario). Si hay varias candidatas para un rol se usa la de mayor puntaje (luego la de mas filas)
   y se avisa en `how.notes`; NUNCA se mezclan tablas dudosas. Un rol que falta deja la receta en `missing`.

2. CALCULO sobre TODAS las filas (sin muestras ni LIMIT: el tope de grupos es de seguridad y, si se superara, la
   receta se declara no calculable en vez de dar una cifra parcial). Para multiplicar fila a fila (existencias x
   costo, cantidad x precio) se agrupa por los valores de cada fila ("agregados" que el motor ya valida) y la
   multiplicacion se hace en Python con Decimal; las filas identicas se cuentan una vez con su `count`. El cruce
   productos <-> ventas se hace con una clave normalizada (minusculas, sin acentos, espacios colapsados); lo que no
   cruza se informa SIEMPRE.

3. DEFINICIONES (tambien en `how.steps` con palabras simples). Periodo = de la primera a la ultima fecha de ventas
   legible, AMBAS incluidas (dias = ultima - primera + 1); mes = 30 dias (DAYS_PER_MONTH).
   - Precio de venta real de cada venta = precio unitario de esa fila; si falta, total / cantidad. Una venta cuenta
     solo con fecha legible, cantidad > 0 y precio >= 0.
   - capital_inventario: mercancia a costo = suma(existencias x costo); costo de lo vendido = suma(cantidad
     vendida x costo del producto); meses de inventario = mercancia / (costo vendido / (dias del periodo / 30)).
     Severidad: attention si meses > 6, important si > 12.
   - productos_estrella: utilidad de un producto = suma(cantidad x (precio real - costo)) = ventas - cantidad x costo;
     top 3 por utilidad (solo las positivas) y su % de la utilidad total (la de TODOS los productos con costo).
   - reposicion: ritmo diario = unidades vendidas / dias del periodo; dias restantes = existencias / ritmo; se
     listan hasta 5 productos con < 15 dias (ritmo 0 excluido). Severidad important si alguno tiene < 7 dias.
   - clientes_concentracion: % de lo vendido (todas las ventas validas) que suman los 3 mejores clientes y el
     primero. attention si el primero > 30 % o los 3 mejores > 50 %; info en otro caso. Ventas sin cliente o a un
     "cliente" generico (mostrador, contado...) cuentan en el total pero no como cliente.
   - sin_movimiento: productos con existencias > 0 y sin ninguna venta en los ultimos 90 dias del periodo (relativo
     a la ultima fecha de ventas, NO a hoy; ventana = los 90 dias que terminan en esa fecha, ambos extremos
     incluidos; "venta" = fila con fecha legible y cantidad > 0, aunque su precio no se lea); plata parada =
     suma(existencias x costo) de ellos. Si el periodo total dura menos de 90 dias se usa el periodo completo y se
     dice en `notes`. attention si la plata parada es >= 20 % de la mercancia.
   - margen_bajo: productos vendidos con margen (utilidad / ventas) < 10 % o con alguna venta por debajo del costo
     (precio real < costo); hasta 5. Severidad important si alguno pierde plata (venta bajo el costo).

4. ROBUSTEZ: tablas vacias, numeros como texto, nulos, ceros (sin dividir por cero), productos repetidos (se suman
   y se avisa), existencias negativas (cuentan 0 y se avisa), fechas ilegibles o fuera de rango (se excluyen y se
   cuentan), ventas de productos inexistentes... nunca lanzan 500: la receta queda en `missing` o con `notes`.
   Solo un fallo de infraestructura (BD caida, tiempo agotado) levanta InsightsUnavailable (el router responde 503).

NOTA sobre "1.200": el motor lee un texto numerico como decimal con punto ("1.200" = 1,2), igual que el chat. Una
celda guardada con separador de miles es-CO se lee distinto de lo que quiso decir el duenio; aqui se avisa cuando
un valor de una columna de dinero/cantidad tiene la forma "1.200" (ver THOUSANDS_LOOKALIKE).
"""

import asyncio
import logging
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from typing import Any

from app.database import get_org_pool
from app.services import data_query_engine as engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes (umbrales: faciles de ajustar)
# ---------------------------------------------------------------------------

RECIPE_PACK = "ferreteria"
DAYS_PER_MONTH = 30                    # un "mes" para meses de inventario
SHORT_PERIOD_DAYS = 60                 # periodo de ventas menor a esto: "periodo corto"
INVENTORY_ATTENTION_MONTHS = Decimal(6)    # meses de inventario > 6  -> attention
INVENTORY_IMPORTANT_MONTHS = Decimal(12)   # meses de inventario > 12 -> important
STARS_TOP_N = 3                        # productos estrella
RESTOCK_DAYS = Decimal(15)             # reposicion: se lista si quedan < 15 dias
RESTOCK_URGENT_DAYS = Decimal(7)       # reposicion: important si alguno tiene < 7 dias
RESTOCK_MAX_LISTED = 5
CLIENT_TOP_N = 3                       # clientes: los N mejores
CLIENT_FIRST_ATTENTION = Decimal("0.30")   # el primero > 30 % de lo vendido -> attention
CLIENT_TOP_ATTENTION = Decimal("0.50")     # los 3 mejores > 50 % -> attention
STALE_WINDOW_DAYS = 90                 # sin_movimiento: ventana de "sin ventas"
PARKED_ATTENTION_SHARE = Decimal("0.20")   # sin_movimiento: attention si la plata parada >= 20 % de la mercancia
LOW_MARGIN = Decimal("0.10")           # margen_bajo: margen < 10 %
LOW_MARGIN_MAX_LISTED = 5
STALE_DATA_DAYS = 60                   # ultima venta mas vieja que esto (frente a hoy): se avisa
MIN_SALE_DATE = date(2000, 1, 1)       # fechas anteriores se consideran error de digitacion
FUTURE_SALE_DAYS = 366                 # fechas mas alla de hoy + 366 dias se consideran error de digitacion
MAX_GROUPS = 200_000                   # tope de seguridad de grupos por consulta (si se supera: no se calcula)
MAX_DAYS_ROWS = 40_000                 # filas de la agrupacion por dia (>100 años de dias)
TOTAL_TIMEOUT_SECONDS = 25.0
MAX_NAME_CHARS = 40                    # nombres de usuario dentro de las frases
GENERIC_CLIENTS = frozenset({
    "mostrador", "contado", "consumidor final", "cliente general", "cliente generico", "cliente mostrador",
    "varios", "cliente varios", "publico general", "venta mostrador", "sin cliente", "n/a", "na", "no aplica",
    "anonimo", "cliente", "ocasional", "cliente ocasional", "cliente de contado", "venta de contado",
})
# "1.200": numero con puntos de miles que el motor lee como decimal (ver docstring del modulo).
THOUSANDS_LOOKALIKE = re.compile(r"^\s*[0-9]{1,3}(\.[0-9]{3})+\s*$")

SEVERITY_RANK = {"info": 0, "attention": 1, "important": 2}
# Orden de items: severidad (important > attention > info); dentro de cada severidad primero los accionables (con
# `action`) y al final los "todo bien" (sin `action`); y a igual severidad y accion, por impacto: primero la plata
# inmovilizada o en riesgo (mercancia, faltantes, margen, plata parada), luego la dependencia de clientes y al final
# la oportunidad (productos estrella). Es estable y determinista.
IMPACT_ORDER = ("capital_inventario", "reposicion", "margen_bajo", "sin_movimiento",
                "clientes_concentracion", "productos_estrella")

_BASE_TZ = timezone(timedelta(hours=-5))   # Colombia no tiene horario de verano: -05:00 fijo, sin tzdata
_MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
           "noviembre", "diciembre")
_WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


class InsightsUnavailable(Exception):
    """Fallo de infraestructura (BD, tiempo agotado). El router responde 503 con el mensaje."""


# ---------------------------------------------------------------------------
# Formato es-CO (frases con plantillas, sin IA)
# ---------------------------------------------------------------------------

def _dec(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _group_thousands(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def fmt_int(value) -> str:
    """Entero con puntos de miles: 1.200."""
    d = _dec(value).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return ("-" if d < 0 else "") + _group_thousands(abs(int(d)))


def _one_decimal(d: Decimal) -> str:
    """12,3 (coma decimal, miles con punto); sin ',0' final: 10 en vez de 10,0."""
    whole, _dot, frac = f"{d.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):f}".partition(".")
    sign = "-" if whole.startswith("-") else ""
    text = sign + _group_thousands(int(whole.lstrip("-") or 0))
    return text if frac in ("", "0") else f"{text},{frac}"


def fmt_money(value) -> str:
    """Pesos colombianos para leer rapido: $360.000, $47,6 M, $1,2 mil millones, $2,5 billones."""
    d = _dec(value)
    sign = "-" if d < 0 else ""
    a = abs(d)
    tiers = ((Decimal(10) ** 12, "billones"), (Decimal(10) ** 9, "mil millones"), (Decimal(10) ** 6, "M"))
    for i, (unit, label) in enumerate(tiers):
        if a >= unit:
            scaled = (a / unit).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            if scaled >= 1000 and i > 0:        # 999,96 M se redondea a 1.000 M: pasa al nivel de arriba
                unit, label = tiers[i - 1]
                scaled = (a / unit).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            if label == "billones" and scaled == 1:
                label = "billón"
            return f"{sign}${_one_decimal(scaled)} {label}"
    pesos = a.quantize(Decimal(1), rounding=ROUND_HALF_UP)
    if pesos >= 1_000_000:
        return f"{sign}$1 M"
    return f"{sign}${_group_thousands(int(pesos))}"


def fmt_percent(ratio) -> str:
    """Razon (0,36) -> '36 %'; por debajo de 10 % con un decimal: '4,5 %'."""
    p = _dec(ratio) * 100
    if abs(p) >= 10:
        return f"{fmt_int(p)} %"
    return f"{_one_decimal(p)} %"


def fmt_date(d: date, with_year: bool = True) -> str:
    text = f"{d.day} de {_MONTHS[d.month - 1]}"
    return f"{text} de {d.year}" if with_year else text


def fmt_range(start: date, end: date) -> str:
    if start == end:
        return f"el {fmt_date(start)}"
    if start.year == end.year:
        return f"entre el {fmt_date(start, False)} y el {fmt_date(end)}"
    return f"entre el {fmt_date(start)} y el {fmt_date(end)}"


def fmt_days(days: int) -> str:
    return f"{days} día" if days == 1 else f"{days} días"


def join_es(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " y " + items[-1]


def plural(n: int, singular: str, plural_: str) -> str:
    return f"{fmt_int(n)} {singular if n == 1 else plural_}"


def short_name(name: str, limit: int = MAX_NAME_CHARS) -> str:
    """Nombre escrito por el usuario dentro de una frase: una linea, acotado."""
    return engine.one_line(name, limit)


def months_phrase(months: Decimal) -> str:
    if months < 1:
        return "menos de un mes"
    if months < 12:
        n = int(months.quantize(Decimal(1), rounding=ROUND_HALF_UP))
        return "un mes" if n == 1 else f"unos {n} meses"
    if months < 24:
        return "más de un año"
    return f"más de {int(months // 12)} años"


# ---------------------------------------------------------------------------
# Normalizacion
# ---------------------------------------------------------------------------

def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def fold(text) -> str:
    """Encabezado -> solo [a-z0-9] separados por un espacio (sin acentos, mayusculas, guiones ni signos)."""
    return re.sub(r"[^0-9a-z]+", " ", strip_accents(str(text)).casefold()).strip()


@lru_cache(maxsize=200_000)
def product_key(name) -> str:
    """Clave de cruce entre hojas: minusculas, sin acentos, sin espacios en los extremos y espacios colapsados.
    (Con cache: los mismos nombres se repiten decenas de miles de veces en las ventas.)"""
    return re.sub(r"\s+", " ", strip_accents(str(name)).casefold()).strip()


_STOPWORDS = frozenset({"de", "del", "la", "el", "los", "las", "en", "por", "y", "cop", "un", "una", "al"})


def _stem(token: str) -> str:
    return token[:-1] if len(token) > 3 and token.endswith("s") else token


# Abreviaturas comunes de planillas (se aplican igual a encabezados y sinonimos)
_ABBREVIATIONS = {"vr": "valor", "vlr": "valor", "unit": "unitario", "cant": "cantidad", "und": "unidad",
                  "uds": "unidades", "prod": "producto", "desc": "descripcion", "fec": "fecha", "qty": "cantidad",
                  "exist": "existencia", "cli": "cliente"}


def _tokens(text) -> list[str]:
    words = [_ABBREVIATIONS.get(t, t) for t in fold(text).split()]
    return [_stem(t) for t in words if t not in _STOPWORDS]


# ---------------------------------------------------------------------------
# Deteccion de roles por columnas
# ---------------------------------------------------------------------------
# Sinonimos (frase, peso): 1.0 es el nombre "de manual"; 0.8 alias comun; 0.5 debil (solo cuenta si no hay nada mejor).
# Una columna solo sirve a UN campo (gana el de mayor puntaje).

_PRODUCT_FIELDS: dict[str, tuple[tuple[str, float], ...]] = {
    "nombre": (("nombre", 1.0), ("producto", 1.0), ("nombre producto", 1.0), ("articulo", 0.8), ("item", 0.8),
               ("descripcion", 0.8), ("referencia", 0.8), ("nombre articulo", 0.8), ("detalle", 0.5),
               ("mercancia", 0.5), ("material", 0.5)),
    "costo": (("costo", 1.0), ("precio compra", 1.0), ("costo unitario", 1.0), ("costo promedio", 1.0),
              ("costo compra", 1.0), ("valor compra", 0.8), ("precio costo", 0.8), ("precio proveedor", 0.8),
              ("costo producto", 0.8), ("compra", 0.5), ("vr compra", 0.8), ("p compra", 0.8)),
    "precio_venta": (("precio venta", 1.0), ("pvp", 1.0), ("precio publico", 1.0), ("precio lista", 0.8),
                     ("valor venta", 0.8), ("precio", 0.8), ("vr venta", 0.8)),
    "stock": (("stock", 1.0), ("existencia", 1.0), ("existencias", 1.0), ("inventario", 0.8),
              ("cantidad disponible", 1.0), ("disponible", 0.8), ("saldo", 0.8), ("unidades disponibles", 1.0),
              ("stock actual", 1.0), ("existencia actual", 1.0), ("cantidad stock", 1.0),
              ("cantidad inventario", 1.0), ("en bodega", 0.8), ("bodega", 0.5), ("cantidad", 0.5),
              ("unidades", 0.5), ("cant", 0.5)),
}
_SALES_FIELDS: dict[str, tuple[tuple[str, float], ...]] = {
    "fecha": (("fecha", 1.0), ("fecha venta", 1.0), ("fecha factura", 1.0), ("fecha emision", 0.8),
              ("fecha transaccion", 0.8), ("fecha pedido", 0.8), ("dia", 0.5), ("date", 0.8)),
    "producto": (("producto", 1.0), ("nombre producto", 1.0), ("articulo", 0.8), ("item", 0.8),
                 ("descripcion", 0.8), ("referencia", 0.8), ("nombre articulo", 0.8), ("detalle", 0.5),
                 ("mercancia", 0.5)),
    "cantidad": (("cantidad", 1.0), ("unidades", 1.0), ("cantidad vendida", 1.0), ("unidades vendidas", 1.0),
                 ("cant", 0.8), ("qty", 0.8), ("und", 0.8), ("unidad", 0.5)),
    "total": (("total", 1.0), ("valor total", 1.0), ("total venta", 1.0), ("venta total", 1.0), ("importe", 0.8),
              ("monto", 0.8), ("ingreso", 0.8), ("total linea", 0.8), ("subtotal", 0.5), ("valor", 0.5),
              ("venta", 0.5)),
    "precio_unitario": (("precio unitario", 1.0), ("valor unitario", 1.0), ("precio", 0.8), ("precio venta", 0.8),
                        ("vr unitario", 0.8), ("precio unidad", 0.8), ("valor unidad", 0.8), ("p unitario", 0.8),
                        ("pu", 0.5)),
    "cliente": (("cliente", 1.0), ("nombre cliente", 1.0), ("comprador", 0.8), ("razon social", 0.8),
                ("tercero", 0.8), ("cliente nombre", 1.0), ("nombre del cliente", 1.0)),
}
_RECEIVABLES_FIELDS: dict[str, tuple[tuple[str, float], ...]] = {
    "cliente": _SALES_FIELDS["cliente"],
    "vencimiento": (("vencimiento", 1.0), ("fecha vencimiento", 1.0), ("vence", 0.8), ("fecha de pago", 0.5),
                    ("fecha limite", 0.8)),
    "saldo": (("saldo", 1.0), ("valor pendiente", 1.0), ("por cobrar", 1.0), ("pendiente", 0.8), ("deuda", 0.8),
              ("saldo pendiente", 1.0), ("valor", 0.5), ("monto", 0.5)),
}
_FIELD_LABEL = {
    "nombre": "nombre del producto", "costo": "costo (precio de compra)", "stock": "existencias (stock)",
    "precio_venta": "precio de venta", "fecha": "fecha", "producto": "producto", "cantidad": "cantidad",
    "valor": "valor (total o precio unitario)", "total": "total", "precio_unitario": "precio unitario",
    "cliente": "cliente",
}
_MATCH_THRESHOLD = 0.5
_PARTIAL_FACTOR = 0.8     # el encabezado contiene todas las palabras del sinonimo, con alguna extra


def field_score(header, synonyms) -> float:
    """Puntaje 0..1 de un encabezado para un campo. Exacto: peso del sinonimo; contiene las palabras: x0,8."""
    tokens = _tokens(header)
    if not tokens:
        return 0.0
    compact, tset = "".join(tokens), set(tokens)
    best = 0.0
    for phrase, weight in synonyms:
        stoks = _tokens(phrase)
        if tokens == stoks or compact == "".join(stoks):
            best = max(best, weight)
        elif set(stoks) <= tset and len(tokens) <= len(stoks) + 2:
            best = max(best, weight * _PARTIAL_FACTOR)
    return best


@dataclass
class RoleMatch:
    table: Any                                  # engine.Table
    role: str
    fields: dict[str, Any]                      # campo -> engine.Column
    scores: dict[str, float]
    score: float
    ambiguous: dict[str, list[str]] = field(default_factory=dict)


def _match_fields(table, spec) -> tuple[dict, dict, dict]:
    """Asigna columnas a campos de forma voraz por puntaje (una columna, un campo)."""
    cands = []
    for ci, col in enumerate(table.columns):
        for fi, (fname, synonyms) in enumerate(spec.items()):
            s = field_score(col.name, synonyms)
            if s >= _MATCH_THRESHOLD:
                cands.append((-s, fi, ci, fname, col))
    cands.sort(key=lambda c: c[:3])
    fields, scores, used_cols = {}, {}, set()
    for neg, _fi, ci, fname, col in cands:
        if fname in fields or ci in used_cols:
            continue
        fields[fname], scores[fname] = col, -neg
        used_cols.add(ci)
    ambiguous = {}
    for fname, col in fields.items():
        others = [
            c.name for ci, c in enumerate(table.columns)
            if c is not col and ci not in used_cols and field_score(c.name, spec[fname]) == scores[fname]
        ]
        if others:
            ambiguous[fname] = [col.name] + others
    return fields, scores, ambiguous


_STRONG_SCORE = 0.8


def _qualifies(role: str, fields: dict, scores: dict | None = None) -> bool:
    if role == "productos":
        # "cantidad"/"unidades" solos (peso 0,5) tambien aparecen en tablas de movimientos o de ventas: como
        # existencias solo valen si la hoja ademas trae costo o precio de venta.
        scores = scores or {}
        strong_stock = scores.get("stock", 0) >= _STRONG_SCORE
        return "nombre" in fields and (
            "costo" in fields or strong_stock or ("stock" in fields and "precio_venta" in fields)
        )
    if role == "ventas":
        return all(f in fields for f in ("fecha", "producto", "cantidad")) and (
            "total" in fields or "precio_unitario" in fields
        )
    if role == "cartera":
        return "cliente" in fields and "vencimiento" in fields and "saldo" in fields
    return False


_ROLE_SPECS = {"productos": _PRODUCT_FIELDS, "ventas": _SALES_FIELDS}


def detect_roles(catalog: dict) -> tuple[dict[str, RoleMatch], dict[str, list[RoleMatch]], bool]:
    """(rol elegido, alternativas descartadas por rol, hay hoja de cartera) a partir del catalogo de la org.

    Cada tabla recibe a lo sumo UN rol. Entre candidatas gana el mayor puntaje; empate: mas filas, luego nombre.
    Si una tabla califica para dos roles se queda con el de mayor puntaje (empate: ventas)."""
    candidates: list[RoleMatch] = []
    for table in catalog.values():
        for role, spec in _ROLE_SPECS.items():
            fields, scores, ambiguous = _match_fields(table, spec)
            if _qualifies(role, fields, scores):
                candidates.append(RoleMatch(table, role, fields, scores, sum(scores.values()), ambiguous))
    pref = {"ventas": 0, "productos": 1}
    candidates.sort(key=lambda m: (-m.score, pref[m.role], -(m.table.rows or 0), m.table.name))
    chosen: dict[str, RoleMatch] = {}
    used_tables: set = set()
    for m in candidates:
        if m.role in chosen or m.table.name in used_tables:
            continue
        chosen[m.role] = m
        used_tables.add(m.table.name)
    alternatives: dict[str, list[RoleMatch]] = defaultdict(list)
    for m in candidates:
        mine = chosen.get(m.role)
        if (mine is not None and m is not mine and m.table.name not in used_tables and (m.table.rows or 0) > 0):
            alternatives[m.role].append(m)
    has_receivables = False
    for table in catalog.values():
        if table.name in used_tables:
            continue
        fields, _s, _a = _match_fields(table, _RECEIVABLES_FIELDS)
        if _qualifies("cartera", fields):
            has_receivables = True
    return chosen, dict(alternatives), has_receivables


# ---------------------------------------------------------------------------
# Lectura con el motor
# ---------------------------------------------------------------------------

@dataclass
class ProductAgg:
    key: str
    label: str
    rows: int = 0
    stock: Decimal = Decimal(0)          # existencias (negativas cuentan 0)
    has_stock: bool = False
    value: Decimal = Decimal(0)          # suma(existencias x costo)
    cost_weight: Decimal = Decimal(0)    # existencias de las filas con costo (para el costo promedio ponderado)
    cost_rows: Decimal = Decimal(0)      # filas con costo (promedio simple si no hay existencias)
    cost_sum: Decimal = Decimal(0)
    cost: Decimal | None = None          # costo unitario final (None = desconocido)


@dataclass
class ProductsData:
    products: dict[str, ProductAgg]
    rows_used: int
    blank_names: int
    negative_stock_rows: int
    unreadable_stock_rows: int
    duplicated: int                      # nombres normalizados que aparecen en mas de una fila
    thousands_lookalikes: int


@dataclass
class SalesAgg:
    key: str
    label: str
    units: Decimal = Decimal(0)
    revenue: Decimal = Decimal(0)
    lines: list = field(default_factory=list)    # (cantidad, precio unitario, venta de la linea, veces)


@dataclass
class SaleLine:
    """Una forma de venta valida (producto o cliente, dia, cantidad, precio) repetida `n` veces."""
    name: str | None
    client: str | None
    day: date | None
    qty: Decimal
    price: Decimal            # precio real de UNA unidad
    revenue: Decimal          # lo vendido en UNA venta de esta forma (cantidad x precio, o el total)
    n: int


@dataclass
class SalesData:
    products: dict[str, SalesAgg]
    clients: dict[str, tuple[str, Decimal]]      # clave -> (nombre, ventas)
    generic_client_revenue: Decimal
    blank_client_revenue: Decimal
    total_revenue: Decimal                       # todas las ventas validas del periodo
    rows_used: int                               # ventas validas con fecha legible
    invalid_rows: int                            # sin cantidad > 0 o sin precio/total legible
    undated_rows: int                            # validas pero sin fecha legible
    out_of_range_rows: int                       # validas pero con fecha imposible
    thousands_lookalikes: int
    period: tuple[date, date, int] | None        # (primera, ultima, dias) de las ventas validas
    window_days: int
    window_keys: set[str]                        # productos con alguna venta en la ventana de sin_movimiento


def _count(row) -> int:
    return int(row[-1])


def parse_products(rows: list[tuple], has_cost: bool, has_stock: bool) -> ProductsData:
    """Filas (nombre[, costo][, existencias], veces) del motor -> productos agregados por clave normalizada."""
    products: dict[str, ProductAgg] = {}
    blank = negative = unreadable = lookalikes = 0
    per_key_rows: Counter = Counter()
    used = 0
    for row in rows:
        n = _count(row)
        name = row[0]
        key = product_key(name) if name is not None else ""
        if not key:
            blank += n
            continue
        i = 1
        cost = stock = None
        if has_cost:
            raw = row[i]
            i += 1
            cost = engine.parse_number(raw)
            if raw is not None and THOUSANDS_LOOKALIKE.match(str(raw)):
                lookalikes += n
            if cost is not None and cost < 0:
                cost = None
        if has_stock:
            raw = row[i]
            stock = engine.parse_number(raw)
            if raw is not None and THOUSANDS_LOOKALIKE.match(str(raw)):
                lookalikes += n
        agg = products.get(key)
        if agg is None:
            agg = products[key] = ProductAgg(key, str(name))
        used += n
        per_key_rows[key] += n
        agg.rows += n
        eff = Decimal(0)
        if has_stock:
            if stock is None:
                unreadable += n
            else:
                agg.has_stock = True
                if stock < 0:
                    negative += n
                else:
                    eff = stock
        agg.stock += eff * n
        if cost is not None and cost > 0:
            agg.value += eff * cost * n
            agg.cost_weight += eff * n
            agg.cost_rows += n
            agg.cost_sum += cost * n
    for agg in products.values():
        if agg.cost_rows > 0:
            # costo unitario: promedio ponderado por existencias (o promedio simple si no hay existencias)
            agg.cost = agg.value / agg.cost_weight if agg.cost_weight > 0 else agg.cost_sum / agg.cost_rows
    duplicated = sum(1 for c in per_key_rows.values() if c > 1)
    return ProductsData(products, used, blank, negative, unreadable, duplicated, lookalikes)


def parse_sale_rows(rows: list[tuple], has_client: bool, has_unit: bool,
                    has_total: bool) -> tuple[list[SaleLine], int, int]:
    """Filas (producto[, cliente], dia, cantidad[, precio][, total], veces) del motor -> (ventas validas, filas
    invalidas, valores con forma "1.200").

    Valida = cantidad > 0 y precio real legible. Precio real de la venta = precio unitario de la fila (>= 0); si
    falta, total / cantidad (total >= 0). Los valores se repiten mucho (cantidades, precios, fechas): se leen una
    sola vez cada uno (memo local) para no pagar 50.000 veces la misma conversion."""
    lines: list[SaleLine] = []
    invalid = lookalikes = 0
    numbers: dict = {}
    days: dict = {}
    day_at = 2 if has_client else 1

    def number(raw):
        if raw not in numbers:
            numbers[raw] = engine.parse_number(raw)
        return numbers[raw]

    for row in rows:
        n = int(row[-1])
        raws = row[day_at + 1:-1]
        qty = number(raws[0])
        unit = number(raws[1]) if has_unit else None
        total = number(raws[1 + has_unit]) if has_total else None
        for raw in raws:
            if raw is not None and THOUSANDS_LOOKALIKE.match(raw):
                lookalikes += n
        if qty is None or qty <= 0:
            invalid += n
            continue
        if unit is not None and unit >= 0:
            price, revenue = unit, qty * unit
        elif total is not None and total >= 0:
            price, revenue = total / qty, total
        else:
            invalid += n
            continue
        label = row[day_at]
        if label not in days:
            try:
                days[label] = date.fromisoformat(label) if label is not None else None
            except ValueError:
                days[label] = None
        lines.append(SaleLine(row[0], row[1] if has_client else None, days[label], qty, price, revenue, n))
    return lines, invalid, lookalikes


def build_sales(rows: list[tuple], has_client: bool, has_unit: bool, has_total: bool, max_date: date) -> SalesData:
    """Ventas validas del periodo por producto y por cliente.

    El periodo sale de las fechas de las ventas VALIDAS (una fila sin cantidad o precio no es una venta, aunque
    comparta hoja: p. ej. movimientos de inventario cargados en la hoja de ventas no estiran el periodo)."""
    lines, invalid, lookalikes = parse_sale_rows(rows, has_client, has_unit, has_total)
    undated = sum(l.n for l in lines if l.day is None)
    dated = [l for l in lines if l.day is not None]
    in_range = [l for l in dated if MIN_SALE_DATE <= l.day <= max_date]
    out_of_range = sum(l.n for l in dated) - sum(l.n for l in in_range)
    period = None
    window_days, window_keys = 0, set()
    if in_range:
        p_from, p_to = min(l.day for l in in_range), max(l.day for l in in_range)
        days = (p_to - p_from).days + 1
        period = (p_from, p_to, days)
        window_days = min(STALE_WINDOW_DAYS, days)
        window_from = p_to - timedelta(days=window_days - 1)
        window_keys = {product_key(l.name) for l in in_range if l.name is not None and l.day >= window_from}

    products: dict[str, SalesAgg] = {}
    acc: dict[str, list] = {}                    # cliente -> [nombre mostrado, mayor grupo, total]
    total_revenue = generic = blank = Decimal(0)
    used = 0
    for l in in_range:
        amount = l.revenue * l.n
        used += l.n
        total_revenue += amount
        key = product_key(l.name) if l.name is not None else ""
        agg = products.get(key)
        if agg is None:
            agg = products[key] = SalesAgg(key, str(l.name) if l.name is not None else "")
        agg.units += l.qty * l.n
        agg.revenue += amount
        agg.lines.append((l.qty, l.price, l.revenue, l.n))
        if has_client:
            ckey = product_key(l.client) if l.client is not None else ""
            if not ckey:
                blank += amount
            elif ckey in GENERIC_CLIENTS:
                generic += amount
            elif ckey not in acc:
                acc[ckey] = [str(l.client), amount, amount]
            else:
                acc[ckey][2] += amount
                if amount > acc[ckey][1]:        # se muestra el nombre del grupo con mas ventas
                    acc[ckey][0], acc[ckey][1] = str(l.client), amount
    clients = {k: (v[0], v[2]) for k, v in acc.items()}
    return SalesData(products, clients, generic, blank, total_revenue, used, invalid, undated, out_of_range,
                     lookalikes, period, window_days, window_keys)


# ---------------------------------------------------------------------------
# Plan de consultas
# ---------------------------------------------------------------------------

def _grouped_plan(table, columns: list[tuple[str, str | None]]):
    """Plan del motor: agrupa por (columna, bucket de fecha opcional) y cuenta filas. Sin LIMIT practico (el tope es
    de seguridad: ver _complete) y sin orden de salida (el motor ordena por las claves)."""
    keys = []
    for name, bucket in columns:
        col = table.column(name)
        keys.append(engine.Key(f"{bucket}({col.name})" if bucket else col.name, col, bucket))
    return engine.Plan(table.id, tuple(keys), (engine.Agg("count", "count", None),), (), (), MAX_GROUPS)


def _complete(result) -> bool:
    """El resultado trae TODOS los grupos (si no, una cifra seria parcial)."""
    return result.total <= len(result.rows)


# ---------------------------------------------------------------------------
# Recetas
# ---------------------------------------------------------------------------

@dataclass
class Context:
    """Todo lo que las recetas necesitan, ya leido y normalizado (las recetas son funciones puras)."""
    products: ProductsData | None
    sales: SalesData
    period_from: date
    period_to: date
    window_keys: set[str]                 # productos con alguna venta en la ventana de sin_movimiento
    window_days: int
    product_table: str
    sales_table: str
    # avisos de calidad por etiqueta: base (estructura de la hoja), cost (costos), stock (existencias)
    product_notes: dict[str, list[str]]
    sales_notes: list[str]                # hoja de ventas (fechas, valores, datos viejos...)
    join_notes: list[str]                 # ventas que no cruzan con la hoja de productos
    matched_sales: dict[str, SalesAgg]    # ventas de productos que si estan en la hoja de productos
    unmatched_rows: int

    @property
    def days(self) -> int:
        return (self.period_to - self.period_from).days + 1

    def notes(self, tags: tuple[str, ...] = (), *, join: bool = False, short_period: bool = False) -> list[str]:
        """Avisos de un item: productos (segun etiquetas), ventas, cruce y periodo corto."""
        out = [n for tag in tags for n in self.product_notes.get(tag, [])] + list(self.sales_notes)
        if join:
            out += self.join_notes
        if short_period and self.days < SHORT_PERIOD_DAYS:
            out.append(
                f"El periodo de ventas es corto ({fmt_days(self.days)}): la cifra puede cambiar con más historia."
            )
        return out


def _metric(label: str, value, unit: str) -> dict:
    return {"label": label, "value": value, "unit": unit}


def _money_value(d) -> int:
    return int(_dec(d).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _pct_value(ratio) -> float:
    return float((_dec(ratio) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _num_value(d, places: str = "0.1") -> float:
    return float(_dec(d).quantize(Decimal(places), rounding=ROUND_HALF_UP))


def _how(ctx: Context, steps: list[str], tables: list[str], rows_used: int, notes: list[str]) -> dict:
    return {"steps": steps, "tables": tables, "rows_used": rows_used, "notes": notes}


def _item(rid: str, kind: str, severity: str, title: str, sentence: str, metrics: list, action: str | None,
          ask: str | None, how: dict) -> dict:
    return {"id": rid, "kind": kind, "severity": severity, "title": title, "sentence": sentence,
            "metrics": metrics, "action": action, "ask": ask, "how": how}


def _cost_known(ctx: Context) -> int:
    return sum(1 for p in ctx.products.products.values() if p.cost is not None)


def recipe_capital_inventario(ctx: Context) -> dict:
    prods = ctx.products.products
    merchandise = sum((p.value for p in prods.values()), Decimal(0))
    sold_revenue = ctx.sales.total_revenue
    cogs = Decimal(0)
    for key, sales in ctx.matched_sales.items():
        cost = prods[key].cost
        if cost is not None:
            cogs += sales.units * cost
    notes = ctx.notes(("base", "cost", "stock"), join=True, short_period=True)
    months = None
    if cogs > 0 and merchandise >= 0:
        months = merchandise * ctx.days / (cogs * DAYS_PER_MONTH)   # = mercancia / (costo vendido / meses)
    if cogs > 0 and ctx.unmatched_rows:
        notes.append("El costo de lo vendido solo incluye los productos que están en tu hoja de productos.")
    severity = "info"
    if months is not None:
        if months > INVENTORY_IMPORTANT_MONTHS:
            severity = "important"
        elif months > INVENTORY_ATTENTION_MONTHS:
            severity = "attention"
    period = fmt_range(ctx.period_from, ctx.period_to)
    base = "Es lo que pagaste por el inventario que hoy tienes en bodega."
    if months is None:
        sentence = (f"{base} No pude calcular en cuánto tiempo se vende porque no encontré ventas de productos "
                    f"con costo.")
        notes.append("Sin ventas de productos con costo no hay forma de medir cuánto tarda en venderse.")
    else:
        sentence = (f"{base} {period.capitalize()} vendiste {fmt_money(sold_revenue)}: a ese ritmo, tardaría "
                    f"{months_phrase(months)} en venderse.")
    if severity in ("attention", "important"):
        action = "Revisa qué productos compraste de más antes de volver a pedir."
    else:
        action = "Tu inventario está en un nivel razonable: cuida que no crezca más que tus ventas."
    metrics = [_metric("Mercancía a costo", _money_value(merchandise), "money"),
               _metric("Vendido en el periodo", _money_value(sold_revenue), "money")]
    if months is not None:
        metrics.append(_metric("Meses de inventario", _num_value(months), "months"))
    steps = [
        f"Multipliqué las existencias de cada producto por su costo de compra ({plural(len(prods), 'producto', 'productos')}).",
        f"Sumé el costo de lo que vendiste en el periodo ({plural(ctx.sales.rows_used, 'venta', 'ventas')}).",
        f"Dividí la mercancía entre el costo mensual de lo vendido (1 mes = {DAYS_PER_MONTH} días).",
    ]
    return _item("capital_inventario", "money", severity, f"Tienes {fmt_money(merchandise)} en mercancía", sentence,
                 metrics, action, "¿Qué productos tengo con más mercancía comprada?",
                 _how(ctx, steps, [ctx.product_table, ctx.sales_table],
                      ctx.products.rows_used + ctx.sales.rows_used, notes))


def _profit_rows(ctx: Context) -> tuple[list[tuple[ProductAgg, Decimal, Decimal, Decimal]], Decimal]:
    """[(producto, utilidad, ventas, unidades)] de los productos vendidos con costo conocido; y utilidad total."""
    prods = ctx.products.products
    rows, total = [], Decimal(0)
    for key, sales in ctx.matched_sales.items():
        cost = prods[key].cost
        if cost is None:
            continue
        profit = sales.revenue - sales.units * cost
        rows.append((prods[key], profit, sales.revenue, sales.units))
        total += profit
    return rows, total


def recipe_productos_estrella(ctx: Context) -> dict | None:
    rows, total = _profit_rows(ctx)
    positive = sorted((r for r in rows if r[1] > 0), key=lambda r: (-r[1], r[0].key))[:STARS_TOP_N]
    notes = ctx.notes(("base", "cost"), join=True)
    no_cost_sold = sum(1 for k in ctx.matched_sales if ctx.products.products[k].cost is None)
    if no_cost_sold:
        notes.append(f"{plural(no_cost_sold, 'producto vendido no tiene', 'productos vendidos no tienen')} costo: "
                     f"no entran en la utilidad.")
    if not positive:
        return None
    top_total = sum((r[1] for r in positive), Decimal(0))
    names = [f"{short_name(r[0].label)} ({fmt_money(r[1])})" for r in positive]
    n = len(positive)
    lead = f"Son {join_es(names)}." if n > 1 else f"Es {names[0]}."
    together = "Juntos dejan" if n > 1 else "Deja"
    metrics = [_metric("Utilidad de los productos estrella", _money_value(top_total), "money")]
    if total > 0 and top_total <= total:
        share = top_total / total
        sentence = f"{lead} {together} {fmt_money(top_total)} de los {fmt_money(total)} que ganaste con todas tus ventas."
        title = (f"Tus {n} productos estrella dejan el {fmt_percent(share)} de tu utilidad" if n > 1
                 else f"Tu producto estrella deja el {fmt_percent(share)} de tu utilidad")
        metrics.append(_metric("Parte de la utilidad total", _pct_value(share), "percent"))
    else:
        # otros productos pierden plata: los estrella dejan MAS que la utilidad neta total (que puede ser negativa)
        if total > 0:
            sentence = (f"{lead} {together} {fmt_money(top_total)}, más que toda tu utilidad ({fmt_money(total)}), "
                        "porque otros productos te hacen perder plata.")
            title = (f"Tus {n} productos estrella sostienen tu utilidad" if n > 1
                     else "Tu producto estrella sostiene tu utilidad")
        else:
            alone = f"Es {short_name(positive[0][0].label)}." if n == 1 else lead   # el titular ya trae su cifra
            sentence = f"{alone} Aun así, en total tus productos pierden plata ({fmt_money(total)})."
            title = (f"Tus {n} productos estrella dejan {fmt_money(top_total)}" if n > 1
                     else f"Tu producto estrella deja {fmt_money(top_total)}")
    metrics.append(_metric("Utilidad total", _money_value(total), "money"))
    steps = [
        "Para cada venta calculé la utilidad: cantidad × (precio al que vendiste − costo del producto).",
        f"Sumé la utilidad de cada producto y me quedé con los {STARS_TOP_N} que más dejan.",
        "Los comparé con la utilidad de todos tus productos.",
    ]
    return _item("productos_estrella", "opportunity", "info", title, sentence, metrics,
                 "Que nunca te falten estos productos y cuida su precio.",
                 "¿Cuáles son mis productos que más utilidad dejan?",
                 _how(ctx, steps, [ctx.product_table, ctx.sales_table],
                      ctx.products.rows_used + ctx.sales.rows_used, notes))


def _days_phrase(days_left: Decimal, stock: Decimal) -> str:
    if stock <= 0:
        return "ya se agotó"
    whole = int(days_left)    # se redondea hacia abajo: ser conservador con el plazo
    return "en menos de un día" if whole < 1 else f"en {fmt_days(whole)}"


def recipe_reposicion(ctx: Context) -> dict:
    prods = ctx.products.products
    low = []
    for key, sales in ctx.matched_sales.items():
        p = prods[key]
        if not p.has_stock or sales.units <= 0:
            continue
        rate = sales.units / ctx.days                 # unidades por dia (> 0)
        left = p.stock / rate
        if left < RESTOCK_DAYS:
            low.append((left, p, rate))
    low.sort(key=lambda r: (r[0], r[1].key))
    notes = ctx.notes(("base", "stock"), join=True, short_period=True)
    steps = [
        f"Calculé cuántas unidades vendes por día (unidades vendidas ÷ {fmt_days(ctx.days)} del periodo).",
        "Dividí tus existencias entre ese ritmo para saber en cuántos días se acaba cada producto.",
        f"Te muestro los que se acaban en menos de {int(RESTOCK_DAYS)} días.",
    ]
    how = _how(ctx, steps, [ctx.product_table, ctx.sales_table], ctx.products.rows_used + ctx.sales.rows_used, notes)
    if not low:
        return _item("reposicion", "info", "info", "Ningún producto se te agota pronto",
                     f"Al ritmo que vendes, todos tus productos te alcanzan para {int(RESTOCK_DAYS)} días o más.",
                     [_metric("Productos por agotarse", 0, "count")], None,
                     "¿Qué productos debo reponer esta semana?", how)
    shown = low[:RESTOCK_MAX_LISTED]
    parts = [f"{short_name(p.label)} ({_days_phrase(left, p.stock)})" for left, p, _r in shown]
    more = len(low) - len(shown)
    n = len(low)
    head = "Al ritmo que vendes se acaba" if n == 1 else "Al ritmo que vendes se acaban"
    sentence = f"{head}: {join_es(parts)}" + (f" y {plural(more, 'más', 'más')}" if more else "") + "."
    urgent = any(left < RESTOCK_URGENT_DAYS for left, _p, _r in low)
    first_left, first, _ = low[0]
    title = (f"{fmt_int(n)} productos se te agotan en menos de {int(RESTOCK_DAYS)} días" if n > 1
             else f"Un producto se te agota en menos de {int(RESTOCK_DAYS)} días")
    return _item("reposicion", "risk", "important" if urgent else "attention", title, sentence,
                 [_metric("Productos por agotarse", n, "count"),
                  _metric("Más urgente", short_name(first.label), "text"),
                  _metric("Días que le quedan", int(first_left) if first.stock > 0 else 0, "days")],
                 f"Haz hoy el pedido de {short_name(first.label)} a tu proveedor.",
                 "¿Qué productos debo reponer esta semana?", how)


def recipe_clientes_concentracion(ctx: Context) -> dict | None:
    sales = ctx.sales
    ranked = sorted(sales.clients.items(), key=lambda kv: (-kv[1][1], kv[0]))
    total = sales.total_revenue
    if not ranked or total <= 0:
        return None
    first = ranked[0][1]
    top = ranked[:CLIENT_TOP_N]
    top_amount = sum((v[1] for _k, v in top), Decimal(0))
    first_share, top_share = first[1] / total, top_amount / total
    concentrated = first_share > CLIENT_FIRST_ATTENTION or top_share > CLIENT_TOP_ATTENTION
    notes = ctx.notes()
    ignored = sales.generic_client_revenue + sales.blank_client_revenue
    if ignored > 0:
        notes.append(
            f"Hay ventas por {fmt_money(ignored)} sin cliente o a un cliente genérico (mostrador, contado...): "
            f"cuentan en el total pero no como cliente."
        )
    n_top = len(top)
    lead = f"Tus {n_top} mejores clientes" if n_top > 1 else "Tu mejor cliente"
    if concentrated:
        sentence = (f"Solo {short_name(first[0])}, el primero, es el {fmt_percent(first_share)} de lo que vendes: "
                    "depender de pocos clientes te deja expuesto si alguno deja de comprar.")
        action = (f"Cuida tu relación con {short_name(first[0])} y busca más clientes para depender menos de pocos.")
        title = (f"Tus {n_top} mejores clientes son el {fmt_percent(top_share)} de tus ventas" if n_top > 1
                 else f"Tu mejor cliente es el {fmt_percent(top_share)} de tus ventas")
        severity = "attention"
    else:
        if n_top > 1:
            sentence = (f"{lead} suman el {fmt_percent(top_share)} de lo que vendes y el primero, "
                        f"{short_name(first[0])}, el {fmt_percent(first_share)}: ninguno pesa demasiado.")
        else:
            sentence = (f"{lead}, {short_name(first[0])}, es el {fmt_percent(first_share)} de lo que vendes: "
                        "ninguno pesa demasiado.")
        action = "Sigue ampliando tu base de clientes."
        title = "Tus ventas están repartidas entre tus clientes"
        severity = "info"
    steps = [
        "Sumé lo que le vendiste a cada cliente en el periodo.",
        f"Ordené los clientes de mayor a menor y tomé los {CLIENT_TOP_N} primeros.",
        "Los comparé con el total de lo vendido.",
    ]
    return _item("clientes_concentracion", "risk", severity, title, sentence,
                 [_metric("Los 3 mejores clientes", _pct_value(top_share), "percent"),
                  _metric("El mejor cliente", _pct_value(first_share), "percent"),
                  _metric("Clientes distintos", len(sales.clients), "count")],
                 action, "¿Cuáles son mis mejores clientes?",
                 _how(ctx, steps, [ctx.sales_table], sales.rows_used, notes))


def recipe_sin_movimiento(ctx: Context) -> dict:
    prods = ctx.products.products
    window = ctx.window_keys or set()
    stuck = [p for p in prods.values() if p.has_stock and p.stock > 0 and p.key not in window]
    parked = sum((p.value for p in stuck), Decimal(0))
    merchandise = sum((p.value for p in prods.values()), Decimal(0))
    notes = ctx.notes(("base", "cost", "stock"))
    short_period = ctx.days < STALE_WINDOW_DAYS
    if short_period:
        notes.append(
            f"Tus ventas cubren solo {fmt_days(ctx.days)}: usé todo el periodo en lugar de {STALE_WINDOW_DAYS} días."
        )
    no_cost = sum(1 for p in stuck if p.cost is None)
    if no_cost:
        notes.append(f"{plural(no_cost, 'producto parado no tiene', 'productos parados no tienen')} costo: "
                     f"no suman plata en esta cifra.")
    window_text = (f"en los últimos {STALE_WINDOW_DAYS} días" if not short_period
                   else f"en todo el periodo ({fmt_days(ctx.days)})")
    steps = [
        f"Tomé los últimos {fmt_days(ctx.window_days)} de tus ventas (hasta el {fmt_date(ctx.period_to)}), "
        "no contados desde hoy.",
        "Busqué los productos con existencias que no aparecen en ninguna venta de esos días.",
        "Multipliqué sus existencias por su costo para ver cuánta plata tienen parada.",
    ]
    how = _how(ctx, steps, [ctx.product_table, ctx.sales_table], ctx.products.rows_used + ctx.sales.rows_used, notes)
    if not stuck:
        return _item("sin_movimiento", "info", "info", "Todos tus productos se han movido",
                     f"Cada producto con existencias tuvo al menos una venta {window_text}: no hay plata quieta.",
                     [_metric("Productos sin movimiento", 0, "count")], None,
                     "¿Qué productos no se están vendiendo?", how)
    share = parked / merchandise if merchandise > 0 else Decimal(0)
    severity = "attention" if merchandise > 0 and share >= PARKED_ATTENTION_SHARE else "info"
    top = sorted(stuck, key=lambda p: (-p.value, p.key))[:3]
    top_text = join_es([f"{short_name(p.label)} ({fmt_money(p.value)})" for p in top if p.value > 0])
    sentence = (f"Es plata de {plural(len(stuck), 'producto', 'productos')} que no vendiste {window_text}")
    sentence += f", sobre todo {top_text}." if top_text else "."
    return _item("sin_movimiento", "money", severity, f"Tienes {fmt_money(parked)} en productos que no se mueven",
                 sentence,
                 [_metric("Plata parada", _money_value(parked), "money"),
                  _metric("Productos sin movimiento", len(stuck), "count"),
                  _metric("Parte de tu mercancía", _pct_value(share), "percent")],
                 "Piensa en una promoción o en devolver lo que no rota antes de comprar más.",
                 "¿Qué productos no se están vendiendo?", how)


def recipe_margen_bajo(ctx: Context) -> dict:
    prods = ctx.products.products
    flagged = []     # (producto, margen o None, pierde?, perdida)
    for key, sales in ctx.matched_sales.items():
        cost = prods[key].cost
        if cost is None or sales.units <= 0:
            continue
        loss = sum((n * (qty * cost - line) for qty, price, line, n in sales.lines if price < cost), Decimal(0))
        below = any(price < cost for _q, price, _l, _n in sales.lines)
        margin = (sales.revenue - sales.units * cost) / sales.revenue if sales.revenue > 0 else None
        if below or (margin is not None and margin < LOW_MARGIN):
            flagged.append((prods[key], margin, below, loss))
    flagged.sort(key=lambda r: (not r[2], -r[3] if r[2] else (r[1] if r[1] is not None else Decimal(-1)), r[0].key))
    notes = ctx.notes(("base", "cost"), join=True)
    no_cost_sold = sum(1 for k in ctx.matched_sales if prods[k].cost is None)
    if no_cost_sold:
        notes.append(f"{plural(no_cost_sold, 'producto vendido no tiene', 'productos vendidos no tienen')} costo: "
                     f"no se pudo calcular su margen.")
    steps = [
        "Para cada producto vendido calculé su margen: (ventas − costo de lo vendido) ÷ ventas.",
        f"Marqué los que dejan menos de {fmt_percent(LOW_MARGIN)} de margen.",
        "Revisé también si alguna venta se hizo a un precio menor que el costo del producto.",
    ]
    how = _how(ctx, steps, [ctx.product_table, ctx.sales_table], ctx.products.rows_used + ctx.sales.rows_used, notes)
    if not flagged:
        return _item("margen_bajo", "info", "info", "Tus productos dejan un margen sano",
                     f"Ninguno de los que vendiste deja menos de {fmt_percent(LOW_MARGIN)} de margen ni se vendió "
                     "por debajo de su costo.", [_metric("Productos con margen bajo", 0, "count")], None,
                     "¿Qué productos me dejan menos margen?", how)
    losing = [r for r in flagged if r[2]]
    total_loss = sum((r[3] for r in losing), Decimal(0))
    shown = flagged[:LOW_MARGIN_MAX_LISTED]
    parts = []
    for p, margin, below, _loss in shown:
        what = "vendido por debajo de su costo" if below else f"margen {fmt_percent(margin)}"
        parts.append(f"{short_name(p.label)} ({what})")
    more = len(flagged) - len(shown)
    n = len(flagged)
    head = "El que más preocupa" if n == 1 else "Los que más preocupan"
    sentence = f"{head}: {join_es(parts)}" + (f" y {plural(more, 'más', 'más')}" if more else "") + "."
    if losing:
        sentence += f" Las ventas bajo el costo te hicieron perder {fmt_money(total_loss)}."
    metrics = [_metric("Productos con margen bajo", n, "count"),
               _metric("Productos vendidos con pérdida", len(losing), "count")]
    if losing:
        metrics.append(_metric("Pérdida en ventas bajo el costo", _money_value(total_loss), "money"))
    title = (f"{fmt_int(n)} productos te dejan muy poca ganancia" if n > 1 else "Un producto te deja muy poca ganancia")
    action = ("Sube el precio o renegocia el costo de estos productos antes de seguir vendiéndolos así."
              if losing else "Revisa el precio o el costo de estos productos: dejan poco por cada venta.")
    return _item("margen_bajo", "risk", "important" if losing else "attention", title, sentence, metrics, action,
                 "¿Qué productos me dejan menos margen?", how)


RECIPES = (
    {"id": "capital_inventario", "title": "Cuánto dinero tienes en mercancía", "fn": recipe_capital_inventario,
     "products": ("nombre", "costo", "stock"), "sales": ("fecha", "producto", "cantidad", "valor")},
    {"id": "productos_estrella", "title": "Tus productos que más utilidad dejan", "fn": recipe_productos_estrella,
     "products": ("nombre", "costo"), "sales": ("fecha", "producto", "cantidad", "valor")},
    {"id": "reposicion", "title": "Productos que se te agotan pronto", "fn": recipe_reposicion,
     "products": ("nombre", "stock"), "sales": ("fecha", "producto", "cantidad")},
    {"id": "clientes_concentracion", "title": "Cuánto dependes de tus mejores clientes",
     "fn": recipe_clientes_concentracion, "products": (), "sales": ("fecha", "cantidad", "valor", "cliente")},
    {"id": "sin_movimiento", "title": "Mercancía que no se mueve", "fn": recipe_sin_movimiento,
     "products": ("nombre", "costo", "stock"), "sales": ("fecha", "producto", "cantidad")},
    {"id": "margen_bajo", "title": "Productos con margen bajo", "fn": recipe_margen_bajo,
     "products": ("nombre", "costo"), "sales": ("fecha", "producto", "cantidad", "valor")},
)
RECEIVABLES_MISSING = {
    "id": "cartera", "title": "Cuánto te deben tus clientes",
    "needs": "Una hoja con cliente, valor y fecha de vencimiento de cada cuenta por cobrar.",
}


# ---------------------------------------------------------------------------
# Que le falta a cada receta (en lenguaje simple)
# ---------------------------------------------------------------------------

def _has_field(role: RoleMatch | None, field_: str) -> bool:
    if role is None:
        return False
    if field_ == "valor":
        return "total" in role.fields or "precio_unitario" in role.fields
    return field_ in role.fields


def _labels(fields) -> str:
    return join_es([_FIELD_LABEL[f] for f in fields])


def _static_needs(recipe: dict, roles: dict[str, RoleMatch]) -> str | None:
    """Texto de lo que falta segun las columnas detectadas, o None si la receta tiene lo que necesita."""
    parts = []
    for role_name, noun, fields, wanted in (
        ("productos", "productos", recipe["products"], "nombre, costo y existencias"),
        ("ventas", "ventas", recipe["sales"], "fecha, producto, cantidad y valor"),
    ):
        if not fields:
            continue
        role = roles.get(role_name)
        if role is None:
            labels = _labels(f for f in fields if f != "nombre") if role_name == "productos" else _labels(fields)
            parts.append(f"Necesito una hoja de {noun} con {labels}.")
            continue
        absent = [f for f in fields if not _has_field(role, f)]
        if absent:
            parts.append(
                f"A tu hoja de {noun} ('{short_name(role.table.display, 60)}') le falta: {_labels(absent)}."
            )
    return " ".join(parts) or None


# ---------------------------------------------------------------------------
# Orquestacion
# ---------------------------------------------------------------------------

def _colombia_now(now: datetime | None) -> datetime:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(_BASE_TZ)


def _role_notes(role: RoleMatch, alternatives: list[RoleMatch], label: str) -> list[str]:
    notes = []
    for alt in alternatives:
        notes.append(
            f"También encontré la hoja '{short_name(alt.table.display, 60)}' que parece de {label}; usé "
            f"'{short_name(role.table.display, 60)}' (más columnas reconocidas o más filas) y no las mezclé."
        )
    for fname, names in role.ambiguous.items():
        notes.append(
            f"En '{short_name(role.table.display, 60)}' hay varias columnas que podrían ser "
            f"{_FIELD_LABEL.get(fname, fname)} ({', '.join(short_name(n, 30) for n in names)}); usé '{short_name(names[0], 30)}'."
        )
    return notes


async def _read_all(pool, roles: dict[str, RoleMatch], now_local: datetime) -> dict:
    """Lee con el motor, en UNA transaccion de solo lectura (foto consistente), todo lo que las recetas usan.

    Devuelve un dict con `products`, `sales` y `problems` (por rol: por que no se pudo leer; la receta pasa a
    `missing`)."""
    out: dict[str, Any] = {"products": None, "sales": None, "problems": {}}
    prod, sale = roles.get("productos"), roles.get("ventas")
    plans, kinds = [], []
    if prod is not None:
        cols = [(prod.fields["nombre"].name, None)] + [(prod.fields[f].name, None) for f in ("costo", "stock")
                                                       if f in prod.fields]
        plans.append(_grouped_plan(prod.table, cols))
        kinds.append("products")
    has_client = has_unit = has_total = False
    if sale is not None:
        has_client, has_unit, has_total = "cliente" in sale.fields, "precio_unitario" in sale.fields, "total" in sale.fields
        tail = [(sale.fields[f].name, None) for f in ("precio_unitario", "total") if f in sale.fields]
        head = [(sale.fields["producto"].name, None)] + ([(sale.fields["cliente"].name, None)] if has_client else [])
        plans.append(_grouped_plan(sale.table, head + [(sale.fields["fecha"].name, "day"),
                                                       (sale.fields["cantidad"].name, None)] + tail))
        kinds.append("sales")
    if not plans:
        return out
    results = dict(zip(kinds, await engine.run_plans(pool, plans)))

    if "products" in results:
        res = results["products"]
        if _complete(res):
            out["products"] = parse_products(res.rows, "costo" in prod.fields, "stock" in prod.fields)
        else:
            out["problems"]["productos"] = ("Tu hoja de productos tiene demasiadas combinaciones distintas para "
                                            "calcular con exactitud.")
    if "sales" in results:
        res = results["sales"]
        if not _complete(res):
            out["problems"]["ventas"] = ("Tus ventas tienen demasiadas combinaciones distintas (producto, cliente, "
                                         "fecha, cantidad y precio) para calcular con exactitud.")
        else:
            max_date = now_local.date() + timedelta(days=FUTURE_SALE_DAYS)
            sales = build_sales(res.rows, has_client, has_unit, has_total, max_date)
            out["sales"] = sales
            total_rows = sum(int(r[-1]) for r in res.rows)
            if total_rows == 0:
                out["problems"]["ventas"] = ("Tu hoja de ventas está vacía: sube tus ventas con fecha, producto, "
                                             "cantidad y valor.")
            elif sales.period is None:
                if sales.invalid_rows == total_rows:
                    out["problems"]["ventas"] = "Tus ventas no tienen cantidades y valores que pueda leer."
                else:
                    out["problems"]["ventas"] = ("Tus ventas no tienen fechas que pueda leer (por ejemplo "
                                                 "2025-07-02 o 02/07/2025).")
    return out


def _count_note(n: int, one: str, many: str) -> str:
    return f"{plural(n, one, many)}."


def _lookalike_note(n: int, where: str) -> str:
    return (f"{plural(n, 'valor', 'valores')} de tu hoja de {where} {'tiene' if n == 1 else 'tienen'} la forma "
            f"'1.200': se {'leyó' if n == 1 else 'leyeron'} como decimal (1,2), igual que en el chat. Revisa que "
            "no sean miles.")


def _quality_notes(prod, sale, alternatives, data) -> tuple[dict[str, list[str]], list[str], list[str], dict, int]:
    """Avisos de calidad de las hojas y cruce productos <-> ventas. (productos por etiqueta, ventas, cruce,
    ventas que si cruzan, filas de ventas que no cruzan)."""
    products: ProductsData | None = data["products"]
    sales: SalesData | None = data["sales"]
    pn: dict[str, list[str]] = {"base": [], "cost": [], "stock": []}
    sn: list[str] = []
    jn: list[str] = []
    if prod is not None:
        pn["base"] += _role_notes(prod, alternatives.get("productos", []), "productos")
    if sale is not None:
        sn += _role_notes(sale, alternatives.get("ventas", []), "ventas")
    if products is not None:
        if products.blank_names:
            pn["base"].append(_count_note(products.blank_names, "fila sin nombre no se contó en tu hoja de productos",
                                          "filas sin nombre no se contaron en tu hoja de productos"))
        if products.duplicated:
            pn["base"].append(
                f"{plural(products.duplicated, 'producto aparece repetido', 'productos aparecen repetidos')} en tu "
                "hoja de productos: sumé sus existencias y usé el costo promedio."
            )
        if products.thousands_lookalikes:
            pn["base"].append(_lookalike_note(products.thousands_lookalikes, "productos"))
        if products.negative_stock_rows:
            pn["stock"].append(_count_note(products.negative_stock_rows, "fila tiene existencias negativas: la conté como 0",
                                           "filas tienen existencias negativas: las conté como 0"))
        if products.unreadable_stock_rows:
            pn["stock"].append(_count_note(products.unreadable_stock_rows, "fila sin existencias legibles no se contó",
                                           "filas sin existencias legibles no se contaron"))
        if prod is not None and "costo" in prod.fields:
            no_cost = sum(1 for p in products.products.values() if p.cost is None)
            if no_cost:
                pn["cost"].append(_count_note(no_cost, "producto no tiene costo (vacío o en cero): no suma",
                                              "productos no tienen costo (vacío o en cero): no suman"))
    matched, unmatched_rows = {}, 0
    if sales is not None:
        if sales.undated_rows:
            sn.append(_count_note(sales.undated_rows, "venta sin fecha legible no se contó",
                                  "ventas sin fecha legible no se contaron"))
        if sales.out_of_range_rows:
            sn.append(
                f"{plural(sales.out_of_range_rows, 'venta con una fecha imposible no se contó', 'ventas con una fecha imposible no se contaron')} "
                "(antes del año 2000 o más de un año en el futuro)."
            )
        if sales.invalid_rows:
            sn.append(_count_note(sales.invalid_rows, "venta sin cantidad o valor legible no se contó",
                                  "ventas sin cantidad o valor legible no se contaron"))
        if sales.thousands_lookalikes:
            sn.append(_lookalike_note(sales.thousands_lookalikes, "ventas"))
        if products is not None:
            matched = {k: a for k, a in sales.products.items() if k in products.products}
            unmatched = [a for k, a in sales.products.items() if k not in products.products]
            unmatched_rows = sum(n for a in unmatched for *_x, n in a.lines)
            if unmatched:
                examples = join_es([f"'{short_name(a.label or '(sin producto)', 30)}'"
                                    for a in sorted(unmatched, key=lambda a: (-a.revenue, a.key))[:3]])
                jn.append(
                    f"{plural(unmatched_rows, 'venta', 'ventas')} de {plural(len(unmatched), 'producto', 'productos')} "
                    f"que no están en tu hoja de productos (por ejemplo {examples}): no entran en los cálculos de "
                    "costo y utilidad."
                )
    return pn, sn, jn, matched, unmatched_rows


def _runtime_needs(recipe: dict, data: dict) -> str | None:
    """Que le falta a una receta cuyas columnas SI existen, segun lo que se leyo de las filas."""
    products: ProductsData | None = data["products"]
    sales: SalesData | None = data["sales"]
    found = [data["problems"][role] for role, key in (("productos", "products"), ("ventas", "sales"))
             if recipe[key] and role in data["problems"]]
    if recipe["products"] and "productos" not in data["problems"] and (products is None or not products.products):
        found.append("Tu hoja de productos está vacía o sin nombres legibles: sube tus productos con costo y existencias.")
    if found:
        return " ".join(found)
    if recipe["sales"] and sales is None:
        return "Tus ventas no tienen cantidades y valores que pueda leer."
    if recipe["sales"] and sales.rows_used == 0:
        return "Tus ventas no tienen cantidades y valores que pueda leer."
    if "costo" in recipe["products"] and not any(p.cost is not None for p in products.products.values()):
        return "El costo (precio de compra) de tus productos está vacío o en cero: lo necesito para calcular esto."
    if "stock" in recipe["products"] and not any(p.has_stock for p in products.products.values()):
        return "Las existencias de tus productos están vacías: las necesito para calcular esto."
    return None


_EMPTY_RESULT_NEEDS = {
    "productos_estrella": "Ventas con utilidad positiva: con tus datos actuales ningún producto deja ganancia.",
    "clientes_concentracion": "Una columna de cliente con nombres en tus ventas (la que tienes está vacía o solo "
                              "trae clientes genéricos como mostrador).",
}


def _compose(roles, alternatives, has_receivables, data, now_local: datetime) -> dict:
    prod, sale = roles.get("productos"), roles.get("ventas")
    sales_data: SalesData | None = data["sales"]
    period = sales_data.period if sales_data is not None else None
    pn, sn, jn, matched, unmatched_rows = _quality_notes(prod, sale, alternatives, data)
    if period is not None:
        gap = (now_local.date() - period[1]).days
        if gap > STALE_DATA_DAYS:
            sn.append(f"Tu última venta registrada es del {fmt_date(period[1])}: si ya vendiste después, sube el "
                      "archivo actualizado.")
    ctx = None
    if period is not None and not data["problems"].get("ventas"):
        ctx = Context(
            products=data["products"], sales=sales_data, period_from=period[0], period_to=period[1],
            window_keys=sales_data.window_keys, window_days=sales_data.window_days,
            product_table=prod.table.display if prod else "", sales_table=sale.table.display,
            product_notes=pn, sales_notes=sn, join_notes=jn, matched_sales=matched, unmatched_rows=unmatched_rows,
        )

    items: list[dict] = []
    missing: list[dict] = []
    for recipe in RECIPES:
        needs = _static_needs(recipe, roles) or _runtime_needs(recipe, data)
        item = None
        if needs is None:
            try:
                item = recipe["fn"](ctx)
            except Exception:   # datos rarisimos en una receta no deben tumbar las demas ni responder 500
                logger.exception("La receta %s fallo; se omite", recipe["id"])
                needs = "Revisa que tus datos de productos y ventas estén completos."
            else:
                if item is None:
                    needs = _EMPTY_RESULT_NEEDS[recipe["id"]]
        if needs is not None:
            missing.append({"id": recipe["id"], "title": recipe["title"], "needs": needs})
        else:
            items.append(item)
    if not has_receivables:
        missing.append(dict(RECEIVABLES_MISSING))
    order = {rid: i for i, rid in enumerate(IMPACT_ORDER)}
    # severidad; dentro de cada una primero lo accionable (con `action`) y al final los "todo bien"; luego impacto
    items.sort(key=lambda it: (-SEVERITY_RANK[it["severity"]], 0 if it["action"] else 1, order.get(it["id"], 99)))
    return {"items": items, "missing": missing}


def build_summary_text(now_local: datetime, items: list[dict], missing: list[dict], period) -> str:
    heading = f"Resumen de tu negocio ({_WEEKDAYS[now_local.weekday()]} {now_local.day} de {_MONTHS[now_local.month - 1]})"
    lines = [heading]
    if items:
        lines += [f"• {it['title']}. {it['sentence']}" for it in items]
        if period is not None:
            lines.append(f"Calculado con tus ventas {fmt_range(period[0], period[1])}.")
    else:
        first = next((m for m in missing if m["id"] != "cartera"), None)
        lines.append("• Todavía no puedo calcular hallazgos con tus datos."
                     + (f" {first['needs']}" if first else ""))
    return "\n".join(lines)


async def _compute(org_id: str, now: datetime | None) -> dict:
    now_local = _colombia_now(now)
    pool = await get_org_pool(org_id)
    async with pool.acquire() as conn:
        records = await conn.fetch(
            "SELECT id, table_name, display_name, row_count, columns_definition FROM org_data_tables"
        )
    catalog = engine.build_catalog(records)
    roles, alternatives, has_receivables = detect_roles(catalog)
    data = await _read_all(pool, roles, now_local)
    composed = _compose(roles, alternatives, has_receivables, data, now_local)
    period = data["sales"].period if data["sales"] is not None and not data["problems"].get("ventas") else None
    return {
        "generated_at": now_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "recipe_pack": RECIPE_PACK,
        "period": ({"from": period[0].isoformat(), "to": period[1].isoformat(), "days": period[2]}
                   if period else None),
        "items": composed["items"],
        "missing": composed["missing"],
        "summary_text": build_summary_text(now_local, composed["items"], composed["missing"], period),
    }


async def get_business_insights(org_id: str, now: datetime | None = None) -> dict:
    """Hallazgos de la organizacion (dict con la forma del contrato GET /api/v1/insights).

    `now` solo se inyecta en tests (fecha del resumen y "datos viejos"); en produccion es la hora actual."""
    try:
        return await asyncio.wait_for(_compute(org_id, now), timeout=TOTAL_TIMEOUT_SECONDS)
    except asyncio.TimeoutError as exc:
        raise InsightsUnavailable("Tus datos tardaron demasiado en calcularse. Intenta de nuevo en un momento.") from exc
    except engine.QueryError:
        logger.exception("Plan de hallazgos invalido para la org %s", org_id)
        raise
    except (OSError, ConnectionError) as exc:
        raise InsightsUnavailable("No pude leer tus datos ahora. Intenta de nuevo en un momento.") from exc
    except Exception as exc:   # asyncpg.PostgresError (timeout de sentencia, BD caida...) sin importar asyncpg aqui
        if type(exc).__module__.startswith("asyncpg"):
            raise InsightsUnavailable("No pude leer tus datos ahora. Intenta de nuevo en un momento.") from exc
        raise
