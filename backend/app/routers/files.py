import json
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.auth import CurrentUserDep
from app.database import get_org_pool
from app.models.schemas import ColumnInfo, FileDetail, FileListItem, FileUploadResponse, MessageResponse
from app.services.file_service import (
    _infer_columns,
    insert_records,
    parse_file,
    store_file,
    validate_file,
)

router = APIRouter(prefix="/api/v1/files", tags=["Files"])


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Sube archivo, lo guarda localmente, y carga datos en tablas automaticamente",
)
async def upload_file(
    file: UploadFile,
    current_user: CurrentUserDep,
):
    from app.services.schema_agent_service import smart_upload

    df = await parse_file(file)
    file_type, size_bytes = await validate_file(file, df)
    columns = _infer_columns(df)

    # 1. Guardar archivo (local + BYTEA en DB)
    file_id = await store_file(
        upload=file,
        org_id=current_user.org_id,
        file_type=file_type,
        columns=columns,
        rows_count=len(df),
        size_bytes=size_bytes,
    )

    # 2. Smart upload: analizar, mapear/crear tabla, insertar datos
    try:
        result = await smart_upload(df, current_user.org_id, file.filename or "archivo")

        # 3. Actualizar uploaded_files con info de carga
        pool = await get_org_pool(current_user.org_id)
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE uploaded_files SET status = 'ready', rows_count = $1 WHERE id = $2",
                result.get("rows_inserted", len(df)),
                file_id,
            )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(f"Smart upload failed: {exc}")
        pool = await get_org_pool(current_user.org_id)
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE uploaded_files SET status = 'ready', rows_count = $1 WHERE id = $2",
                len(df), file_id,
            )
        result = {"status": "uploaded_without_mapping", "rows_inserted": 0}

    if result.get("rows_inserted"):
        # Si la organizacion aun no tiene tableros, se sugieren (no lanza ni espera mas que su tope de tiempo).
        from app.services.dashboard_suggest_service import auto_suggest_after_upload
        await auto_suggest_after_upload(current_user.org_id)

    created_at = datetime.now(timezone.utc)

    return {
        "file_id": file_id,
        "filename": file.filename or "archivo",
        "file_type": file_type,
        "file_size_bytes": size_bytes,
        "rows_count": result.get("rows_inserted", len(df)),
        "columns_detected": [c.model_dump() for c in columns],
        "status": "ready",
        "created_at": created_at.isoformat(),
        "smart_upload": {
            "table_name": result.get("table_name"),
            "table_id": result.get("table_id"),
            "rows_inserted": result.get("rows_inserted", 0),
            "actions": result.get("actions", []),
        },
    }


@router.get("", summary="Lista los archivos de la organización")
async def list_files(current_user: CurrentUserDep):
    pool = await get_org_pool(current_user.org_id)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, filename, original_name, mime_type, size_bytes, rows_count, status, created_at
            FROM uploaded_files
            WHERE status != 'deleted'
            ORDER BY created_at DESC
            """
        )

    return [
        {
            "id": str(row["id"]),
            "file_id": str(row["id"]),
            "name": row["filename"] or "archivo",
            "original_name": row["original_name"] or row["filename"] or "archivo",
            "filename": row["filename"] or "archivo",
            "file_type": _mime_to_type(row["mime_type"] or ""),
            "size_bytes": row["size_bytes"] or 0,
            "row_count": row["rows_count"] or 0,
            "rows_count": row["rows_count"] or 0,
            "status": row["status"] or "uploaded",
            "created_at": row["created_at"].isoformat() if row["created_at"] else "",
        }
        for row in rows
    ]


@router.get(
    "/{file_id}",
    response_model=FileDetail,
    summary="Detalle de archivo con vista previa de 50 filas",
)
async def get_file(file_id: str, current_user: CurrentUserDep) -> FileDetail:
    import uuid as _uuid
    pool = await get_org_pool(current_user.org_id)

    try:
        fid = _uuid.UUID(file_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID invalido.")

    async with pool.acquire() as conn:
        file_row = await conn.fetchrow(
            """
            SELECT id, filename, mime_type, size_bytes, rows_count,
                   columns_info, status, error_message, created_at
            FROM uploaded_files
            WHERE id = $1
            """,
            fid,
        )
        if not file_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado.")

        record_rows = await conn.fetch(
            """
            SELECT data FROM data_records
            WHERE table_name = $1
            ORDER BY created_at
            LIMIT 50
            """,
            file_id,
        )

    cols_raw = file_row["columns_info"]
    if isinstance(cols_raw, str):
        cols_raw = json.loads(cols_raw)
    columns = [ColumnInfo(**c) for c in (cols_raw or [])]

    preview: list[dict] = []
    for r in record_rows:
        data = r["data"]
        if isinstance(data, str):
            data = json.loads(data)
        preview.append(data)

    return FileDetail(
        file_id=str(file_row["id"]),
        filename=file_row["filename"],
        file_type=_mime_to_type(file_row["mime_type"] or ""),
        file_size_bytes=file_row["size_bytes"] or 0,
        rows_count=file_row["rows_count"] or 0,
        columns_detected=columns,
        status=file_row["status"],
        error_message=file_row.get("error_message"),
        created_at=file_row["created_at"],
        preview_rows=preview,
    )


@router.get(
    "/{file_id}/download",
    summary="Descarga el archivo como BYTEA",
)
async def download_file(file_id: str, current_user: CurrentUserDep) -> Response:
    import uuid as _uuid
    pool = await get_org_pool(current_user.org_id)

    try:
        fid = _uuid.UUID(file_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID invalido.")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT filename, mime_type, file_data FROM uploaded_files WHERE id = $1",
            fid,
        )

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado.")

    file_data: bytes = bytes(row["file_data"]) if row["file_data"] else b""
    mime = row["mime_type"] or "application/octet-stream"
    filename = row["filename"] or "archivo"

    return Response(
        content=file_data,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete(
    "/{file_id}",
    summary="Elimina un archivo (soft delete via status=deleted)",
)
async def delete_file(file_id: str, current_user: CurrentUserDep):
    import uuid as _uuid
    pool = await get_org_pool(current_user.org_id)

    try:
        fid = _uuid.UUID(file_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de archivo invalido.")

    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE uploaded_files SET status = 'deleted' WHERE id = $1 AND status != 'deleted'",
            fid,
        )

    if result == "UPDATE 0":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado.")

    return {"message": "Archivo eliminado correctamente."}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mime_to_type(mime: str) -> str:
    mapping = {
        "text/csv": "csv",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "application/vnd.ms-excel": "xlsx",
        "application/json": "json",
    }
    return mapping.get(mime, "unknown")
