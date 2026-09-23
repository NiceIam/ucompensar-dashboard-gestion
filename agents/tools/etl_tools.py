"""Tools del ETLAgent para extraccion, mapeo y carga de datos."""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
from google.adk.tools import ToolContext
from psycopg2.extras import Json

from agents.config import get_main_conn, get_org_conn
from agents.tools._security import validate_org_id

logger = logging.getLogger("agents.tools.etl")

BATCH_SIZE = 500
MAX_RECORDS = 10_000


def extract_from_pdf(file_path: str, org_id: str, tool_context: ToolContext) -> dict:
    """Extrae datos tabulares de un archivo PDF usando pdfplumber.

    Busca tablas en cada pagina del PDF y las combina en un solo dataset.
    Guarda una preview de los datos en el state del pipeline.

    Args:
        file_path: Ruta local o URL del archivo PDF a procesar.
        org_id: UUID de la organizacion propietaria.

    Returns:
        dict con tables_found, rows_extracted, columns (lista),
        preview (primeras 5 filas como lista de dicts).
    """
    _auth_err = validate_org_id(org_id, tool_context)
    if _auth_err:
        return _auth_err
    try:
        import pdfplumber

        all_rows: list[dict] = []
        columns: list[str] | None = None
        tables_found = 0

        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_tables = page.extract_tables()
                for table in page_tables:
                    tables_found += 1
                    if not table or len(table) < 2:
                        continue
                    # First row is header if we don't have columns yet
                    if columns is None:
                        columns = [
                            str(c).strip().lower().replace(" ", "_")
                            for c in table[0]
                        ]
                        data_rows = table[1:]
                    else:
                        data_rows = table[1:]  # Skip repeated headers

                    for row in data_rows:
                        if len(row) == len(columns):
                            all_rows.append(dict(zip(columns, row)))

        if not all_rows:
            return {
                "error": "No se encontraron tablas en el PDF.",
                "tables_found": tables_found,
                "rows_extracted": 0,
            }

        # Enforce limit
        if len(all_rows) > MAX_RECORDS:
            all_rows = all_rows[:MAX_RECORDS]
            logger.warning(f"PDF truncado a {MAX_RECORDS} filas (limite del plan)")

        # Store in state for later use
        tool_context.state["extracted_data"] = all_rows
        tool_context.state["extracted_columns"] = columns

        return {
            "tables_found": tables_found,
            "rows_extracted": len(all_rows),
            "columns": columns,
            "preview": all_rows[:5],
        }

    except Exception as e:
        logger.error(f"Error extrayendo PDF: {e}", exc_info=True)
        return {"error": f"Error al leer el PDF: {type(e).__name__}"}


def extract_from_spreadsheet(
    file_path: str, org_id: str, tool_context: ToolContext
) -> dict:
    """Extrae datos de un archivo CSV o Excel usando pandas.

    Lee la primera hoja si es Excel, o el archivo completo si es CSV.
    Normaliza los nombres de las columnas a snake_case.

    Args:
        file_path: Ruta local del archivo CSV o Excel.
        org_id: UUID de la organizacion propietaria.

    Returns:
        dict con rows_extracted, columns (lista),
        preview (primeras 5 filas como lista de dicts).
    """
    _auth_err = validate_org_id(org_id, tool_context)
    if _auth_err:
        return _auth_err
    try:
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""

        if ext == "csv":
            df = pd.read_csv(file_path, nrows=MAX_RECORDS)
        elif ext in ("xlsx", "xls"):
            df = pd.read_excel(file_path, nrows=MAX_RECORDS)
        else:
            return {"error": f"Formato no soportado: .{ext}. Use CSV o Excel."}

        # Normalize column names
        df.columns = [
            str(c).strip().lower().replace(" ", "_").replace(".", "_")
            for c in df.columns
        ]
        # Replace NaN with None for JSON
        df = df.where(df.notna(), None)

        columns = list(df.columns)
        rows = df.to_dict("records")

        tool_context.state["extracted_data"] = rows
        tool_context.state["extracted_columns"] = columns

        return {
            "rows_extracted": len(rows),
            "columns": columns,
            "preview": rows[:5],
        }

    except Exception as e:
        logger.error(f"Error extrayendo spreadsheet: {e}", exc_info=True)
        return {"error": f"Error al leer el archivo: {type(e).__name__}"}


