"""Endpoints para ingesta de datos via ETL."""

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.auth import CurrentUserDep
from app.database import get_org_pool
from app.models.schemas import (
    ETLJobListResponse,
    ETLJobResponse,
    ETLUploadResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/etl", tags=["ETL"])

ALLOWED_EXTENSIONS: set[str] = {"csv", "xlsx", "xls", "pdf"}
ALLOWED_MIMES: set[str] = {
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/pdf",
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post(
    "/upload",
    response_model=ETLUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Sube archivo para procesamiento ETL",
)
async def upload_for_etl(
    current_user: CurrentUserDep,
    file: UploadFile = File(...),
    target_table: str = Form(default=""),
) -> ETLUploadResponse:
    """Recibe un archivo, lo valida, lo almacena en uploaded_files y crea un ETL job."""
    # Validar extension
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato no soportado. Use: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    if file.content_type and file.content_type not in ALLOWED_MIMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de archivo no permitido.",
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo esta vacio.",
        )
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="El archivo excede el limite de 10MB.",
        )

    source_type = "pdf" if ext == "pdf" else ("csv" if ext == "csv" else "excel")
    file_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    pool = await get_org_pool(current_user.org_id)
    async with pool.acquire() as conn:
        # Guardar el archivo como BYTEA en uploaded_files
        await conn.execute(
            """
            INSERT INTO uploaded_files (
                id, filename, original_name, mime_type,
                size_bytes, file_data, status
            )
            VALUES ($1, $2, $3, $4, $5, $6, 'uploaded')
            """,
            file_id,
            file.filename or "archivo",
            file.filename or "archivo",
            file.content_type or "application/octet-stream",
            len(content),
            content,
        )

        # Crear ETL job
        job_row = await conn.fetchrow(
            """
            INSERT INTO etl_jobs (
                file_id, source_type, filename, target_table, status, started_at
            )
            VALUES ($1, $2, $3, $4, 'pending', $5)
            RETURNING id
            """,
            file_id,
            source_type,
            file.filename or "",
            target_table or None,
            now,
        )

    job_id = str(job_row["id"])

    return ETLUploadResponse(
        job_id=job_id,
        filename=file.filename or "",
        source_type=source_type,
        status="pending",
        message="Archivo recibido. El procesamiento comenzara en breve.",
    )


@router.get(
    "/jobs",
    response_model=ETLJobListResponse,
    summary="Lista trabajos ETL de la organizacion",
)
async def list_etl_jobs(current_user: CurrentUserDep) -> ETLJobListResponse:
    pool = await get_org_pool(current_user.org_id)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, source_type, filename, target_table, status,
                   rows_extracted, rows_loaded, error_message, started_at, completed_at
            FROM etl_jobs
            ORDER BY created_at DESC
            LIMIT 50
            """
        )

    jobs = [
        ETLJobResponse(
            job_id=str(r["id"]),
            source_type=r["source_type"] or "",
            filename=r["filename"] or "",
            status=r["status"],
            rows_extracted=r["rows_extracted"] or 0,
            rows_loaded=r["rows_loaded"] or 0,
            error_message=r.get("error_message"),
            started_at=r.get("started_at"),
            completed_at=r.get("completed_at"),
        )
        for r in rows
    ]

    return ETLJobListResponse(jobs=jobs, total=len(jobs))


@router.get(
    "/jobs/{job_id}",
    response_model=ETLJobResponse,
    summary="Estado de un trabajo ETL",
)
async def get_etl_job(job_id: str, current_user: CurrentUserDep) -> ETLJobResponse:
    pool = await get_org_pool(current_user.org_id)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM etl_jobs WHERE id = $1",
            job_id,
        )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job no encontrado.",
        )

    return ETLJobResponse(
        job_id=str(row["id"]),
        source_type=row["source_type"] or "",
        filename=row["filename"] or "",
        status=row["status"],
        rows_extracted=row["rows_extracted"] or 0,
        rows_loaded=row["rows_loaded"] or 0,
        error_message=row.get("error_message"),
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
    )
