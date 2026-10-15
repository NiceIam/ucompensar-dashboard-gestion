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

        # Limpiar nombres de columnas (desduplicados igual que en analyze_csv)
        df.columns = _clean_column_names(df.columns)

        # Valores por columna: Series.tolist() devuelve tipos nativos de Python y
        # respeta el dtype de cada columna (iterrows() subiria enteros a float
        # cuando hay una columna decimal al lado).
        col_values = {col: df[col].tolist() for col in df.columns}

        # Insertar filas. Envuelto en una transaccion: si una fila falla a
        # mitad de archivo, se revierte todo en vez de dejar datos parciales.
        inserted = 0
        async with conn.transaction():
            for i in range(len(df)):
                row_data = {}
                for col in df.columns:
                    val = _json_safe_value(col_values[col][i])
                    if val is not None:
                        row_data[col] = val

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

            # Actualizar row_count
            total = await conn.fetchval(
                "SELECT count(*) FROM org_data_rows WHERE table_id = $1",
                table_uuid,
            )
            await conn.execute(
                "UPDATE org_data_tables SET row_count = $1 WHERE id = $2",
                total, table_uuid,
            )

    logger.info(f"Cargados {inserted} registros en {table_name} (org: {org_id})")
    return {
        "table_id": table_id,
        "table_name": table_name,
        "rows_inserted": inserted,
        "total_rows": total,
    }


# ---------------------------------------------------------------------------
# Pipeline completo: analizar + decidir + cargar
# ---------------------------------------------------------------------------

async def smart_upload(
    df: pd.DataFrame,
    org_id: str,
    filename: str,
) -> dict:
    """Pipeline completo: analiza CSV, decide destino, carga datos.

    1. Analiza columnas del CSV
    2. Busca tabla existente compatible
    3. Si encuentra match >= 50%: carga en tabla existente (agrega columnas faltantes)
    4. Si no: crea tabla nueva y carga
    """
    # Sin columnas (JSON '[]', Excel en blanco) no hay nada que cargar: rechazar
    # antes de crear una tabla fantasma.
    if len(df.columns) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El archivo no tiene columnas (encabezados). Verifique que no este vacio.",
        )

    analysis = analyze_csv(df)
    matching_table = await find_matching_table(org_id, analysis["columns"])

    actions = []

    if matching_table and matching_table["match_score"] >= 0.5:
        # --- Usar tabla existente ---
        table_id = matching_table["table_id"]
        table_name = matching_table["table_name"]

        # Agregar columnas faltantes si las hay
        if matching_table["missing_in_table"]:
            new_cols = [
                {
                    "name": col_name,
                    "type": next(
                        (c["inferred_type"] for c in analysis["columns"] if c["clean_name"] == col_name),
                        "text"
                    ),
                }
                for col_name in matching_table["missing_in_table"]
            ]
            modify_result = await modify_table(org_id, table_id, add_columns=new_cols)
            actions.append({
                "action": "modify_table",
                "detail": f"Agregadas {len(new_cols)} columnas a '{table_name}': {', '.join(matching_table['missing_in_table'])}",
            })

        # Cargar datos
        load_result = await load_csv_to_table(df, org_id, table_id)
        actions.append({
            "action": "load_data",
            "detail": f"Cargados {load_result['rows_inserted']} registros en '{table_name}'",
        })

        return {
            "status": "loaded_to_existing",
            "table_name": table_name,
            "table_id": table_id,
            "match_score": matching_table["match_score"],
            "rows_inserted": load_result["rows_inserted"],
            "total_rows": load_result["total_rows"],
            "actions": actions,
            "analysis": analysis,
        }

    else:
        # --- Crear tabla nueva ---
        table_name = analysis["suggested_table_name"]
        display_name = analysis["suggested_display_name"]

        # Definir columnas
        columns_def = [
            {
                "name": col["clean_name"],
                "type": col["inferred_type"],
                "required": col["is_required"],
            }
            for col in analysis["columns"]
        ]

        create_result = await create_table(org_id, table_name, display_name, columns_def)

        if "error" in create_result:
            # Tabla ya existia — declarar las columnas nuevas y cargar ahi
            table_id = create_result["table_id"]
            modify_result = await modify_table(
                org_id,
                table_id,
                add_columns=[{"name": c["name"], "type": c["type"]} for c in columns_def],
            )
            if modify_result.get("columns_added"):
                actions.append({
                    "action": "modify_table",
                    "detail": f"Agregadas {modify_result['columns_added']} columnas a '{table_name}'",
                })
            load_result = await load_csv_to_table(df, org_id, table_id)
            actions.append({
                "action": "load_to_existing",
                "detail": f"Tabla '{table_name}' ya existia. Cargados {load_result['rows_inserted']} registros adicionales.",
            })
            return {
                "status": "loaded_to_existing",
                "table_name": table_name,
                "table_id": table_id,
                "rows_inserted": load_result["rows_inserted"],
                "total_rows": load_result["total_rows"],
                "actions": actions,
                "analysis": analysis,
            }

        actions.append({
            "action": "create_table",
            "detail": f"Tabla '{display_name}' creada con {len(columns_def)} columnas",
        })

        # Cargar datos. Si falla, la tabla recien creada no debe quedar huerfana.
        try:
            load_result = await load_csv_to_table(df, org_id, create_result["table_id"])
        except Exception:
            await _drop_table_record(org_id, create_result["table_id"])
            raise
        actions.append({
            "action": "load_data",
            "detail": f"Cargados {load_result['rows_inserted']} registros",
        })

        return {
            "status": "created_new_table",
            "table_name": table_name,
            "table_id": create_result["table_id"],
            "rows_inserted": load_result["rows_inserted"],
            "total_rows": load_result["total_rows"],
            "actions": actions,
            "analysis": analysis,
        }