def get_org_schema(org_id: str, tool_context: ToolContext) -> dict:
    """Obtiene las tablas estandarizadas de la organizacion con sus definiciones de columnas.

    Consulta org_data_tables en la BD de la org y business_types en la BD principal.

    Args:
        org_id: UUID de la organizacion.

    Returns:
        dict con business_type (nombre), tables (lista de tablas con name,
        display_name, columns con name, type, label, required).
    """
    _auth_err = validate_org_id(org_id, tool_context)
    if _auth_err:
        return _auth_err
    try:
        # Get org's business type from main DB
        with get_main_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT o.business_type_id, bt.name, bt.display_name
                    FROM organizations o
                    LEFT JOIN business_types bt ON bt.id = o.business_type_id
                    WHERE o.id = %s
                    """,
                    (org_id,),
                )
                org_row = cur.fetchone()

        business_type_display = (org_row or {}).get("display_name", "Desconocido")

        # Get org's tables from org DB
        with get_org_conn(org_id) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, table_name, display_name, columns_definition, row_count
                    FROM org_data_tables
                    WHERE org_id = %s
                    """,
                    (org_id,),
                )
                tables = cur.fetchall()

        result = {
            "business_type": business_type_display,
            "tables": [
                {
                    "id": str(t["id"]),
                    "name": t["table_name"],
                    "display_name": t["display_name"],
                    "row_count": t["row_count"] or 0,
                    "columns": t["columns_definition"],
                }
                for t in tables
            ],
        }

        tool_context.state["org_schema"] = result
        return result

    except Exception as e:
        logger.error(f"Error obteniendo schema: {e}", exc_info=True)
        return {"error": f"Error al obtener schema: {type(e).__name__}"}


def map_columns_to_schema(
    target_table: str,
    org_id: str,
    tool_context: ToolContext,
) -> dict:
    """Mapea las columnas extraidas del archivo a las columnas del schema destino.

    Usa coincidencia por nombre para mapear automaticamente.
    Las columnas que no coinciden se reportan como no mapeadas.
    El agente LLM puede luego ajustar los mapeos usando su comprension del contexto.

    Args:
        target_table: Nombre de la tabla destino (ej: 'productos', 'ventas').
        org_id: UUID de la organizacion.

    Returns:
        dict con mappings (lista de source->target con confidence),
        unmapped_source (columnas del archivo sin mapear),
        unmapped_target (columnas del schema sin dato).
    """
    _auth_err = validate_org_id(org_id, tool_context)
    if _auth_err:
        return _auth_err
    try:
        extracted_columns: list[str] = tool_context.state.get(
            "extracted_columns", []
        )
        org_schema: dict | None = tool_context.state.get("org_schema")

        if not extracted_columns:
            return {"error": "No hay columnas extraidas. Ejecute extract primero."}

        if not org_schema:
            return {
                "error": "No hay schema disponible. Ejecute get_org_schema primero."
            }

        # Find target table in schema
        target = None
        for t in org_schema.get("tables", []):
            if t["name"] == target_table:
                target = t
                break

        if not target:
            available = [t["name"] for t in org_schema.get("tables", [])]
            return {
                "error": (
                    f"Tabla '{target_table}' no encontrada. "
                    f"Disponibles: {available}"
                )
            }

        schema_columns: dict[str, dict] = {
            col["name"]: col for col in target["columns"]
        }

        mappings: list[dict] = []
        mapped_sources: set[str] = set()
        mapped_targets: set[str] = set()

        # Pass 1: exact match
        for src_col in extracted_columns:
            if src_col in schema_columns:
                mappings.append({
                    "source": src_col,
                    "target": src_col,
                    "confidence": 1.0,
                })
                mapped_sources.add(src_col)
                mapped_targets.add(src_col)

        # Pass 2: fuzzy match (contains)
        for src_col in extracted_columns:
            if src_col in mapped_sources:
                continue
            for tgt_name, tgt_info in schema_columns.items():
                if tgt_name in mapped_targets:
                    continue
                # Check if one contains the other
                label = tgt_info.get("label", "").lower().replace(" ", "_")
                if (
                    src_col in tgt_name
                    or tgt_name in src_col
                    or src_col in label
                    or label in src_col
                ):
                    mappings.append({
                        "source": src_col,
                        "target": tgt_name,
                        "confidence": 0.7,
                    })
                    mapped_sources.add(src_col)
                    mapped_targets.add(tgt_name)
                    break

        unmapped_source = [c for c in extracted_columns if c not in mapped_sources]
        unmapped_target = [c for c in schema_columns if c not in mapped_targets]

        result = {
            "target_table": target_table,
            "mappings": mappings,
            "unmapped_source": unmapped_source,
            "unmapped_target": unmapped_target,
            "auto_mapped_count": len(mappings),
            "total_source_columns": len(extracted_columns),
            "total_target_columns": len(schema_columns),
        }

        tool_context.state["column_mappings"] = result
        return result

    except Exception as e:
        logger.error(f"Error mapeando columnas: {e}", exc_info=True)
        return {"error": f"Error al mapear columnas: {type(e).__name__}"}


