"""Nombres legibles de columnas, titulos de graficos y unidades — PI0320251.

El duenio no tecnico no debe ver "Suma de vr.total por mes de fec". Todo aqui es DETERMINISTA (sin IA):

  1. Si la columna trae un ROL de negocio confirmado (carga inteligente: `total`, `producto`, `cliente`...), se usa
     el vocabulario de ese rol ("Ventas", "producto", "forma de pago").
  2. Si no, se humaniza el encabezado: se separan guiones, puntos y camelCase, se expanden las abreviaturas
     comunes ("vr" -> "valor", "cant" -> "cantidad", "fec" -> "fecha", "p.unit" -> "precio unitario") y se
     restauran las tildes mas frecuentes.

Estos nombres son SOLO de presentacion: la huella de un tablero (`chart_specs.fingerprint`) y todo lo que se
guarda siguen usando los nombres canonicos de columna, nunca las etiquetas.
"""

import re
import unicodedata
from datetime import date

from app.services import data_query_engine as engine
from app.services import intake_ontology as onto

MONTHS_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
    "noviembre", "diciembre",
)
BUCKET_WORD = {"day": "día", "week": "semana", "month": "mes", "year": "año"}

# ---------------------------------------------------------------------------
# Humanizador de encabezados
# ---------------------------------------------------------------------------

# Pares de palabras que juntas significan otra cosa ("p.unit" = precio unitario).
_BIGRAMS = {
    ("p", "unit"): "precio unitario", ("p", "unitario"): "precio unitario", ("pr", "unit"): "precio unitario",
    ("pre", "unit"): "precio unitario", ("v", "unit"): "valor unitario", ("vr", "unit"): "valor unitario",
    ("vlr", "unit"): "valor unitario", ("val", "unit"): "valor unitario", ("c", "unit"): "costo unitario",
    ("sell", "price"): "precio de venta", ("unit", "price"): "precio unitario", ("unit", "cost"): "costo unitario",
    ("fec", "ven"): "fecha de vencimiento", ("fecha", "ven"): "fecha de vencimiento",
    ("payment", "method"): "método de pago", ("met", "pago"): "método de pago", ("metodo", "pago"): "método de pago", ("forma", "pago"): "forma de pago",
}
_ABBREV = {
    "vr": "valor", "vlr": "valor", "val": "valor", "cant": "cantidad", "cantd": "cantidad", "ctd": "cantidad",
    "cnt": "cantidad", "qty": "cantidad", "fec": "fecha", "fch": "fecha", "tot": "total", "dcto": "descuento",
    "dscto": "descuento", "unit": "unitario", "und": "unidades", "unds": "unidades", "uds": "unidades",
    "unid": "unidades", "prod": "producto", "prov": "proveedor", "cli": "cliente", "cat": "categoría",
    "ref": "referencia", "doc": "documento", "obs": "observaciones", "dir": "dirección", "tel": "teléfono",
    "cel": "celular", "cod": "código", "nro": "número", "num": "número", "pcio": "precio", "prec": "precio",
    "mto": "monto", "fact": "factura", "cta": "cuenta", "ciud": "ciudad", "dpto": "departamento",
    "mpio": "municipio", "sucur": "sucursal", "vend": "vendedor",
    # Inglés frecuente en archivos exportados de otros programas.
    "item": "producto", "cost": "costo", "price": "precio", "date": "fecha", "name": "nombre",
    "customer": "cliente", "client": "cliente", "product": "producto", "amount": "monto",
    "supplier": "proveedor", "category": "categoría", "stock": "existencias", "quantity": "cantidad",
    "payment": "pago", "method": "método", "discount": "descuento",
}
_ACRONYMS = frozenset({"iva", "nit", "sku", "ean", "id", "pdf", "url", "rut", "pos", "cc", "dian"})
# Tildes que los encabezados suelen perder.
_ACCENTS = {
    "region": "región", "categoria": "categoría", "categorias": "categorías", "telefono": "teléfono",
    "codigo": "código", "numero": "número", "metodo": "método", "pais": "país", "area": "área", "dia": "día",
    "dias": "días", "credito": "crédito", "debito": "débito", "ultimo": "último", "ultima": "última",
    "linea": "línea", "articulo": "artículo", "articulos": "artículos", "cedula": "cédula", "razon": "razón",
    "almacen": "almacén", "periodo": "período", "minimo": "mínimo", "maximo": "máximo", "direccion": "dirección",
    "descripcion": "descripción", "cuanto": "cuánto", "ano": "año", "anio": "año", "mes": "mes",
    "facturacion": "facturación", "observaciones": "observaciones", "telefonos": "teléfonos",
    "quien": "quién", "cual": "cuál", "ultimos": "últimos",
}
_SPLIT_CAMEL = re.compile(r"(?<=[a-záéíóúñ])(?=[A-ZÁÉÍÓÚÑ])")
_SEPARATORS = re.compile(r"[\s_\-./\\:;,]+")


