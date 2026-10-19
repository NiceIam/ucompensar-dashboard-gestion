"""Schema Agent — Agente inteligente para analisis de CSVs y gestion de schema.

Analiza archivos subidos, sugiere/crea tablas, mapea columnas y carga datos
en la base de datos de la organizacion. Funciona sin LLM externo.
"""

import json
import logging
import math
import re
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import HTTPException, status

from app.database import get_org_pool
from app.services import data_query_engine as engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mapeo de nombres comunes en español a tipos de datos
# ---------------------------------------------------------------------------
COLUMN_TYPE_HINTS: dict[str, str] = {
    # Fechas
    "fecha": "date", "date": "date", "dia": "date", "periodo": "date",
    "created_at": "date", "updated_at": "date", "vencimiento": "date",
    # Numeros
    "precio": "number", "costo": "number", "valor": "number", "total": "number",
    "subtotal": "number", "iva": "number", "descuento": "number",
    "cantidad": "integer", "stock": "integer", "inventario": "integer",
    "duracion": "number", "horas": "number", "monto": "number",
    "precio_compra": "number", "precio_venta": "number", "precio_base": "number",
    "precio_unitario": "number", "rows_extracted": "integer", "rows_loaded": "integer",
    # Booleanos
    "disponible": "boolean", "activo": "boolean", "pagado": "boolean",
    # Texto (default)
    "nombre": "text", "descripcion": "text", "email": "text", "telefono": "text",
    "direccion": "text", "ciudad": "text", "categoria": "text", "estado": "text",
    "cliente": "text", "proveedor": "text", "producto": "text", "servicio": "text",
    "numero": "text", "codigo": "text", "contacto": "text", "empresa": "text",
}

# Palabras clave para sugerir nombres de tabla
TABLE_NAME_KEYWORDS: dict[str, list[str]] = {
    "productos": ["producto", "precio_compra", "precio_venta", "stock", "codigo", "ean", "sku"],
    "ventas": ["venta", "precio_unitario", "metodo_pago", "factura", "receipt"],
    "clientes": ["cliente", "empresa", "telefono", "email", "ciudad", "contacto"],
    "proveedores": ["proveedor", "suministr", "supply", "vendor"],
    "servicios": ["servicio", "duracion", "precio_base", "tarifa"],
    "cotizaciones": ["cotizacion", "quote", "presupuesto", "estado"],
    "facturas": ["factura", "invoice", "subtotal", "iva", "total", "estado_pago"],
    "inventario_movimientos": ["movimiento", "tipo_movimiento", "entrada", "salida"],
    "menu_items": ["menu", "plato", "disponible", "costo"],
    "pedidos": ["pedido", "mesa", "mesero", "order"],
    "empleados": ["empleado", "cargo", "salario", "departamento"],
}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _clean_column_names(columns) -> list[str]:
    """Normaliza encabezados (str, minusculas, '_') y desduplica los que colisionan.

    'Nombre' y 'nombre' limpian al mismo nombre: el segundo pasa a 'nombre_2'.
    analyze_csv (lo que declara la tabla) y load_csv_to_table (las claves de cada
    fila) usan esta misma funcion para que ambos lados coincidan.
    """
    cleaned: list[str] = []
    used: set[str] = set()
    for col in columns:
        base = str(col).strip().lower().replace(" ", "_")
        name, n = base, 2
        while name in used:
            name = f"{base}_{n}"
            n += 1
        used.add(name)
        cleaned.append(name)
    return cleaned