def load_to_org_table(
    org_id: str,
    target_table: str,
    source: str,
    tool_context: ToolContext,
) -> dict:
    """Carga los datos transformados en la tabla destino de la organizacion.

    Lee los datos extraidos y los mapeos de columnas del state, aplica
    las transformaciones necesarias, y hace batch INSERT en org_data_rows.

    Args:
        org_id: UUID de la organizacion.
        target_table: Nombre de la tabla destino (ej: 'productos').
        source: Origen de los datos ('pdf', 'csv', 'excel', 'chatbot').

    Returns:
        dict con rows_loaded, rows_failed, warnings, table_name.
    """
    _auth_err = validate_org_id(org_id, tool_context)
    if _auth_err:
        return _auth_err
    try:
        extracted_data: list[dict] = tool_context.state.get("extracted_data", [])
        column_mappings: dict = tool_context.state.get("column_mappings", {})
        mappings: list[dict] = column_mappings.get("mappings", [])

        if not extracted_data:
            return {"error": "No hay datos extraidos para cargar."}

        with get_org_conn(org_id) as conn:
            with conn.cursor() as cur:
                # Get table_id y schema de columnas para validar tipos.
                cur.execute(
                    "SELECT id, row_count, columns_definition FROM org_data_tables WHERE org_id = %s AND table_name = %s",
                    (org_id, target_table),
                )
                table_row = cur.fetchone()
                if not table_row:
                    return {
                        "error": (
                            f"Tabla '{target_table}' no encontrada para esta organizacion."
                        )
                    }

                table_id: str = str(table_row["id"])
                current_count: int = table_row.get("row_count", 0) or 0

                # Parsear schema de columnas para validacion de tipos.
                _col_def = table_row.get("columns_definition") or []
                if isinstance(_col_def, str):
                    import json as _json
                    try:
                        _col_def = _json.loads(_col_def)
                    except Exception:
                        _col_def = []
                col_type_map: dict[str, str] = {
                    c["name"]: c.get("type", "text") for c in _col_def if isinstance(c, dict)
                }

                # Check limit
                if current_count + len(extracted_data) > MAX_RECORDS:
                    max_loadable = MAX_RECORDS - current_count
                    if max_loadable <= 0:
                        return {
                            "error": (
                                f"La tabla ya tiene {current_count} registros "
                                f"(limite: {MAX_RECORDS})."
                            )
                        }
                    extracted_data = extracted_data[:max_loadable]
                    logger.warning(f"Datos truncados a {max_loadable} filas por limite")

                # Build mapping dict
                mapping_dict: dict[str, str] = {
                    m["source"]: m["target"] for m in mappings
                }

                # Transform rows
                rows_to_insert: list[tuple] = []
                rows_failed = 0
                warnings: list[str] = []

                for raw_row in extracted_data:
                    try:
                        transformed: dict[str, Any] = {}
                        row_valid = True
                        for src_col, value in raw_row.items():
                            target_col = mapping_dict.get(src_col)
                            if not target_col:
                                continue
                            if value is None or (
                                isinstance(value, float) and pd.isna(value)
                            ):
                                transformed[target_col] = None
                                continue
                            # Validar y coercionar tipo segun schema.
                            expected_type = col_type_map.get(target_col, "text")
                            try:
                                if expected_type in ("number", "integer", "float"):
                                    transformed[target_col] = (
                                        int(value) if expected_type == "integer"
                                        else float(value)
                                    )
                                elif expected_type == "date":
                                    # Aceptar strings con formato fecha; dejar como str.
                                    transformed[target_col] = str(value).strip()
                                else:
                                    transformed[target_col] = str(value)
                            except (ValueError, TypeError):
                                # Valor no convertible: incluir como None + warning
                                transformed[target_col] = None
                                if len(warnings) < 20:
                                    warnings.append(
                                        f"Col '{target_col}': valor '{str(value)[:30]}' no es {expected_type}"
                                    )

                        if transformed:
                            rows_to_insert.append(
                                (org_id, table_id, Json(transformed), source)
                            )
                    except Exception:
                        rows_failed += 1

                # Batch insert
                loaded = 0
                for i in range(0, len(rows_to_insert), BATCH_SIZE):
                    batch = rows_to_insert[i : i + BATCH_SIZE]
                    for row_tuple in batch:
                        cur.execute(
                            """
                            INSERT INTO org_data_rows (org_id, table_id, data, source)
                            VALUES (%s, %s, %s, %s)
                            """,
                            row_tuple,
                        )
                    loaded += len(batch)

                # Update row_count
                new_count = current_count + loaded
                cur.execute(
                    "UPDATE org_data_tables SET row_count = %s WHERE id = %s",
                    (new_count, table_id),
                )

            conn.commit()

        if rows_failed > 0:
            warnings.append(
                f"{rows_failed} filas no pudieron ser transformadas."
            )
        if len(extracted_data) < len(
            tool_context.state.get("extracted_data", [])
        ):
            warnings.append(
                f"Datos truncados al limite de {MAX_RECORDS} registros."
            )

        return {
            "table_name": target_table,
            "rows_loaded": loaded,
            "rows_failed": rows_failed,
            "total_rows_in_table": new_count,
            "warnings": warnings,
        }

    except Exception as e:
        logger.error(f"Error cargando datos: {e}", exc_info=True)
        return {"error": f"Error al cargar datos: {type(e).__name__}"}


