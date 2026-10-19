"""Modelo base del negocio ("ontologia") para la CARGA INTELIGENTE — PI0320251.

Define, en un solo lugar y sin tocar la base de datos, el vocabulario con el que el sistema entiende cualquier
hoja que suba el duenio: los TIPOS de hoja (`kind`) y los ROLES de columna de cada tipo. Lo usan el agente de
esquema (heuristico y Gemini), el emparejamiento de cargas, los hallazgos de negocio y, mas adelante, la
extraccion desde fotos/PDF/notas: todos hablan este mismo idioma.

METADATA (sin migracion de esquema). Todo vive en `org_data_tables.columns_definition` (JSONB, una lista de
columnas), compatible hacia atras: una tabla sin estos campos funciona exactamente como antes.

  columnas (una por elemento):
    {"name": "vlr_compra", "type": "number", "required": false,
     "role": "costo_unitario",            # rol confirmado (uno de ROLES_BY_KIND[kind] o "otro")
     "role_confidence": 0.93,             # 0..1
     "label": "Vlr Compra",               # encabezado ORIGINAL del archivo (para explicarselo al duenio)
     "desc": "..."}                       # (opcional) descripcion corta de una columna 'otro'
  hoja: va en la PRIMERA columna, clave "sheet" (la lista no admite un diccionario aparte sin romper a los demas
    consumidores, que iteran `c["name"]`):
    {"sheet": {"kind": "compras", "kind_confidence": 0.9, "mapping_source": "heuristic|ai|user",
               "signature": "ab12cd34ef56...", "at": "2026-10-19T14:02:11Z", "v": 1}}
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

META_VERSION = 1

KINDS: tuple[str, ...] = (
    "productos", "ventas", "compras", "cuentas_por_cobrar", "movimientos_inventario", "clientes", "proveedores",
    "otro",
)

ROLES_BY_KIND: dict[str, tuple[str, ...]] = {
    "productos": ("producto_nombre", "producto_codigo", "categoria", "costo_unitario", "precio_venta", "stock",
                  "proveedor"),
    "ventas": ("fecha", "producto", "cantidad", "precio_unitario", "total", "cliente", "metodo_pago"),
    "compras": ("fecha", "producto", "cantidad", "costo_unitario", "total", "proveedor", "documento"),
    "cuentas_por_cobrar": ("cliente", "valor", "fecha_emision", "fecha_vencimiento", "estado"),
    "movimientos_inventario": ("fecha", "producto", "tipo_movimiento", "cantidad"),
    "clientes": ("nombre", "contacto", "telefono", "email"),
    "proveedores": ("nombre", "contacto", "telefono", "email"),
    "otro": (),
}
OTHER_ROLE = "otro"

# Todos los roles posibles (union), para el esquema estructurado que se le pide al modelo.
ALL_ROLES: tuple[str, ...] = tuple(sorted({r for roles in ROLES_BY_KIND.values() for r in roles})) + (OTHER_ROLE,)

KIND_LABEL: dict[str, str] = {
    "productos": "productos", "ventas": "ventas", "compras": "compras",
    "cuentas_por_cobrar": "cuentas por cobrar", "movimientos_inventario": "movimientos de inventario",
    "clientes": "clientes", "proveedores": "proveedores", "otro": "datos",
}
# "Esto es tu lista de..." / "Estas son tus..." — frase corta para el desplegable de correccion.
KIND_CHOICE_LABEL: dict[str, str] = {
    "productos": "Lista de productos (costos, precios, existencias)",
    "ventas": "Ventas (lo que vendiste)",
    "compras": "Compras (lo que le compraste a proveedores)",
    "cuentas_por_cobrar": "Cuentas por cobrar (lo que te deben)",
    "movimientos_inventario": "Movimientos de inventario (entradas y salidas)",
    "clientes": "Lista de clientes",
    "proveedores": "Lista de proveedores",
    "otro": "Otra cosa (la guardo tal cual)",
}

# (titulo corto, explicacion en lenguaje del duenio) por (tipo, rol)
_EXPLAIN: dict[tuple[str, str], tuple[str, str]] = {
    ("productos", "producto_nombre"): ("Nombre del producto", "el nombre de cada producto"),
    ("productos", "producto_codigo"): ("Código", "el código o la referencia del producto"),
    ("productos", "categoria"): ("Categoría", "el grupo al que pertenece el producto"),
    ("productos", "costo_unitario"): ("Costo", "lo que pagaste por cada producto"),
    ("productos", "precio_venta"): ("Precio de venta", "el precio al que lo vendes"),
    ("productos", "stock"): ("Existencias", "cuántas unidades tienes disponibles"),
    ("productos", "proveedor"): ("Proveedor", "a quién le compras el producto"),
    ("ventas", "fecha"): ("Fecha de la venta", "el día en que se hizo la venta"),
    ("ventas", "producto"): ("Producto vendido", "qué producto se vendió"),
    ("ventas", "cantidad"): ("Cantidad", "cuántas unidades se vendieron"),
    ("ventas", "precio_unitario"): ("Precio por unidad", "lo que cobraste por cada unidad"),
    ("ventas", "total"): ("Total de la venta", "lo que sumó toda la venta"),
    ("ventas", "cliente"): ("Cliente", "quién compró"),
    ("ventas", "metodo_pago"): ("Forma de pago", "cómo pagó el cliente"),
    ("compras", "fecha"): ("Fecha de la compra", "el día en que hiciste la compra"),
    ("compras", "producto"): ("Producto comprado", "qué producto compraste"),
    ("compras", "cantidad"): ("Cantidad", "cuántas unidades compraste"),
    ("compras", "costo_unitario"): ("Costo por unidad", "lo que pagaste por cada unidad"),
    ("compras", "total"): ("Total de la compra", "lo que sumó toda la compra"),
    ("compras", "proveedor"): ("Proveedor", "a quién le compraste"),
    ("compras", "documento"): ("Factura o documento", "el número de la factura o la remisión"),
    ("cuentas_por_cobrar", "cliente"): ("Cliente", "quién te debe"),
    ("cuentas_por_cobrar", "valor"): ("Valor que te deben", "cuánto te debe"),
    ("cuentas_por_cobrar", "fecha_emision"): ("Fecha de la cuenta", "cuándo se generó la cuenta"),
    ("cuentas_por_cobrar", "fecha_vencimiento"): ("Fecha de vencimiento", "hasta cuándo tenía para pagarte"),
    ("cuentas_por_cobrar", "estado"): ("Estado", "si está pendiente o ya la pagaron"),
    ("movimientos_inventario", "fecha"): ("Fecha del movimiento", "el día en que entró o salió la mercancía"),
    ("movimientos_inventario", "producto"): ("Producto", "qué producto se movió"),
    ("movimientos_inventario", "tipo_movimiento"): ("Tipo de movimiento", "si la mercancía entró o salió"),
    ("movimientos_inventario", "cantidad"): ("Cantidad", "cuántas unidades se movieron"),
    ("clientes", "nombre"): ("Nombre del cliente", "el nombre del cliente"),
    ("clientes", "contacto"): ("Persona de contacto", "con quién hablar"),
    ("clientes", "telefono"): ("Teléfono", "el teléfono o el celular"),
    ("clientes", "email"): ("Correo", "el correo electrónico"),
    ("proveedores", "nombre"): ("Nombre del proveedor", "el nombre del proveedor"),
    ("proveedores", "contacto"): ("Persona de contacto", "con quién hablar"),
    ("proveedores", "telefono"): ("Teléfono", "el teléfono o el celular"),
    ("proveedores", "email"): ("Correo", "el correo electrónico"),
}
OTHER_EXPLAIN = ("Dato adicional", "un dato extra que guardo tal cual")

# Roles que se leen como fecha / numero (para fijar el tipo de la columna con el contenido a la vista).
DATE_ROLES = frozenset({"fecha", "fecha_emision", "fecha_vencimiento"})
NUMBER_ROLES = frozenset({"cantidad", "costo_unitario", "precio_venta", "stock", "precio_unitario", "total", "valor"})

# Palabras que, en el nombre de la hoja o del archivo, delatan el tipo.
KIND_NAME_HINTS: dict[str, tuple[str, ...]] = {
    "productos": ("producto", "inventario", "catalogo", "articulo", "item", "referencias", "stock", "existencias",
                  "products", "inventory"),
    "ventas": ("venta", "ventas", "factura", "pedido", "sales", "facturacion", "ingresos"),
    "compras": ("compra", "compras", "purchase", "purchases", "egresos", "gastos"),
    "cuentas_por_cobrar": ("cartera", "cobrar", "por cobrar", "deudores", "cxc", "receivable", "fiado", "fiados"),
    "movimientos_inventario": ("movimiento", "movimientos", "kardex", "entradas", "salidas"),
    "clientes": ("cliente", "clientes", "customers", "contactos"),
    "proveedores": ("proveedor", "proveedores", "suppliers", "vendors"),
}

# Reglas de un tipo: el tipo "califica" cuando cada GRUPO tiene al menos un rol presente.
KIND_GROUPS: dict[str, tuple[tuple[str, ...], ...]] = {
    "productos": (("producto_nombre",), ("costo_unitario", "stock", "precio_venta")),
    "ventas": (("fecha",), ("producto",), ("cantidad",), ("total", "precio_unitario")),
    "compras": (("fecha",), ("producto",), ("cantidad",), ("costo_unitario", "total"), ("proveedor",)),
    "cuentas_por_cobrar": (("cliente",), ("valor",), ("fecha_vencimiento", "estado", "fecha_emision")),
    "movimientos_inventario": (("fecha",), ("producto",), ("tipo_movimiento",), ("cantidad",)),
    "clientes": (("nombre",), ("contacto", "telefono", "email")),
    "proveedores": (("nombre",), ("contacto", "telefono", "email")),
}

# Que roles guardados alimentan a los hallazgos (campo del detector -> rol de la ontologia).
INSIGHT_FIELDS_PRODUCTOS = {"nombre": "producto_nombre", "costo": "costo_unitario", "precio_venta": "precio_venta",
                            "stock": "stock"}
INSIGHT_FIELDS_VENTAS = {"fecha": "fecha", "producto": "producto", "cantidad": "cantidad",
                         "precio_unitario": "precio_unitario", "total": "total", "cliente": "cliente"}


def is_kind(value: Any) -> bool:
    return isinstance(value, str) and value in KINDS


def is_valid_role(kind: Any, role: Any) -> bool:
    """Lista blanca: el rol debe pertenecer al tipo (o ser 'otro')."""
    if not is_kind(kind) or not isinstance(role, str):
        return False
    return role == OTHER_ROLE or role in ROLES_BY_KIND[kind]


def role_titles(kind: str, role: str) -> tuple[str, str]:
    """(titulo corto, explicacion) en espanol sencillo."""
    return _EXPLAIN.get((kind, role), OTHER_EXPLAIN)


def allowed_roles(kind: str) -> list[dict]:
    """Opciones del desplegable de correccion: {role, label, explain}."""
    out = [{"role": r, "label": role_titles(kind, r)[0], "explain": role_titles(kind, r)[1]}
           for r in ROLES_BY_KIND.get(kind, ())]
    out.append({"role": OTHER_ROLE, "label": OTHER_EXPLAIN[0], "explain": OTHER_EXPLAIN[1]})
    return out


# ---------------------------------------------------------------------------
# Normalizacion y firma de estructura
# ---------------------------------------------------------------------------

def fold(text: Any) -> str:
    """Encabezado -> solo [a-z0-9] separados por un espacio (sin acentos, mayusculas ni signos)."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", str(text)) if not unicodedata.combining(c))
    return re.sub(r"[^0-9a-z]+", " ", plain.casefold()).strip()