def _parse_uuid(value: str) -> Optional[uuid.UUID]:
    """UUID o None si el id viene mal formado (para responder 'no encontrada', no 500)."""
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def _json_safe_value(val):
    """Convierte una celda a un valor serializable en jsonb; None = omitir la clave."""
    # JSON anidado (Excel/JSON con listas o dicts): pd.isna devolveria un array
    if isinstance(val, (list, dict, tuple, set)):
        return json.dumps(val, ensure_ascii=False, default=str)
    if pd.isna(val):
        return None
    # bool antes que int (bool es subclase de int); los de numpy no lo son
    if isinstance(val, (bool, np.bool_)):
        return bool(val)
    if isinstance(val, (int, np.integer)):
        return int(val)
    if isinstance(val, (float, np.floating)):
        # inf/-inf generarian 'Infinity', que jsonb rechaza: se tratan como nulos
        return float(val) if math.isfinite(val) else None
    return str(val)


# ---------------------------------------------------------------------------
# Rango de fechas por columna (para el catalogo del chat)
# ---------------------------------------------------------------------------

async def _refresh_date_ranges(conn, table_uuid, cols: list, names: Optional[set] = None) -> tuple[list, bool]:
    """Recalcula el rango (min, max) de las columnas de fecha de una tabla y lo anota en columns_definition
    (clave extra `range`: ["AAAA-MM-DD", "AAAA-MM-DD"]; las tablas sin ella siguen funcionando igual).

    Se calcula UNA vez, al cargar datos, con el motor de consultas del chat (mismo parseo de fechas que los
    filtros) sobre TODA la tabla: equivale a min de minimos / max de maximos y ademas corrige tablas viejas sin
    rango o con uno desactualizado. `names` limita las columnas (None = todas las de fecha entre las primeras
    engine.RANGE_MAX_COLUMNS). Sin fechas legibles la columna queda sin `range`. Corre en un savepoint y NUNCA
    lanza: si falla, la carga sigue sin rango. Devuelve (columns_definition nuevo, si cambio algo)."""
    wanted: list[str] = []
    for c in cols[: engine.RANGE_MAX_COLUMNS]:
        name = c.get("name") if isinstance(c, dict) else None
        if isinstance(name, str) and engine.is_date_type(c.get("type")) and name not in wanted:
            if names is None or name in names:
                wanted.append(name)
    if not wanted:
        return cols, False
    try:
        async with conn.transaction():
            ranges = await engine.date_ranges(conn, table_uuid, wanted)
    except Exception as exc:
        # Sin el mensaje: un error de la BD puede citar valores de celdas.
        logger.warning("No se pudo calcular el rango de fechas de la tabla %s: %s", table_uuid, type(exc).__name__)
        return cols, False
    new_cols, changed, done = [], False, set()
    for c in cols:
        name = c.get("name") if isinstance(c, dict) else None
        if name in wanted and name not in done:
            done.add(name)
            c = dict(c)
            found = ranges.get(name)
            rng = [found[0].isoformat(), found[1].isoformat()] if found else None
            if c.get("range") != rng:
                changed = True
                if rng:
                    c["range"] = rng
                else:
                    c.pop("range", None)
        new_cols.append(c)
    return new_cols, changed


def _parse_columns_definition(raw) -> list:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
    return raw if isinstance(raw, list) else []