def _accent(word: str) -> str:
    if word in _ACCENTS:
        return _ACCENTS[word]
    if re.fullmatch(r"[a-z]{2,}cion", word):
        return word[:-4] + "ción"
    if re.fullmatch(r"[a-z]{2,}sion", word):
        return word[:-4] + "sión"
    return word


def humanize_words(raw) -> list[str]:
    """Encabezado crudo -> lista de palabras legibles en minuscula (siglas en mayuscula). Nunca lanza."""
    text = unicodedata.normalize("NFC", str(raw or ""))[:120]
    text = text.strip("¿?¡!()[]{}#*'\"` ")
    text = _SPLIT_CAMEL.sub(" ", text)
    tokens = [t for t in _SEPARATORS.split(text.lower()) if t]
    words: list[str] = []
    i = 0
    while i < len(tokens):
        pair = _BIGRAMS.get((tokens[i], tokens[i + 1])) if i + 1 < len(tokens) else None
        if pair:
            words.extend(pair.split())
            i += 2
            continue
        words.append(_ABBREV.get(tokens[i], tokens[i]))
        i += 1
    out = []
    for w in words:
        w = w.upper() if w in _ACRONYMS else _accent(w)
        if not out or out[-1] != w:          # "valor valor" no aporta
            out.append(w)
    return out


def humanize(raw, fallback: str = "Columna") -> str:
    """'vr.total' -> 'Valor total'; 'p.unit' -> 'Precio unitario'; 'cuánto_debe' -> 'Cuánto debe'."""
    words = humanize_words(raw)
    if not words:
        return fallback
    first = words[0]
    words[0] = first if first.isupper() and len(first) > 1 else first[:1].upper() + first[1:]
    return " ".join(words)[:60]


def lower_phrase(text: str) -> str:
    """'Valor total' -> 'valor total'; las siglas ('IVA') se respetan."""
    words = text.split(" ")
    return " ".join(w if (w.isupper() and len(w) > 1) else w.lower() for w in words)


