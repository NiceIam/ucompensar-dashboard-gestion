import io
import json
import logging
import uuid
from typing import Any, Optional

import pandas as pd
from fastapi import HTTPException, UploadFile, status

from app.database import get_org_pool
from app.models.schemas import ColumnInfo

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_ROWS = 10_000
ALLOWED_TYPES = {
    "text/csv": "csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xlsx",
    "application/json": "json",
}


def _infer_columns(df: pd.DataFrame) -> list[ColumnInfo]:
    infos: list[ColumnInfo] = []
    for col in df.columns:
        series = df[col]
        sample = series.dropna().head(3).tolist()
        infos.append(
            ColumnInfo(
                name=str(col),
                dtype=str(series.dtype),
                non_null_count=int(series.count()),
                sample_values=[str(v) for v in sample],
            )
        )
    return infos


async def parse_file(upload: UploadFile) -> pd.DataFrame:
    """Lee el archivo subido y lo convierte a DataFrame."""
    content = await upload.read()
    await upload.seek(0)

    content_type = upload.content_type or ""
    filename = upload.filename or ""

    file_type: str | None = ALLOWED_TYPES.get(content_type)
    if not file_type:
        if filename.endswith(".csv"):
            file_type = "csv"
        elif filename.endswith((".xlsx", ".xls")):
            file_type = "xlsx"
        elif filename.endswith(".json"):
            file_type = "json"

    if not file_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Tipo de archivo no soportado. Use CSV, Excel o JSON.",
        )

    try:
        if file_type == "csv":
            df = pd.read_csv(io.BytesIO(content))
        elif file_type == "xlsx":
            df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
        else:
            data = json.loads(content)
            df = pd.DataFrame(data if isinstance(data, list) else [data])
    except Exception as exc:
        logger.error("Error al parsear archivo '%s': %s", upload.filename, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Error al procesar el archivo. Verifique el formato.",
        )

    return df


async def parse_file_sheets(upload: UploadFile) -> list[tuple[Optional[str], pd.DataFrame]]:
    """Lee el archivo subido y retorna una lista de (nombre_hoja, DataFrame).

    CSV y JSON siempre tienen una sola "hoja" (nombre_hoja=None). Un Excel
    puede traer varias pestañas (ej. plantilla con una hoja por tabla de
    negocio) — a diferencia de parse_file(), esta funcion las lee TODAS en
    vez de quedarse solo con la primera.
    """
    content = await upload.read()
    await upload.seek(0)

    content_type = upload.content_type or ""
    filename = upload.filename or ""

    file_type: str | None = ALLOWED_TYPES.get(content_type)
    if not file_type:
        if filename.endswith(".csv"):
            file_type = "csv"
        elif filename.endswith((".xlsx", ".xls")):
            file_type = "xlsx"
        elif filename.endswith(".json"):
            file_type = "json"

    if not file_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Tipo de archivo no soportado. Use CSV, Excel o JSON.",
        )

    try:
        if file_type == "csv":
            return [(None, pd.read_csv(io.BytesIO(content)))]
        elif file_type == "xlsx":
            sheets = pd.read_excel(io.BytesIO(content), engine="openpyxl", sheet_name=None)
            return list(sheets.items())
        else:
            data = json.loads(content)
            df = pd.DataFrame(data if isinstance(data, list) else [data])
            return [(None, df)]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error al parsear archivo '%s': %s", upload.filename, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Error al procesar el archivo. Verifique el formato.",
        )


async def validate_file(upload: UploadFile, df: pd.DataFrame) -> tuple[str, int]:
    """Valida tamaño, tipo y conteo de filas. Retorna (file_type, size_bytes)."""
    content_type = upload.content_type or ""
    filename = upload.filename or ""

    file_type: str | None = ALLOWED_TYPES.get(content_type)
    if not file_type:
        if filename.endswith(".csv"):
            file_type = "csv"
        elif filename.endswith((".xlsx", ".xls")):
            file_type = "xlsx"
        elif filename.endswith(".json"):
            file_type = "json"

    if not file_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Tipo de archivo no soportado.",
        )

    content = await upload.read()
    await upload.seek(0)
    size_bytes = len(content)

    if size_bytes > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El archivo supera el límite de {MAX_FILE_SIZE_BYTES // 1024 // 1024}MB.",
        )

    if len(df) > MAX_ROWS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"El archivo tiene {len(df)} filas. El límite del prototipo es {MAX_ROWS}.",
        )

    return file_type, size_bytes


async def store_file(
    upload: UploadFile,
    org_id: str,
    file_type: str,
    columns: list[ColumnInfo],
    rows_count: int,
    size_bytes: int,
) -> str:
    """Almacena el archivo en carpeta local + BYTEA en DB. Retorna file_id."""
    import os
    content = await upload.read()
    await upload.seek(0)

    file_id = str(uuid.uuid4())
    original_name = upload.filename or "archivo"
    mime_type = upload.content_type or "application/octet-stream"

    # Guardar en carpeta local: backend/uploads/<org_id>/
    uploads_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", org_id)
    os.makedirs(uploads_dir, exist_ok=True)
    local_path = os.path.join(uploads_dir, f"{file_id}_{original_name}")
    with open(local_path, "wb") as f:
        f.write(content)
    logger.info(f"Archivo guardado localmente: {local_path}")

    pool = await get_org_pool(org_id)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO uploaded_files (
                id, filename, original_name, mime_type,
                size_bytes, rows_count, columns_info, file_data, status
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, 'uploaded')
            """,
            file_id,
            original_name,
            original_name,
            mime_type,
            size_bytes,
            rows_count,
            json.dumps([c.model_dump() for c in columns]),
            content,
        )

    return file_id


async def insert_records(
    df: pd.DataFrame,
    file_id: str,
    org_id: str,
) -> int:
    """Inserta las filas del DataFrame en data_records. Retorna conteo insertado."""
    pool = await get_org_pool(org_id)

    batch_size = 500
    total = 0

    async with pool.acquire() as conn:
        for i in range(0, len(df), batch_size):
            batch_df = df.iloc[i : i + batch_size]
            for _, row in batch_df.iterrows():
                data = row.where(pd.notnull(row), None).to_dict()
                await conn.execute(
                    """
                    INSERT INTO data_records (table_name, data)
                    VALUES ($1, $2::jsonb)
                    """,
                    file_id,
                    json.dumps(data, default=str),
                )
                total += 1

    return total