async def backfill_date_ranges(
    org_id: str, *, dry_run: bool = True, refresh: bool = False, pool=None
) -> list[dict]:
    """Mantenimiento: calcula y guarda el rango de fechas de las tablas de UNA org cargadas antes de que existiera.

    Por defecto solo mira columnas de fecha SIN rango; refresh=True recalcula todas (p. ej. tras borrar filas o al
    cambiar el año, que mueve la ventana de años de 2 digitos). dry_run=True (por defecto) no escribe nada.
    Correrlo sin cargas de archivos en curso. Devuelve, por tabla con algo que calcular:
    {"table", "rows", "ranges": {columna: [min, max]}, "changed", "applied"}. Ver scripts/backfill_date_ranges.py."""
    pool = pool or await get_org_pool(org_id)
    report = []
    async with pool.acquire() as conn:
        tables = await conn.fetch(
            "SELECT id, table_name, display_name, row_count, columns_definition FROM org_data_tables"
        )
        for t in sorted(tables, key=lambda r: r["table_name"]):
            cols = _parse_columns_definition(t["columns_definition"])
            names = {
                c["name"] for c in cols[: engine.RANGE_MAX_COLUMNS]
                if isinstance(c, dict) and isinstance(c.get("name"), str) and engine.is_date_type(c.get("type"))
                and (refresh or "range" not in c)
            }
            if not names or not (t["row_count"] or 0):
                continue
            async with conn.transaction():
                new_cols, changed = await _refresh_date_ranges(conn, t["id"], cols, names)
                if changed and not dry_run:
                    await conn.execute(
                        "UPDATE org_data_tables SET columns_definition = $1::jsonb WHERE id = $2",
                        json.dumps(new_cols), t["id"],
                    )
            report.append({
                "table": t["table_name"],
                "rows": t["row_count"],
                "ranges": {c["name"]: c["range"] for c in new_cols if c.get("name") in names and c.get("range")},
                "changed": changed,
                "applied": bool(changed and not dry_run),
            })
    return report


# ---------------------------------------------------------------------------
# Analisis de CSV
# ---------------------------------------------------------------------------

def analyze_csv(df: pd.DataFrame) -> dict:
    """Analiza un DataFrame y retorna metadata completa de las columnas."""
    columns_analysis = []
    clean_names = _clean_column_names(df.columns)
    for i, col in enumerate(df.columns):
        col_clean = clean_names[i]
        # iloc (no df[col]): con encabezados repetidos df[col] devolveria un DataFrame
        raw_series = df.iloc[:, i]
        series = raw_series.dropna()

        # Inferir tipo
        inferred_type = _infer_column_type(col_clean, series)

        # Valores unicos y muestras
        # list/dict (JSON anidado) no son hashables: se cuentan por su texto JSON
        unique_count = series.map(
            lambda v: json.dumps(v, default=str) if isinstance(v, (list, dict, tuple, set)) else v
        ).nunique()
        sample_values = series.head(5).astype(str).tolist()

        columns_analysis.append({
            "original_name": str(col),
            "clean_name": col_clean,
            "inferred_type": inferred_type,
            "non_null_count": int(len(series)),
            "total_count": int(len(df)),
            "null_count": int(raw_series.isna().sum()),
            "unique_count": int(unique_count),
            "sample_values": sample_values,
            "is_required": bool(raw_series.isna().sum() == 0),
        })

    # Sugerir nombre de tabla
    suggested_table = _suggest_table_name(df.columns.tolist())

    return {
        "row_count": len(df),
        "column_count": len(df.columns),
        "columns": columns_analysis,
        "suggested_table_name": suggested_table,
        "suggested_display_name": suggested_table.replace("_", " ").title(),
    }


# Raices que ademas pueden ir pegadas a otra palabra ('fechanacimiento',
# 'precioventa', camelCase de JSON). Lista corta a proposito: el prefijo libre
# daria falsos positivos clinicos, y cada raiz excluye los suyos (valoracion,
# periodontitis, totalidad...).
_CONCAT_HINT_ROOTS: dict[str, re.Pattern] = {
    "fecha": re.compile(r"fecha"),
    "precio": re.compile(r"precio(?!s[oa])"),
    "valor": re.compile(r"valor(?![ai])"),
    "costo": re.compile(r"costo(?!s[oa])"),
    "total": re.compile(r"total(?!id|m)"),
    "cantidad": re.compile(r"cantidad"),
    "periodo": re.compile(r"periodo(?!n)"),
}


def _token_matches_hint(token: str, key: str) -> bool:
    """Token completo del nombre vs. palabra del hint: tolera plural ('precios',
    'totales') y sufijo numerico ('fecha1'); NO subcadenas arbitrarias."""
    if re.fullmatch(rf"{re.escape(key)}(?:s|es)?\d*", token):
        return True
    root = _CONCAT_HINT_ROOTS.get(key)
    return bool(root and root.match(token))