def create_etl_job(
    org_id: str,
    source_type: str,
    source_metadata: dict,
    tool_context: ToolContext,
) -> dict:
    """Crea un registro de trabajo ETL en la tabla etl_jobs para tracking.

    Args:
        org_id: UUID de la organizacion.
        source_type: Tipo de fuente ('pdf', 'csv', 'excel', 'database', 'chatbot').
        source_metadata: Metadata del origen (nombre de archivo, ruta, etc).

    Returns:
        dict con job_id y status inicial.
    """
    _auth_err = validate_org_id(org_id, tool_context)
    if _auth_err:
        return _auth_err
    try:
        with get_org_conn(org_id) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO etl_jobs (org_id, source_type, source_metadata, status, started_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    RETURNING id
                    """,
                    (org_id, source_type, Json(source_metadata), "pending"),
                )
                job_id = str(cur.fetchone()["id"])
            conn.commit()

        tool_context.state["etl_job_id"] = job_id
        return {"job_id": job_id, "status": "pending"}

    except Exception as e:
        logger.error(f"Error creando ETL job: {e}", exc_info=True)
        return {"error": f"Error al crear job: {type(e).__name__}"}


def update_etl_job(
    org_id: str,
    status: str,
    tool_context: ToolContext,
    rows_extracted: int = 0,
    rows_loaded: int = 0,
    error_message: str = "",
) -> dict:
    """Actualiza el estado y metricas de un trabajo ETL existente.

    Args:
        org_id: UUID de la organizacion.
        status: Nuevo estado ('extracting', 'transforming', 'loading', 'completed', 'failed').
        rows_extracted: Numero de filas extraidas.
        rows_loaded: Numero de filas cargadas exitosamente.
        error_message: Mensaje de error si el status es 'failed'.

    Returns:
        dict con job_id y nuevo status.
    """
    _auth_err = validate_org_id(org_id, tool_context)
    if _auth_err:
        return _auth_err
    try:
        job_id: str | None = tool_context.state.get("etl_job_id")
        if not job_id:
            return {"error": "No hay job_id en el state."}

        # Build SET clause dynamically
        set_parts = ["status = %s"]
        params: list[Any] = [status]

        if rows_extracted > 0:
            set_parts.append("rows_extracted = %s")
            params.append(rows_extracted)
        if rows_loaded > 0:
            set_parts.append("rows_loaded = %s")
            params.append(rows_loaded)
        if error_message:
            set_parts.append("error_message = %s")
            params.append(error_message[:500])
        if status in ("completed", "failed"):
            set_parts.append("completed_at = NOW()")

        params.append(job_id)

        with get_org_conn(org_id) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE etl_jobs SET {', '.join(set_parts)} WHERE id = %s",
                    tuple(params),
                )
            conn.commit()

        return {"job_id": job_id, "status": status}

    except Exception as e:
        logger.error(f"Error actualizando ETL job: {e}", exc_info=True)
        return {"error": f"Error al actualizar job: {type(e).__name__}"}