def capitalize(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def plural(phrase: str) -> str:
    """Plural simple de una frase nominal: solo la primera palabra ('forma de pago' -> 'formas de pago')."""
    head, _, rest = phrase.partition(" ")
    if not head:
        return phrase
    if head.endswith("z"):
        head = head[:-1] + "ces"
    elif head[-1] in "aeiouáéíóú":
        head += "s"
    elif head.endswith("s"):
        pass
    else:
        head += "es"
    return f"{head} {rest}".strip()


# ---------------------------------------------------------------------------
# Vocabulario por rol
# ---------------------------------------------------------------------------

# Frase minuscula que sigue a "por": "ventas por <producto>".
_DIM_BY_ROLE = {
    "producto": "producto", "producto_nombre": "producto", "producto_codigo": "código de producto",
    "categoria": "categoría", "cliente": "cliente", "metodo_pago": "forma de pago", "proveedor": "proveedor",
    "estado": "estado", "tipo_movimiento": "tipo de movimiento", "documento": "documento", "nombre": "nombre",
    "contacto": "contacto", "fecha": "fecha", "fecha_emision": "fecha de emisión",
    "fecha_vencimiento": "fecha de vencimiento",
}
# (tipo de hoja, rol) -> sustantivo de la medida para titulos de graficos ("Ventas por mes").
_MEASURE_NOUN = {
    ("ventas", "total"): "Ventas", ("compras", "total"): "Compras", ("ventas", "cantidad"): "Unidades vendidas",
    ("compras", "cantidad"): "Unidades compradas", ("movimientos_inventario", "cantidad"): "Unidades movidas",
    ("cuentas_por_cobrar", "valor"): "Cartera por cobrar", ("ventas", "precio_unitario"): "Precio por unidad",
    ("productos", "precio_venta"): "Precio de venta", ("productos", "stock"): "Existencias",
    ("productos", "costo_unitario"): "Costo", ("compras", "costo_unitario"): "Costo por unidad",
}
_MEASURE_NOUN_BY_ROLE = {
    "precio_unitario": "Precio por unidad", "costo_unitario": "Costo por unidad", "precio_venta": "Precio de venta",
    "stock": "Existencias", "cantidad": "Unidades", "total": "Total", "valor": "Valor",
}
# Cifra suma / promedio con nombre propio.
_SUM_LABEL = {
    ("ventas", "total"): "Total vendido", ("compras", "total"): "Total comprado",
    ("cuentas_por_cobrar", "valor"): "Total que te deben", ("productos", "stock"): "Unidades en existencias",
    ("ventas", "cantidad"): "Unidades vendidas", ("compras", "cantidad"): "Unidades compradas",
    ("movimientos_inventario", "cantidad"): "Unidades movidas",
}
_AVG_LABEL = {
    ("ventas", "total"): "Venta promedio", ("compras", "total"): "Compra promedio",
    ("cuentas_por_cobrar", "valor"): "Deuda promedio",
}
COUNT_NOUN = {
    "ventas": "ventas", "compras": "compras", "cuentas_por_cobrar": "cuentas por cobrar",
    "movimientos_inventario": "movimientos", "productos": "productos", "clientes": "clientes",
    "proveedores": "proveedores",
}
# Roles que son dinero (aunque el encabezado no lo diga) y roles que NUNCA lo son.
MONEY_ROLES = frozenset({"total", "precio_unitario", "costo_unitario", "valor", "precio_venta"})
NON_MONEY_ROLES = frozenset({"cantidad", "stock"})
# Dimensiones categoricas que un duenio reconoce de inmediato (orden de preferencia para desglosar).
CATEGORY_ROLES = ("producto", "producto_nombre", "cliente", "categoria", "metodo_pago", "proveedor", "estado",
                  "tipo_movimiento")
# Para elegir como desglosar cuando no hay roles: por palabras del encabezado.
NAME_ORDER = ("producto", "servicio", "plato", "cliente", "categoria", "linea", "marca", "proveedor", "vendedor",
              "sede", "sucursal", "ciudad", "region", "metodo", "medio", "canal", "tipo", "estado")


def _role(col) -> str | None:
    return getattr(col, "role", None)


def _kind(table) -> str | None:
    return getattr(table, "sheet_kind", None)


def raw_name(col) -> str:
    """Encabezado del que partir: el original del archivo si lo hay, si no el nombre canonico."""
    return col.label or col.name


def dim_phrase(col) -> str:
    """Frase minuscula de una columna usada como dimension: 'producto', 'forma de pago', 'valor total'."""
    role = _role(col)
    if role in _DIM_BY_ROLE:
        return _DIM_BY_ROLE[role]
    return lower_phrase(humanize(raw_name(col)))


def dim_label(col) -> str:
    """Etiqueta corta para selectores y encabezados de tabla: 'Producto', 'Forma de pago'."""
    return capitalize(dim_phrase(col))


def measure_noun(col, table=None) -> str:
    role = _role(col)
    if role:
        noun = _MEASURE_NOUN.get((_kind(table), role)) or _MEASURE_NOUN_BY_ROLE.get(role)
        if noun:
            return noun
    return humanize(raw_name(col))


def measure_label(col, table=None) -> str:
    """Nombre completo para chips y encabezados: 'Total de la venta', 'Precio por unidad'."""
    role = _role(col)
    kind = _kind(table)
    if role and kind in onto.ROLES_BY_KIND:
        title = onto.role_titles(kind, role)[0]
        if role in onto.ROLES_BY_KIND[kind]:
            return title
    return humanize(raw_name(col))


def column_label(col, table=None) -> str:
    """Nombre legible de cualquier columna (rol primero, encabezado humanizado si no)."""
    role = _role(col)
    kind = _kind(table)
    if role in _DIM_BY_ROLE and col.kind in (engine.KIND_TEXT, engine.KIND_BOOL):
        return dim_label(col)
    if role and kind in onto.ROLES_BY_KIND:
        return measure_label(col, table)
    return humanize(raw_name(col))


def bucket_phrase(key) -> str:
    """'mes', 'día'... o la dimension ('producto'). Lo que sigue a 'por' en un titulo."""
    if key.bucket:
        return BUCKET_WORD[key.bucket]
    return "fecha" if key.col.kind == engine.KIND_DATE else dim_phrase(key.col)


def key_label(key) -> str:
    """Encabezado del eje X: 'Mes', 'Producto', 'Día'."""
    return capitalize(bucket_phrase(key))


def count_noun(table=None) -> str:
    return COUNT_NOUN.get(_kind(table) or "", "registros")


def agg_noun(agg, table=None) -> str:
    """Nombre de la medida para ejes y titulos: 'Ventas', 'Cantidad de ventas'."""
    if agg.fn == "count" or agg.col is None:
        return capitalize(f"número de {count_noun(table)}")
    if agg.fn == "count_distinct":
        return capitalize(f"cantidad de {plural(dim_phrase(agg.col))} diferentes")
    return measure_noun(agg.col, table)


def _fn_prefix(fn: str) -> str:
    return {"avg": "Promedio de", "min": "Mínimo de", "max": "Máximo de"}[fn]


def agg_title(agg, table=None) -> str:
    """Cifra: 'Total vendido', 'Venta promedio', 'Registros de Ventas' (conteo) — para la etiqueta de un KPI."""
    if agg.fn == "count" or agg.col is None:
        return f"Registros de {engine.cell(table.display, 40)}" if table is not None else "Registros"
    if agg.fn == "count_distinct":
        return agg_noun(agg, table)
    role, kind = _role(agg.col), _kind(table)
    if agg.fn == "sum":
        specific = _SUM_LABEL.get((kind, role))
        if specific:
            return specific
        return f"Suma de {lower_phrase(measure_noun(agg.col, table))}"
    if agg.fn == "avg" and (kind, role) in _AVG_LABEL:
        return _AVG_LABEL[(kind, role)]
    return f"{_fn_prefix(agg.fn)} {lower_phrase(measure_noun(agg.col, table))}"


def chart_title(key, agg, table=None) -> str:
    """'Ventas por mes', 'Total por producto', 'Venta promedio por cliente'."""
    by = bucket_phrase(key)
    if agg.fn == "sum" and agg.col is not None:
        return f"{measure_noun(agg.col, table)} por {by}"
    if agg.fn == "avg" and agg.col is not None and (_kind(table), _role(agg.col)) in _AVG_LABEL:
        return f"{_AVG_LABEL[(_kind(table), _role(agg.col))]} por {by}"
    if agg.fn in ("count", "count_distinct") or agg.col is None:
        return f"{agg_noun(agg, table)} por {by}"
    return f"{agg_title(agg, table)} por {by}"


def unit_of(agg) -> str:
    """'count' (conteos), 'money' si la medida es dinero (por ROL o por nombre), 'number' en otro caso."""
    if agg.fn in ("count", "count_distinct") or agg.col is None:
        return "count"
    role = _role(agg.col)
    if role in MONEY_ROLES:
        return "money"
    if role in NON_MONEY_ROLES:
        return "number"
    from app.services.chart_specs import is_money_name      # import tardio: chart_specs importa este modulo

    return "money" if is_money_name(raw_name(agg.col)) or is_money_name(agg.col.name) else "number"


# ---------------------------------------------------------------------------
# Fechas y titulos del detalle
# ---------------------------------------------------------------------------

def date_es(d: date) -> str:
    return f"{d.day} de {MONTHS_ES[d.month - 1]} de {d.year}"


def period_phrase(bucket: str, value: str) -> str | None:
    """'2026-09-15' (day) -> 'del 15 de septiembre de 2026'; '2026-09' (month) -> 'de septiembre de 2026'."""
    try:
        if bucket == "day":
            return "del " + date_es(date.fromisoformat(value))
        if bucket == "week":
            d = date.fromisoformat(value)
            return f"de la semana del {d.day} de {MONTHS_ES[d.month - 1]} de {d.year}"
        if bucket == "month":
            y, m = value.split("-")
            return f"de {MONTHS_ES[int(m) - 1]} de {int(y)}"
        if bucket == "year":
            return f"de {int(value)}"
    except (ValueError, IndexError):
        return None
    return None


_PREP_BY_ROLE = {"producto": "de", "producto_nombre": "de", "cliente": "de", "proveedor": "de", "categoria": "de",
                 "nombre": "de", "metodo_pago": "pagadas con"}


def slice_title(noun: str, key, value, *, empty: bool = False, other: int | None = None) -> str:
    """Titulo humano del dato tocado: 'Ventas del 15 de septiembre de 2026', 'Ventas de Cemento Argos'."""
    col = key.col
    if other is not None:
        return f"{noun} de los {other} {plural(dim_phrase(col))} restantes" if other != 1 else f"{noun} del otro grupo"
    if empty:
        return f"{noun} sin {dim_phrase(col)}"
    text = engine.cell(value, 60)
    if key.bucket:
        phrase = period_phrase(key.bucket, str(value))
        return f"{noun} {phrase}" if phrase else f"{noun} · {key_label(key)}: {text}"
    prep = _PREP_BY_ROLE.get(_role(col))
    if prep == "pagadas con":
        return f"{noun} (pagadas con {text})"
    if prep:
        return f"{noun} {prep} {text}"
    return f"{noun} · {dim_label(col)}: {text}"