def _infer_column_type(col_name: str, series: pd.Series) -> str:
    """Infiere el tipo de dato basado en nombre y valores."""
    # 1. Buscar por nombre. Por palabra completa, no por subcadena: 'dia' no debe
    # matchear 'diagnostico' ni 'iva' 'narrativa' (dominio clinico).
    name_tokens = [t for t in re.split(r"[\W_]+", col_name) if t]
    for hint_key, hint_type in COLUMN_TYPE_HINTS.items():
        key_tokens = hint_key.split("_")
        n = len(key_tokens)
        if any(
            all(_token_matches_hint(t, k) for t, k in zip(name_tokens[i:i + n], key_tokens))
            for i in range(len(name_tokens) - n + 1)
        ):
            return hint_type

    # 2. Buscar por contenido
    if len(series) == 0:
        return "text"

    # bool y datetime nativos antes de to_numeric, que los convierte a enteros
    if pd.api.types.is_bool_dtype(series) or series.map(lambda v: isinstance(v, (bool, np.bool_))).all():
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"

    # Intentar numerico
    try:
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().sum() > len(series) * 0.8:
            if (numeric.dropna() == numeric.dropna().astype(int)).all():
                return "integer"
            return "number"
    except (ValueError, TypeError):
        pass

    # Intentar fecha
    try:
        dates = pd.to_datetime(series, errors="coerce", dayfirst=True)
        if dates.notna().sum() > len(series) * 0.7:
            return "date"
    except (ValueError, TypeError):
        pass

    # Booleano
    bool_vals = {"true", "false", "si", "no", "1", "0", "yes"}
    if series.astype(str).str.lower().isin(bool_vals).sum() > len(series) * 0.8:
        return "boolean"

    return "text"


def _suggest_table_name(columns: list[str]) -> str:
    """Sugiere un nombre de tabla basado en las columnas del CSV."""
    cols_lower = [str(c).strip().lower().replace(" ", "_") for c in columns]
    cols_text = " ".join(cols_lower)

    best_match = "datos_importados"
    best_score = 0

    for table_name, keywords in TABLE_NAME_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in cols_text)
        if score > best_score:
            best_score = score
            best_match = table_name

    return best_match


# ---------------------------------------------------------------------------
# Buscar tabla existente compatible
# ---------------------------------------------------------------------------

async def find_matching_table(org_id: str, csv_columns: list[dict]) -> Optional[dict]:
    """Busca una tabla existente que sea compatible con las columnas del CSV."""
    pool = await get_org_pool(org_id)
    async with pool.acquire() as conn:
        tables = await conn.fetch(
            "SELECT id, table_name, display_name, columns_definition FROM org_data_tables"
        )

    csv_col_names = {c["clean_name"] for c in csv_columns}

    best_match = None
    best_score = 0

    for table in tables:
        cols_def = table["columns_definition"]
        if isinstance(cols_def, str):
            cols_def = json.loads(cols_def)

        table_col_names = {c["name"] for c in cols_def}

        # Calcular coincidencia
        if not table_col_names:
            continue

        intersection = csv_col_names & table_col_names
        score = len(intersection) / max(len(table_col_names), 1)

        # Tambien checar similitud fuzzy (los pares identicos tambien suman, por lo
        # que las coincidencias exactas pesan doble: ya hay tests que lo fijan)
        for csv_col in csv_col_names:
            for table_col in table_col_names:
                sim = SequenceMatcher(None, csv_col, table_col).ratio()
                if sim > 0.8:
                    score += 0.1

        # Se compara SIN tope: el bonus desempata (una tabla de 3 columnas que
        # coincide exacto le gana a una de 4 con las mismas 3). El tope de 1.0
        # se aplica solo al score que se reporta.
        if score > best_score and score >= 0.3:
            best_score = score
            missing_cols = csv_col_names - table_col_names
            extra_cols = table_col_names - csv_col_names
            best_match = {
                "table_id": str(table["id"]),
                "table_name": table["table_name"],
                "display_name": table["display_name"],
                "match_score": min(round(score, 2), 1.0),
                "matched_columns": list(intersection),
                "missing_in_table": list(missing_cols),
                "extra_in_table": list(extra_cols),
                "columns_definition": cols_def,
            }

    return best_match