def signature(headers: Iterable[Any]) -> str:
    """Firma de la ESTRUCTURA de una hoja: hash de los encabezados normalizados, sin importar el orden.

    Dos archivos con los mismos encabezados (aunque cambien mayusculas, tildes o el orden de las columnas)
    comparten firma; asi la respuesta del modelo se reutiliza sin volver a llamarlo."""
    folded = sorted(fold(h) for h in headers)
    return hashlib.sha256("\x1f".join(folded).encode("utf-8")).hexdigest()[:24]


# ---------------------------------------------------------------------------
# Lectura/escritura de la metadata dentro de columns_definition
# ---------------------------------------------------------------------------

def parse_columns(raw: Any) -> list:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
    return raw if isinstance(raw, list) else []


def read_sheet_meta(cols: Any) -> Optional[dict]:
    """Metadata de la hoja (`kind`...) o None si la tabla es anterior a la carga inteligente o esta mal formada."""
    for c in parse_columns(cols):
        if isinstance(c, dict) and isinstance(c.get("sheet"), dict):
            meta = c["sheet"]
            kind = meta.get("kind")
            if not is_kind(kind):
                return None
            conf = meta.get("kind_confidence")
            return {
                "kind": kind,
                "kind_confidence": float(conf) if isinstance(conf, (int, float)) and not isinstance(conf, bool) else 0.0,
                "mapping_source": meta.get("mapping_source") if meta.get("mapping_source") in ("heuristic", "ai", "user")
                else "heuristic",
                "signature": meta.get("signature") if isinstance(meta.get("signature"), str) else None,
                "at": meta.get("at") if isinstance(meta.get("at"), str) else None,
            }
        break   # solo la primera columna lleva la metadata de la hoja
    return None


