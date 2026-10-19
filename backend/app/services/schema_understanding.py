"""Paso DETERMINISTA del agente de esquema ("entender la hoja") — PI0320251.

Sin red y sin modelo: a partir de los encabezados, el tipo de cada columna y una muestra de sus valores decide
(a) de que TIPO es la hoja (`kind`: productos, ventas, compras...) y (b) que ROL cumple cada columna (fecha,
producto, costo_unitario...), con una confianza 0..1. Si la confianza es alta no hace falta llamar a ningun
modelo (ver schema_ai_service); si es baja, este resultado sirve de respaldo (`mapping_source: "heuristic"`).

Entiende espanol, ingles y abreviaturas de planillas colombianas ("Vlr Compra", "Cant", "Prec Unit", "qty",
"price", "customer"). Los encabezados genericos ("C1", "Col 2") no dicen nada: esas hojas salen con confianza
baja y quedan para el modelo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from app.services import intake_ontology as onto
from app.services.intake_ontology import fold

# ---------------------------------------------------------------------------
# Umbrales
# ---------------------------------------------------------------------------
HEADER_MATCH_MIN = 0.5          # puntaje minimo de un encabezado para asignarle un rol
CLEAR_CONFIDENCE = 0.8          # confianza minima del tipo para NO llamar al modelo
CLEAR_MARGIN = 0.15             # ventaja minima sobre el segundo tipo candidato
NAME_HINT_BONUS = 0.25          # el nombre de la hoja/archivo ("Compras 2026") apoya un tipo
MAX_PROFILE_VALUES = 200        # valores por columna que se miran para tipo/ratios

# ---------------------------------------------------------------------------
# Tokens y abreviaturas
# ---------------------------------------------------------------------------
_STOPWORDS = frozenset({"de", "del", "la", "el", "los", "las", "en", "por", "y", "cop", "un", "una", "al", "the",
                        "of", "col", "columna"})
_ABBREV = {
    "vr": "valor", "vlr": "valor", "val": "valor", "unit": "unitario", "unitary": "unitario", "und": "unidad",
    "uds": "unidades", "unds": "unidades", "cant": "cantidad", "cnt": "cantidad", "prod": "producto",
    "desc": "descripcion", "descrip": "descripcion", "fec": "fecha", "qty": "cantidad", "quantity": "cantidad",
    "exist": "existencia", "cli": "cliente", "prec": "precio", "pcio": "precio", "cto": "costo",
    "pu": "precio unitario", "pvp": "pvp", "tel": "telefono", "cel": "celular", "ref": "referencia",
    "cod": "codigo", "nro": "numero", "num": "numero", "no": "numero", "vta": "venta", "vtas": "venta",
    "cpa": "compra", "cpas": "compra", "prov": "proveedor", "dcto": "descuento", "tot": "total",
    "mov": "movimiento", "fact": "factura", "pago": "pago",
}
# Traducciones directas (el ingles aporta palabras sueltas; las frases se arman con ellas).
_EN = {"price": "precio", "cost": "costo", "customer": "cliente", "client": "cliente", "product": "producto",
       "item": "item", "date": "fecha", "amount": "monto", "supplier": "proveedor", "vendor": "proveedor",
       "name": "nombre", "phone": "telefono", "mobile": "celular", "status": "estado", "payment": "pago",
       "method": "metodo", "category": "categoria", "invoice": "factura", "due": "vencimiento",
       "balance": "saldo", "units": "unidades", "unit": "unitario", "stock": "stock", "inventory": "inventario",
       "contact": "contacto", "mail": "email", "revenue": "ingreso", "sales": "venta", "sale": "venta",
       "purchase": "compra", "type": "tipo", "movement": "movimiento", "document": "documento",
       "order": "orden", "total": "total", "code": "codigo", "email": "email"}


def _stem(token: str) -> str:
    return token[:-1] if len(token) > 3 and token.endswith("s") and not token.endswith("ss") else token


def _tokens(text: Any) -> list[str]:
    out: list[str] = []
    for t in fold(text).split():
        t = _ABBREV.get(t, t)
        t = _EN.get(t, t)
        out.extend(t.split())
    return [_stem(t) for t in out if t not in _STOPWORDS]


def _syn(strong: str = "", alias: str = "", weak: str = "") -> tuple[tuple[str, float], ...]:
    """Sinonimos separados por '|' en tres fuerzas: nombre 'de manual' (1,0), alias comun (0,85) y debil (0,55)."""
    out: list[tuple[str, float]] = []
    for text, weight in ((strong, 1.0), (alias, 0.85), (weak, 0.55)):
        out.extend((p.strip(), weight) for p in text.split("|") if p.strip())
    return tuple(out)


# (tipo, rol) -> sinonimos. El MISMO encabezado puede servir a roles distintos segun el tipo.
SYNONYMS: dict[tuple[str, str], tuple[tuple[str, float], ...]] = {
    ("productos", "producto_nombre"): _syn(
        "nombre|producto|nombre producto|descripcion producto|product name",
        "articulo|item|descripcion|nombre articulo|nombre item", "detalle|mercancia|material|insumo"),
    ("productos", "producto_codigo"): _syn(
        "codigo|sku|ean|codigo barras|referencia|codigo producto|plu", "barcode|cod barras|id producto"),
    ("productos", "categoria"): _syn("categoria|linea|familia|grupo|rubro", "subcategoria|clase", "tipo"),
    ("productos", "costo_unitario"): _syn(
        "costo|costo unitario|precio compra|costo promedio|costo compra|valor compra|precio costo",
        "precio proveedor|costo producto|costo unidad|valor costo|costo neto", "compra"),
    ("productos", "precio_venta"): _syn(
        "precio venta|pvp|precio publico|precio lista|valor venta",
        "precio|precio unitario|valor unitario|precio al publico|precio final"),
    ("productos", "stock"): _syn(
        "stock|existencia|existencia actual|stock actual|cantidad disponible|unidades disponibles|inventario",
        "disponible|saldo|en bodega|cantidad stock|cantidad inventario|inventario actual|stock disponible",
        "bodega|cantidad|unidades|unidad"),
    ("productos", "proveedor"): _syn("proveedor|nombre proveedor", "distribuidor|marca fabricante|fabricante"),

    ("ventas", "fecha"): _syn("fecha|fecha venta|fecha factura|fecha pedido|fecha transaccion",
                              "fecha emision|fecha de venta|fecha documento|fecha registro", "dia|periodo|mes"),
    ("ventas", "producto"): _syn("producto|nombre producto|articulo|item|plato|servicio",
                                 "descripcion|referencia|concepto|nombre articulo|nombre item|descripcion producto",
                                 "detalle|mercancia"),
    ("ventas", "cantidad"): _syn("cantidad|cantidad vendida|unidades vendidas|unidades",
                                 "cantidad producto|total unidades", "unidad"),
    ("ventas", "precio_unitario"): _syn(
        "precio unitario|valor unitario|precio unidad|valor unidad|precio",
        "precio venta|valor unit|precio por unidad|precio individual", "unitario"),
    ("ventas", "total"): _syn("total|valor total|total venta|venta total|importe|total linea|monto|ingreso",
                              "valor venta|total factura|monto total|valor neto", "subtotal|valor|venta"),
    ("ventas", "cliente"): _syn("cliente|nombre cliente|comprador|razon social|nombre del cliente",
                                "tercero|cliente nombre|nombre comprador|empresa", "nombre"),
    ("ventas", "metodo_pago"): _syn("metodo pago|forma pago|medio pago|tipo pago|metodo de pago|forma de pago",
                                    "medio de pago|pago|condicion pago", "tipo|forma"),

    ("compras", "fecha"): _syn("fecha|fecha compra|fecha factura|fecha pedido|fecha de compra",
                               "fecha emision|fecha documento|fecha registro", "dia|periodo|mes"),
    ("compras", "producto"): _syn("producto|nombre producto|articulo|item|insumo|material|mercancia",
                                  "descripcion|referencia|concepto|nombre articulo", "detalle"),
    ("compras", "cantidad"): _syn("cantidad|cantidad comprada|unidades compradas|unidades",
                                  "cantidad producto|total unidades", "unidad"),
    ("compras", "costo_unitario"): _syn(
        "costo unitario|costo|precio compra|costo unidad|valor compra|precio costo",
        "precio unitario|valor unitario|precio unidad|valor unidad|precio", "unitario"),
    ("compras", "total"): _syn("total|valor total|total compra|importe|total linea|monto",
                               "valor compra total|total factura|monto total|valor neto", "subtotal|valor|compra"),
    ("compras", "proveedor"): _syn("proveedor|nombre proveedor|supplier|vendor",
                                   "razon social|tercero|distribuidor|empresa", "nombre"),
    ("compras", "documento"): _syn("factura|numero factura|documento|remision|orden compra|comprobante",
                                   "numero documento|numero|orden|numero remision|numero comprobante", ""),

    ("cuentas_por_cobrar", "cliente"): _syn("cliente|deudor|nombre cliente|nombre deudor|razon social",
                                            "tercero|empresa|nombre del cliente", "nombre"),
    ("cuentas_por_cobrar", "valor"): _syn(
        "saldo|saldo pendiente|valor pendiente|por cobrar|deuda|valor adeudado|monto adeudado|saldo por cobrar",
        "valor|monto|balance|valor factura|total adeudado|total", "importe"),
    ("cuentas_por_cobrar", "fecha_emision"): _syn(
        "fecha emision|fecha factura|fecha expedicion|fecha de la factura|fecha elaboracion",
        "fecha documento|fecha|fecha registro", ""),
    ("cuentas_por_cobrar", "fecha_vencimiento"): _syn(
        "vencimiento|fecha vencimiento|fecha limite|fecha limite pago|vence|fecha de vencimiento",
        "fecha pago|fecha de pago|vence el|dia vencimiento", "limite"),
    ("cuentas_por_cobrar", "estado"): _syn("estado|estado pago|estado cuenta|situacion|estado cartera",
                                           "estatus|pagado|condicion", ""),

    ("movimientos_inventario", "fecha"): _syn("fecha|fecha movimiento", "fecha registro|fecha operacion", "dia"),
    ("movimientos_inventario", "producto"): _syn("producto|nombre producto|articulo|item|insumo|material",
                                                 "descripcion|referencia", "detalle|mercancia"),
    ("movimientos_inventario", "tipo_movimiento"): _syn("tipo movimiento|movimiento|tipo mov|entrada salida",
                                                        "operacion|tipo operacion|concepto|tipo", "motivo"),
    ("movimientos_inventario", "cantidad"): _syn("cantidad|unidades", "cantidad movimiento", "unidad"),

    ("clientes", "nombre"): _syn("nombre cliente|cliente|razon social|nombre del cliente|nombre completo",
                                 "nombre|empresa|tercero", "contacto"),
    ("clientes", "contacto"): _syn("contacto|persona contacto|nombre contacto|responsable|representante",
                                   "atencion|persona|encargado", ""),
    ("clientes", "telefono"): _syn("telefono|celular|movil|whatsapp|telefono celular|numero telefono|telefono contacto",
                                   "tel|fijo|contacto telefono", "numero"),
    ("clientes", "email"): _syn("email|correo|correo electronico|e mail|mail", "correo contacto|email contacto", ""),

    ("proveedores", "nombre"): _syn("nombre proveedor|proveedor|razon social|nombre del proveedor|distribuidor",
                                    "nombre|empresa|tercero", "contacto"),
    ("proveedores", "contacto"): _syn("contacto|persona contacto|nombre contacto|responsable|representante",
                                      "atencion|persona|encargado|vendedor", ""),
    ("proveedores", "telefono"): _syn("telefono|celular|movil|whatsapp|telefono celular|numero telefono",
                                      "tel|fijo|contacto telefono", "numero"),
    ("proveedores", "email"): _syn("email|correo|correo electronico|e mail|mail", "correo contacto", ""),
}

_PARTIAL_FACTOR = 0.8


def header_score(header: Any, synonyms: tuple[tuple[str, float], ...]) -> float:
    """Puntaje 0..1 de un encabezado para un rol: exacto = peso del sinonimo; contiene sus palabras = x0,8."""
    toks = _tokens(header)
    if not toks:
        return 0.0
    compact, tset = "".join(toks), set(toks)
    best = 0.0
    for phrase, weight in synonyms:
        stoks = _tokens(phrase)
        if not stoks:
            continue
        if toks == stoks or compact == "".join(stoks):
            best = max(best, weight)
        elif set(stoks) <= tset and len(toks) <= len(stoks) + 2:
            best = max(best, weight * _PARTIAL_FACTOR)
    return best


# ---------------------------------------------------------------------------
# Perfil de una columna (contenido)
# ---------------------------------------------------------------------------
_MONEY_RE = re.compile(r"^\s*[$€]?\s*-?\(?\s*[0-9][0-9.,\s]*\)?\s*(?:cop|COP|pesos)?\s*$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_PHONE_RE = re.compile(r"^\+?[0-9][0-9\s().-]{6,17}$")
_DATE_RE = re.compile(r"^\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})([T ].*)?$")


@dataclass
class ColumnProfile:
    index: int
    original: str
    clean: str
    inferred_type: str = "text"
    non_null: int = 0
    numeric_ratio: float = 0.0
    date_ratio: float = 0.0
    email_ratio: float = 0.0
    phone_ratio: float = 0.0
    sample: list[str] = field(default_factory=list)


def _ratio(values: list, test) -> float:
    return sum(1 for v in values if test(v)) / len(values) if values else 0.0


def _is_number(v: Any) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return v == v
    return isinstance(v, str) and bool(_MONEY_RE.match(v))


def _is_date(v: Any) -> bool:
    if isinstance(v, (pd.Timestamp,)) or hasattr(v, "isoformat") and not isinstance(v, str):
        return True
    return isinstance(v, str) and bool(_DATE_RE.match(v))


def profile_column(index: int, original: Any, clean: str, series: pd.Series, inferred_type: str) -> ColumnProfile:
    values = series.dropna().head(MAX_PROFILE_VALUES).tolist()
    strs = [v for v in values if isinstance(v, str)]
    return ColumnProfile(
        index=index, original=str(original), clean=clean, inferred_type=inferred_type, non_null=len(values),
        numeric_ratio=_ratio(values, _is_number),
        date_ratio=_ratio(values, _is_date),
        email_ratio=_ratio(strs, lambda v: bool(_EMAIL_RE.match(v.strip()))) if strs else 0.0,
        phone_ratio=(_ratio(values, lambda v: bool(_PHONE_RE.match(str(v).strip())) and 7 <= len(re.sub(r"\D", "", str(v))) <= 13)
                     if not strs or len(strs) == len(values) else 0.0),
        sample=[onto.clean_text(v, 40) for v in values[:5]],
    )


# Roles que exigen contenido numerico / fecha / texto.
_NEEDS_NUMBER = onto.NUMBER_ROLES
_NEEDS_DATE = onto.DATE_ROLES
_NEEDS_TEXT = frozenset({"producto_nombre", "producto", "cliente", "proveedor", "nombre", "categoria", "metodo_pago",
                         "tipo_movimiento", "estado", "contacto"})


def role_score(kind: str, role: str, p: ColumnProfile) -> tuple[float, str]:
    """(puntaje, fuente) de que la columna `p` cumpla `role` en un tipo `kind`. Fuente: 'header' o 'content'."""
    syn = SYNONYMS.get((kind, role))
    s = header_score(p.original, syn) if syn else 0.0
    source = "header"
    if s:
        # el contenido desmiente al encabezado: "fecha" con texto, "total" con nombres...
        if role in _NEEDS_NUMBER and p.non_null and p.numeric_ratio < 0.5:
            s *= 0.4
        elif role in _NEEDS_DATE and p.non_null and p.date_ratio < 0.5 and p.inferred_type != "date":
            s *= 0.4
        elif role in _NEEDS_TEXT and p.non_null and p.numeric_ratio > 0.9 and role != "estado":
            s *= 0.5
        return s, source
    # Sin pista en el encabezado: solo lo que el contenido delata solo (correo, celular, fecha)
    if p.non_null >= 2:
        if role == "email" and p.email_ratio >= 0.7:
            return 0.9, "content"
        if role == "telefono" and p.phone_ratio >= 0.8 and p.numeric_ratio >= 0.8:
            return 0.7, "content"
        if role == "fecha" and p.date_ratio >= 0.9:
            return 0.6, "content"
    return 0.0, source


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------

@dataclass
class ColumnResult:
    index: int
    original: str
    clean: str
    role: str = onto.OTHER_ROLE
    confidence: float = 0.0
    source: str = "heuristic"          # heuristic | ai | cache | user
    desc: Optional[str] = None         # descripcion corta (solo columnas 'otro' que describe el modelo)


@dataclass
class Understanding:
    kind: str
    kind_confidence: float
    columns: list[ColumnResult]
    source: str = "heuristic"          # heuristic | ai | cache | user
    signature: str = ""
    clear: bool = False                # confianza alta: no hace falta modelo ni preguntarle al usuario
    review_reasons: list[str] = field(default_factory=list)
    runner_up: Optional[str] = None
    usage: Optional[dict] = None       # tokens de la llamada al modelo (si la hubo)
    from_cache: bool = False
    ai_error: Optional[str] = None     # por que no se uso el modelo (sin clave, falla...) — solo para logs/pruebas

    @property
    def needs_review(self) -> bool:
        return bool(self.review_reasons)


@dataclass
class _KindScore:
    kind: str
    score: float
    assignment: dict[str, tuple[int, float, str]]     # rol -> (indice de columna, puntaje, fuente)
    groups_ok: int
    groups_total: int


def _assign(kind: str, profiles: list[ColumnProfile]) -> dict[str, tuple[int, float, str]]:
    """Asignacion voraz por puntaje (una columna sirve a un solo rol y un rol a una sola columna)."""
    cands = []
    for ci, p in enumerate(profiles):
        for ri, role in enumerate(onto.ROLES_BY_KIND[kind]):
            s, src = role_score(kind, role, p)
            if s >= HEADER_MATCH_MIN:
                cands.append((-s, ri, ci, role, src))
    cands.sort(key=lambda c: c[:3])
    out: dict[str, tuple[int, float, str]] = {}
    used: set[int] = set()
    for neg, _ri, ci, role, src in cands:
        if role in out or ci in used:
            continue
        out[role] = (ci, -neg, src)
        used.add(ci)
    return out


def _score_kind(kind: str, profiles: list[ColumnProfile], name_hints: set[str]) -> _KindScore:
    assignment = _assign(kind, profiles)
    groups = onto.KIND_GROUPS[kind]
    ok_scores = []
    for g in groups:
        found = [assignment[r][1] for r in g if r in assignment]
        if found:
            ok_scores.append(max(found))
    coverage = len(ok_scores) / len(groups)
    strength = sum(ok_scores) / len(ok_scores) if ok_scores else 0.0
    score = coverage * strength
    if coverage == 1.0:
        in_groups = {r for g in groups for r in g}
        extras = sum(1 for r in assignment if r not in in_groups)
        score += min(0.09, 0.03 * extras)
    if kind in name_hints and coverage >= 0.5:
        score += NAME_HINT_BONUS
    return _KindScore(kind, score, assignment, len(ok_scores), len(groups))


def _eligible(s: "_KindScore", hints: set[str]) -> bool:
    """Un tipo solo compite si la hoja tiene TODO lo que ese tipo necesita (o casi todo y el nombre de la hoja lo
    confirma: "ventas.xlsx" sin columna de cantidad sigue siendo de ventas)."""
    if s.groups_ok == s.groups_total:
        return True
    return s.kind in hints and s.groups_ok >= 2 and s.groups_ok >= s.groups_total - 1


def name_hint_kinds(*names: Optional[str]) -> set[str]:
    """Tipos que el nombre de la hoja o del archivo sugiere ("Compras octubre" -> compras)."""
    text = " " + re.sub(r"\d+", " ", " ".join(fold(n) for n in names if n)) + " "
    found = set()
    for kind, words in onto.KIND_NAME_HINTS.items():
        if any(f" {fold(w)} " in text or f" {fold(w)}s " in text for w in words):
            found.add(kind)
    return found


def understand_deterministic(
    profiles: list[ColumnProfile], *, sheet_name: Optional[str] = None, file_name: Optional[str] = None,
) -> Understanding:
    """Tipo de hoja y rol de cada columna a partir de encabezados y contenido (sin modelo)."""
    sig = onto.signature(p.original for p in profiles)
    hints = name_hint_kinds(sheet_name, file_name)
    scored = [_score_kind(k, profiles, hints) for k in onto.ROLES_BY_KIND if k != "otro"]

    # Penalizacion entre rivales: una hoja con proveedor y sin cliente no es de ventas, y al reves.
    by_kind = {s.kind: s for s in scored}
    has_client = "cliente" in by_kind["ventas"].assignment
    has_supplier = "proveedor" in by_kind["compras"].assignment and by_kind["compras"].assignment["proveedor"][1] >= 0.85
    if has_supplier and not has_client:
        by_kind["ventas"].score -= 0.3
    if has_client and not has_supplier:
        by_kind["compras"].score -= 0.3
    # Un catalogo de productos no trae fecha por fila: una hoja con producto, precio Y fecha es de movimientos
    # (ventas, compras...), no una lista de productos.
    ventas_fecha = by_kind["ventas"].assignment.get("fecha")
    if ventas_fecha is not None and ventas_fecha[1] >= 0.85:
        by_kind["productos"].score -= 0.35
    # Las cuentas por cobrar no traen producto y cantidad por fila: eso es una venta con "fecha" y "total".
    v = by_kind["ventas"].assignment
    if "producto" in v and "cantidad" in v:
        by_kind["cuentas_por_cobrar"].score -= 0.35
    scored = [s_ for s_ in scored if _eligible(s_, hints)]
    if not scored:
        return Understanding("otro", 0.3, [ColumnResult(p.index, p.original, p.clean) for p in profiles], "heuristic",
                             sig, clear=False)
    scored.sort(key=lambda s: (-s.score, s.kind))
    best = scored[0]
    second = scored[1] if len(scored) > 1 else _KindScore("otro", 0.0, {}, 0, 1)
    unrecognised = len(profiles) > 0 and best.score < 0.5

    if unrecognised:
        kind, kind_conf, runner = "otro", 0.3, best.kind if best.score > 0.2 else None
        columns = [ColumnResult(p.index, p.original, p.clean) for p in profiles]
        # sin tipo no hay roles: a lo sumo el correo/celular (que se delatan solos) se anotan como dato adicional
        reasons: list[str] = []
        return Understanding(kind, kind_conf, columns, "heuristic", sig, clear=False, review_reasons=reasons,
                             runner_up=runner)

    kind = best.kind
    margin = best.score - second.score
    kind_conf = round(min(0.98, best.score), 3)
    clear = kind_conf >= CLEAR_CONFIDENCE and margin >= CLEAR_MARGIN and best.groups_ok == best.groups_total
    columns = [ColumnResult(p.index, p.original, p.clean) for p in profiles]
    for role, (ci, s, _src) in best.assignment.items():
        columns[ci].role = role
        columns[ci].confidence = round(min(0.98, s), 3)
    reasons = []
    if not clear:
        label = onto.KIND_LABEL[kind]
        if margin < CLEAR_MARGIN and second.score >= 0.5:
            reasons.append(f"Esta hoja se parece a {label} pero también a {onto.KIND_LABEL[second.kind]}.")
        else:
            reasons.append(f"No estoy del todo seguro de que sean {label}.")
    return Understanding(kind, kind_conf, columns, "heuristic", sig, clear=clear, review_reasons=reasons,
                         runner_up=second.kind if second.score >= 0.5 else None)


# ---------------------------------------------------------------------------
# DataFrame -> perfiles
# ---------------------------------------------------------------------------

def profiles_from_frame(df: pd.DataFrame, clean_names: list[str], inferred_types: list[str]) -> list[ColumnProfile]:
    return [
        profile_column(i, col, clean_names[i], df.iloc[:, i], inferred_types[i])
        for i, col in enumerate(df.columns)
    ]


def profiles_from_names(names: list[str]) -> list[ColumnProfile]:
    """Perfiles solo con encabezados (tablas ya guardadas sin metadata): sin contenido, solo el nombre."""
    return [ColumnProfile(index=i, original=n, clean=n) for i, n in enumerate(names)]


def kind_of_names(names: list[str], table_name: Optional[str] = None) -> tuple[str, float]:
    """Tipo probable de una tabla YA guardada que no trae `kind` (plantillas, cargas viejas): solo por nombres."""
    if not names:
        return "otro", 0.0
    u = understand_deterministic(profiles_from_names(names), sheet_name=table_name)
    return u.kind, u.kind_confidence


def explain_column(c: ColumnResult, kind: str) -> str:
    """Frase para el duenio: «Vlr Compra» es lo que pagaste por cada producto."""
    if c.role == onto.OTHER_ROLE:
        return c.desc or onto.OTHER_EXPLAIN[1]
    return onto.role_titles(kind, c.role)[1]


def final_type(inferred: str, role: str, p: Optional[ColumnProfile]) -> str:
    """Tipo de dato de la columna con el rol a la vista: los roles de fecha y de numero mandan si el contenido lo
    confirma; si no, se respeta lo inferido."""
    if p is None:
        return inferred
    if role in _NEEDS_DATE and (inferred == "date" or p.date_ratio >= 0.7):
        return "date"
    if role in _NEEDS_NUMBER and inferred in ("integer", "number"):
        return inferred
    if role in _NEEDS_NUMBER and p.numeric_ratio >= 0.8:
        return "number"
    return inferred