# ---------------------------------------------------------------------------
# Crear tabla nueva
# ---------------------------------------------------------------------------

async def create_table(
    org_id: str,
    table_name: str,
    display_name: str,
    columns: list[dict],
) -> dict:
    """Crea una nueva tabla en org_data_tables."""
    pool = await get_org_pool(org_id)
    async with pool.acquire() as conn:
        # INSERT atomico con ON CONFLICT en vez de SELECT-then-INSERT: evita
        # la condicion de carrera de crear la misma tabla dos veces si dos
        # requests llegan casi al mismo tiempo (se apoya en la restriccion
        # UNIQUE de table_name).
        row = await conn.fetchrow(
            """
            INSERT INTO org_data_tables (table_name, display_name, columns_definition, row_count)
            VALUES ($1, $2, $3::jsonb, 0)
            ON CONFLICT (table_name) DO NOTHING
            RETURNING id, table_name, display_name, columns_definition, row_count
            """,
            table_name,
            display_name,
            json.dumps(columns),
        )

        if not row:
            existing_id = await conn.fetchval(
                "SELECT id FROM org_data_tables WHERE table_name = $1", table_name
            )
            return {"error": f"La tabla '{table_name}' ya existe", "table_id": str(existing_id)}

    logger.info(f"Tabla creada: {table_name} en org {org_id}")
    return {
        "table_id": str(row["id"]),
        "table_name": row["table_name"],
        "display_name": row["display_name"],
        "columns": columns,
        "row_count": 0,
    }


# ---------------------------------------------------------------------------
# Modificar tabla existente (agregar columnas)
# ---------------------------------------------------------------------------

async def modify_table(
    org_id: str,
    table_id: str,
    add_columns: list[dict] = None,
    new_display_name: str = None,
) -> dict:
    """Modifica una tabla existente — agrega columnas o cambia nombre."""
    table_uuid = _parse_uuid(table_id)
    if table_uuid is None:
        return {"error": "Tabla no encontrada"}

    pool = await get_org_pool(org_id)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, table_name, display_name, columns_definition FROM org_data_tables WHERE id = $1",
            table_uuid,
        )
        if not row:
            return {"error": "Tabla no encontrada"}

        current_cols = row["columns_definition"]
        if isinstance(current_cols, str):
            current_cols = json.loads(current_cols)

        existing_names = {c["name"] for c in current_cols}

        columns_added = 0
        if add_columns:
            for col in add_columns:
                if col["name"] not in existing_names:
                    current_cols.append(col)
                    existing_names.add(col["name"])
                    columns_added += 1

        # Una columna de fecha recien declarada puede tener ya valores en las filas existentes: se anota su rango.
        added_dates = {c["name"] for c in (add_columns or []) if engine.is_date_type(c.get("type"))}
        if columns_added and added_dates:
            current_cols, _ = await _refresh_date_ranges(conn, table_uuid, current_cols, added_dates)

        updates = {"columns_definition": json.dumps(current_cols)}
        if new_display_name:
            updates["display_name"] = new_display_name

        await conn.execute(
            """
            UPDATE org_data_tables
            SET columns_definition = $1::jsonb, display_name = COALESCE($2, display_name)
            WHERE id = $3
            """,
            json.dumps(current_cols),
            new_display_name,
            table_uuid,
        )

    return {
        "table_id": table_id,
        "table_name": row["table_name"],
        "display_name": new_display_name or row["display_name"],
        "columns": current_cols,
        "columns_added": columns_added,
    }