def column_roles(cols: Any) -> dict[str, dict]:
    """{nombre de columna: {"role", "confidence", "label"}} de las columnas con un rol valido guardado.

    El rol se valida contra el `kind` de la hoja: uno fuera de la lista blanca se ignora (no confiar en lo que
    haya en la BD)."""
    cols = parse_columns(cols)
    meta = read_sheet_meta(cols)
    if meta is None:
        return {}
    out: dict[str, dict] = {}
    for c in cols:
        if not isinstance(c, dict) or not isinstance(c.get("name"), str):
            continue
        role = c.get("role")
        if isinstance(role, str) and is_valid_role(meta["kind"], role):
            conf = c.get("role_confidence")
            out[c["name"]] = {
                "role": role,
                "confidence": float(conf) if isinstance(conf, (int, float)) and not isinstance(conf, bool) else 0.0,
                "label": c.get("label") if isinstance(c.get("label"), str) else c["name"],
            }
    return out


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_sheet_meta(kind: str, kind_confidence: float, mapping_source: str, sig: Optional[str]) -> dict:
    return {
        "kind": kind,
        "kind_confidence": round(max(0.0, min(1.0, float(kind_confidence))), 3),
        "mapping_source": mapping_source,
        "signature": sig,
        "at": now_iso(),
        "v": META_VERSION,
    }


def with_sheet_meta(cols: list, meta: dict) -> list:
    """Copia de `cols` con la metadata de la hoja en la primera columna (y en ninguna otra)."""
    out: list = []
    placed = False
    for c in parse_columns(cols):
        if isinstance(c, dict):
            c = {k: v for k, v in c.items() if k != "sheet"}
            if not placed:
                c["sheet"] = meta
                placed = True
        out.append(c)
    return out


def clean_text(value: Any, limit: int) -> str:
    """Texto de usuario -> una linea sin caracteres de control, acotado (para guardarlo o mandarlo al modelo)."""
    text = re.sub(r"[\x00-\x1f\x7f-\x9f  ]+", " ", str(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]