# ---------------------------------------------------------------------------
# Eliminar tabla
# ---------------------------------------------------------------------------

async def _drop_table_record(org_id: str, table_id: str) -> None:
    """Borra el registro de una tabla recien creada cuya carga fallo (best effort)."""
    try:
        pool = await get_org_pool(org_id)
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM org_data_tables WHERE id = $1", uuid.UUID(table_id))
    except Exception:
        logger.exception(f"No se pudo limpiar la tabla huerfana {table_id} (org: {org_id})")


async def delete_table(org_id: str, table_id: str) -> dict:
    """Elimina una tabla y todos sus datos."""
    table_uuid = _parse_uuid(table_id)
    if table_uuid is None:
        return {"error": "Tabla no encontrada"}

    pool = await get_org_pool(org_id)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT table_name, display_name FROM org_data_tables WHERE id = $1",
            table_uuid,
        )
        if not row:
            return {"error": "Tabla no encontrada"}

        # Los 3 DELETE van en una transaccion: todo o nada, sin dejar la tabla
        # con filas borradas y row_count obsoleto si uno falla.
        async with conn.transaction():
            # Eliminar datos. Postgres no permite funciones de agregacion (count(*))
            # dentro de RETURNING -- se cuenta en Python sobre las filas devueltas.
            deleted_ids = await conn.fetch(
                "DELETE FROM org_data_rows WHERE table_id = $1 RETURNING id",
                table_uuid,
            )
            deleted_rows = len(deleted_ids)

            # Eliminar data_records legacy
            await conn.execute(
                "DELETE FROM data_records WHERE table_name = $1", row["table_name"]
            )

            # Eliminar tabla
            await conn.execute("DELETE FROM org_data_tables WHERE id = $1", table_uuid)

    logger.info(f"Tabla eliminada: {row['table_name']} ({deleted_rows} filas)")
    return {
        "table_name": row["table_name"],
        "display_name": row["display_name"],
        "rows_deleted": deleted_rows,
    }


# ---------------------------------------------------------------------------
# Cargar datos de CSV a tabla
# ---------------------------------------------------------------------------

def frame_rows(df: pd.DataFrame) -> list[dict]:
    """Filas de un DataFrame tal como se guardan en org_data_rows: columnas con nombre limpio (desduplicado igual
    que analyze_csv) y solo las celdas con valor (None = se omite la clave).

    Series.tolist() devuelve tipos nativos de Python y respeta el dtype de cada columna (iterrows() subiria
    enteros a float cuando hay una columna decimal al lado)."""
    df = df.copy()
    df.columns = _clean_column_names(df.columns)
    col_values = {col: df[col].tolist() for col in df.columns}
    rows = []
    for i in range(len(df)):
        row_data = {}
        for col in df.columns:
            val = _json_safe_value(col_values[col][i])
            if val is not None:
                row_data[col] = val
        rows.append(row_data)
    return rows


async def load_csv_to_table(
    df: pd.DataFrame,
    org_id: str,
    table_id: str,
    column_mapping: dict[str, str] = None,
) -> dict:
    """Carga datos de un DataFrame a una tabla especifica.

    Args:
        df: DataFrame con los datos
        org_id: ID de la organizacion
        table_id: ID de la tabla destino
        column_mapping: Mapeo de columnas CSV → columnas tabla (opcional)
    """
    table_uuid = _parse_uuid(table_id)
    if table_uuid is None:
        return {"error": "Tabla no encontrada"}

    pool = await get_org_pool(org_id)

    async with pool.acquire() as conn:
        table_row = await conn.fetchrow(
            "SELECT id, table_name, columns_definition FROM org_data_tables WHERE id = $1",
            table_uuid,
        )
        if not table_row:
            return {"error": "Tabla no encontrada"}

        table_name = table_row["table_name"]

        # Aplicar mapeo de columnas si existe
        if column_mapping:
            df = df.rename(columns=column_mapping)

        # Filas ya limpias (nombres desduplicados igual que en analyze_csv, valores serializables)
        row_dicts = frame_rows(df)

        # Insertar filas. Envuelto en una transaccion: si una fila falla a
        # mitad de archivo, se revierte todo en vez de dejar datos parciales.
        inserted = 0
        async with conn.transaction():
            for row_data in row_dicts:
                await conn.execute(
                    "INSERT INTO org_data_rows (table_id, data) VALUES ($1, $2::jsonb)",
                    table_uuid,
                    json.dumps(row_data, ensure_ascii=False),
                )

                # Legacy data_records
                await conn.execute(
                    "INSERT INTO data_records (table_name, data) VALUES ($1, $2::jsonb)",
                    table_name,
                    json.dumps(row_data, ensure_ascii=False),
                )
                inserted += 1

            # Marca de esta carga: las filas insertadas en UNA transaccion comparten created_at (NOW() es el
            # inicio de la transaccion). Sirve para deshacer solo esta carga (undo_load).
            loaded_at = await conn.fetchval(
                "SELECT max(created_at) FROM org_data_rows WHERE table_id = $1", table_uuid,
            ) if inserted else None
            # Actualizar row_count
            total = await conn.fetchval(
                "SELECT count(*) FROM org_data_rows WHERE table_id = $1",
                table_uuid,
            )
            await conn.execute(
                "UPDATE org_data_tables SET row_count = $1 WHERE id = $2",
                total, table_uuid,
            )

            # Rango de fechas por columna (se calcula aqui, una vez; el chat solo lo lee). Misma transaccion:
            # filas y rango quedan o no quedan juntos.
            cols_def = _parse_columns_definition(table_row["columns_definition"])
            new_cols, changed = await _refresh_date_ranges(conn, table_uuid, cols_def)
            if changed:
                await conn.execute(
                    "UPDATE org_data_tables SET columns_definition = $1::jsonb WHERE id = $2",
                    json.dumps(new_cols), table_uuid,
                )

    logger.info(f"Cargados {inserted} registros en {table_name} (org: {org_id})")
    return {
        "table_id": table_id,
        "table_name": table_name,
        "rows_inserted": inserted,
        "total_rows": total,
        "loaded_at": loaded_at.isoformat() if hasattr(loaded_at, "isoformat") else None,
    }


async def undo_load(org_id: str, table_id: str, loaded_at: str) -> dict:
    """Deshace UNA carga: borra solo las filas insertadas con la marca `loaded_at` (la devuelve load_csv_to_table) y
    deja el conteo y el rango de fechas de la tabla como si no hubiera pasado. No toca las demas filas."""
    table_uuid = _parse_uuid(table_id)
    if table_uuid is None:
        return {"error": "Tabla no encontrada"}
    try:
        stamp = datetime.fromisoformat(str(loaded_at))
    except ValueError:
        return {"error": "No reconozco esa carga."}
    if stamp.tzinfo is None:
        return {"error": "No reconozco esa carga."}
    pool = await get_org_pool(org_id)
    async with pool.acquire() as conn:
        table_row = await conn.fetchrow(
            "SELECT id, table_name, columns_definition FROM org_data_tables WHERE id = $1", table_uuid,
        )
        if not table_row:
            return {"error": "Tabla no encontrada"}
        async with conn.transaction():
            gone = await conn.fetch(
                "DELETE FROM org_data_rows WHERE table_id = $1 AND created_at = $2 RETURNING id", table_uuid, stamp,
            )
            await conn.execute(
                "DELETE FROM data_records WHERE table_name = $1 AND created_at = $2", table_row["table_name"], stamp,
            )
            total = await conn.fetchval("SELECT count(*) FROM org_data_rows WHERE table_id = $1", table_uuid)
            await conn.execute("UPDATE org_data_tables SET row_count = $1 WHERE id = $2", total, table_uuid)
            if gone:
                cols_def = _parse_columns_definition(table_row["columns_definition"])
                new_cols, changed = await _refresh_date_ranges(conn, table_uuid, cols_def)
                if changed:
                    await conn.execute(
                        "UPDATE org_data_tables SET columns_definition = $1::jsonb WHERE id = $2",
                        json.dumps(new_cols), table_uuid,
                    )
    return {"table_id": table_id, "rows_deleted": len(gone), "total_rows": total}


# ---------------------------------------------------------------------------
# Pipeline completo: analizar + decidir + cargar
# ---------------------------------------------------------------------------

async def smart_upload(
    df: pd.DataFrame,
    org_id: str,
    filename: str,
    *,
    sheet_name: Optional[str] = None,
    understanding=None,
) -> dict:
    """Pipeline completo: entiende la hoja, decide el destino SIN mezclar en silencio, carga los datos.

    1. Entiende el tipo de hoja (`kind`) y el rol de cada columna (cache de firma -> determinista; si recibe
       `understanding` ya resuelto, p. ej. con Gemini, usa ese).
    2. Una carga se SUMA a una hoja existente solo si el tipo coincide Y las columnas se parecen >= 80 %
       (o es una plantilla vacia compatible). Si hay duda o no coincide, crea una hoja NUEVA con nombre derivado
       del archivo/hoja: nunca mezcla datos distintos.
    3. Carga y deja los roles en la metadata (columns_definition).
    """
    # Sin columnas (JSON '[]', Excel en blanco) no hay nada que cargar: rechazar
    # antes de crear una tabla fantasma.
    if len(df.columns) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El archivo no tiene columnas (encabezados). Verifique que no este vacio.",
        )

    # import perezoso: intake_service importa este modulo
    from app.services import intake_service as intake
    from app.services import schema_ai_service as ai_service

    prep = intake.prepare_sheet(df, enforce_limits=False)
    analysis = prep.analysis
    org_tables = await intake.load_org_tables(org_id)
    und = understanding or await ai_service.understand(
        org_id, prep.profiles, sheet_name=sheet_name, file_name=filename, org_tables=org_tables, use_ai=False,
    )
    cand = intake.best_candidate(und, [intake.view_of_table(t) for t in org_tables])
    decision = intake.decide(und, cand)
    actions: list[dict] = []

    if decision == "append" and cand is not None:
        table_row = next(t for t in org_tables if str(t["id"]) == cand.table.table_id)
        res = await intake.append_sheet(org_id, prep, und, table_row, guard_duplicates=False)
        actions.append({"action": "load_data",
                        "detail": f"Cargados {res['rows_inserted']} registros en '{res['table_name']}'"})
        return {
            "status": "loaded_to_existing",
            "table_name": res["table_name"],
            "table_id": res["table_id"],
            "match_score": round(cand.similarity, 2),
            "kind": und.kind,
            "rows_inserted": res["rows_inserted"],
            "total_rows": res["total_rows"],
            "actions": actions,
            "analysis": analysis,
        }

    # --- Crear tabla nueva (tambien cuando hay duda: no se mezcla en silencio) ---
    display = intake.derive_display_name(und.kind, filename, sheet_name, bool(sheet_name))
    res = await intake.create_sheet(org_id, prep, und, display)
    actions.append({"action": "create_table",
                    "detail": f"Tabla '{display}' creada con {len(prep.profiles)} columnas"})
    actions.append({"action": "load_data", "detail": f"Cargados {res['rows_inserted']} registros"})
    return {
        "status": "created_new_table",
        "table_name": res["table_name"],
        "table_id": res["table_id"],
        "kind": und.kind,
        "rows_inserted": res["rows_inserted"],
        "total_rows": res["total_rows"],
        "actions": actions,
        "analysis": analysis,
    }
