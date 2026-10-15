"""Router para gestion inteligente de schema — Schema Agent."""

import logging

from fastapi import APIRouter, HTTPException, UploadFile, File, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional

from app.auth import CurrentUserDep
from app.services import schema_agent_service as agent
from app.services.file_service import parse_file, parse_file_sheets

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/schema", tags=["Schema Agent"])


def _table_uuid(table_id: str):
    """UUID de la tabla; 404 (no 500 por ValueError) si el id viene mal formado."""
    import uuid as _uuid

    try:
        return _uuid.UUID(table_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tabla no encontrada")


class CreateTableRequest(BaseModel):
    table_name: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=150)
    columns: list[dict]


class ModifyTableRequest(BaseModel):
    add_columns: list[dict] = Field(default_factory=list)
    new_display_name: Optional[str] = None


@router.post("/analyze", summary="Analiza un CSV y sugiere schema")
async def analyze_file(
    file: UploadFile = File(...),
    current_user: CurrentUserDep = None,
):
    df = await parse_file(file)
    analysis = agent.analyze_csv(df)
    matching = await agent.find_matching_table(current_user.org_id, analysis["columns"])
    analysis["matching_table"] = matching
    return JSONResponse(content=analysis)


@router.post(
    "/smart-upload",
    summary="Upload inteligente — analiza, decide y carga (soporta Excel con varias hojas)",
)
async def smart_upload(
    file: UploadFile = File(...),
    current_user: CurrentUserDep = None,
):
    sheets = await parse_file_sheets(file)
    filename = file.filename or "upload.csv"

    # Caso simple: CSV/JSON o Excel de una sola hoja — mismo shape de respuesta de siempre.
    if len(sheets) == 1:
        _sheet_name, df = sheets[0]
        result = await agent.smart_upload(df, current_user.org_id, filename)
        return JSONResponse(content=result)

    # Excel con varias pestañas: procesar cada una por separado y agregar resultados.
    # No se procesan en paralelo a proposito, para evitar carreras al crear/actualizar
    # tablas en la misma organizacion.
    sheet_results: list[dict] = []
    total_rows_inserted = 0

    for sheet_name, df in sheets:
        label = sheet_name or filename
        if df.empty:
            sheet_results.append({
                "sheet_name": sheet_name,
                "status": "skipped_empty",
                "rows_inserted": 0,
            })
            continue

        try:
            result = await agent.smart_upload(df, current_user.org_id, f"{filename} :: {label}")
            result["sheet_name"] = sheet_name
            sheet_results.append(result)
            total_rows_inserted += result.get("rows_inserted", 0) or 0
        except Exception as exc:
            logger.error("Error procesando hoja '%s' de '%s': %s", sheet_name, filename, exc)
            sheet_results.append({
                "sheet_name": sheet_name,
                "status": "error",
                "error": str(exc),
                "rows_inserted": 0,
            })

    return JSONResponse(content={
        "status": "multi_sheet_processed",
        "multi_sheet": True,
        "sheets_processed": len(sheets),
        "total_rows_inserted": total_rows_inserted,
        "sheets": sheet_results,
    })


@router.post("/tables", summary="Crea tabla nueva")
async def create_table(body: CreateTableRequest, current_user: CurrentUserDep = None):
    result = await agent.create_table(
        current_user.org_id, body.table_name, body.display_name, body.columns,
    )
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result["error"])
    return result


@router.put("/tables/{table_id}", summary="Modifica tabla existente")
async def modify_table(table_id: str, body: ModifyTableRequest, current_user: CurrentUserDep = None):
    result = await agent.modify_table(
        current_user.org_id, table_id, body.add_columns, body.new_display_name,
    )
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.delete("/tables/{table_id}", summary="Elimina tabla y sus datos")
async def delete_table(table_id: str, current_user: CurrentUserDep = None):
    result = await agent.delete_table(current_user.org_id, table_id)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.get("/tables/{table_id}/rows", summary="Obtiene filas de una tabla")
async def get_table_rows(
    table_id: str,
    limit: int = 20,
    offset: int = 0,
    current_user: CurrentUserDep = None,
):
    """Retorna filas reales de org_data_rows para una tabla."""
    from app.database import get_org_pool

    table_uuid = _table_uuid(table_id)
    pool = await get_org_pool(current_user.org_id)
    async with pool.acquire() as conn:
        table = await conn.fetchrow(
            "SELECT table_name, display_name, row_count FROM org_data_tables WHERE id = $1",
            table_uuid,
        )
        if not table:
            raise HTTPException(status_code=404, detail="Tabla no encontrada")

        rows = await conn.fetch(
            "SELECT id, data, created_at FROM org_data_rows WHERE table_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            table_uuid, min(limit, 100), offset,
        )

    import json as _json

    parsed_rows = []
    for r in rows:
        data = r["data"]
        if isinstance(data, str):
            try:
                data = _json.loads(data)
            except (ValueError, TypeError):
                pass
        parsed_rows.append({
            "id": str(r["id"]),
            "data": data,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        })

    return {
        "table_name": table["table_name"],
        "display_name": table["display_name"],
        "total": table["row_count"] or 0,
        "rows": parsed_rows,
    }


@router.delete("/tables/{table_id}/rows/{row_id}", summary="Elimina una fila")
async def delete_row(table_id: str, row_id: str, current_user: CurrentUserDep = None):
    from app.database import get_org_pool
    import uuid as _uuid

    # Ids mal formados: 404 (el recurso no existe) en vez de un 500 por ValueError
    table_uuid = _table_uuid(table_id)
    try:
        row_uuid = _uuid.UUID(row_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fila no encontrada")

    pool = await get_org_pool(current_user.org_id)
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM org_data_rows WHERE id = $1 AND table_id = $2",
            row_uuid, table_uuid,
        )
        count = await conn.fetchval(
            "SELECT count(*) FROM org_data_rows WHERE table_id = $1", table_uuid,
        )
        await conn.execute(
            "UPDATE org_data_tables SET row_count = $1 WHERE id = $2", count, table_uuid,
        )
    return {"deleted": True, "new_count": count}


@router.get("/tables/{table_id}/template", summary="Descarga plantilla CSV de una tabla")
async def download_template(table_id: str, current_user: CurrentUserDep = None):
    """CSV vacio con headers y fila ejemplo."""
    from app.database import get_org_pool
    from fastapi.responses import Response
    import json as _json

    table_uuid = _table_uuid(table_id)
    pool = await get_org_pool(current_user.org_id)
    async with pool.acquire() as conn:
        table = await conn.fetchrow(
            "SELECT table_name, columns_definition FROM org_data_tables WHERE id = $1",
            table_uuid,
        )
    if not table:
        raise HTTPException(status_code=404, detail="Tabla no encontrada")

    cols = table["columns_definition"]
    if isinstance(cols, str):
        cols = _json.loads(cols)

    header = ",".join(c["name"] for c in cols)
    example = ",".join(
        {"text": "ejemplo_texto", "number": "0.00", "integer": "0", "date": "2025-01-01", "boolean": "true"}.get(c.get("type", "text"), "")
        for c in cols
    )
    csv_content = f"{header}\n{example}\n"

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="plantilla_{table["table_name"]}.csv"'},
    )


@router.get("/template-all", summary="Descarga plantilla Excel con todas las tablas")
async def download_all_templates(current_user: CurrentUserDep = None):
    """Genera un Excel con una hoja por tabla, headers + fila ejemplo."""
    from app.database import get_org_pool
    from fastapi.responses import Response
    import uuid as _uuid
    import json as _json
    import io
    import openpyxl

    pool = await get_org_pool(current_user.org_id)
    async with pool.acquire() as conn:
        tables = await conn.fetch(
            "SELECT table_name, display_name, columns_definition FROM org_data_tables ORDER BY table_name"
        )

    if not tables:
        raise HTTPException(status_code=404, detail="No hay tablas configuradas")

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    type_examples = {"text": "ejemplo", "number": 0.0, "integer": 0, "date": "2025-01-01", "boolean": True}

    for t in tables:
        cols = t["columns_definition"]
        if isinstance(cols, str):
            cols = _json.loads(cols)
        if not cols:
            continue

        ws = wb.create_sheet(title=t["display_name"][:31])

        # Headers en negrita
        for ci, col in enumerate(cols, 1):
            cell = ws.cell(row=1, column=ci, value=col["name"])
            cell.font = openpyxl.styles.Font(bold=True)
            # Tipo como comentario
            cell.comment = openpyxl.comments.Comment(f"Tipo: {col.get('type', 'text')}", "Sistema")

        # Fila ejemplo
        for ci, col in enumerate(cols, 1):
            ws.cell(row=2, column=ci, value=type_examples.get(col.get("type", "text"), ""))

        # Auto-width
        for ci, col in enumerate(cols, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(ci)].width = max(len(col["name"]) + 4, 15)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="plantilla_completa.xlsx"'},
    )


@router.get("/tables/{table_id}/export", summary="Exporta datos de una tabla como CSV")
async def export_table_data(table_id: str, current_user: CurrentUserDep = None):
    """Descarga todos los datos de una tabla como CSV."""
    from app.database import get_org_pool
    from fastapi.responses import Response
    import json as _json
    import io
    import csv as _csv

    table_uuid = _table_uuid(table_id)
    pool = await get_org_pool(current_user.org_id)
    async with pool.acquire() as conn:
        table = await conn.fetchrow(
            "SELECT table_name, display_name, columns_definition FROM org_data_tables WHERE id = $1",
            table_uuid,
        )
        if not table:
            raise HTTPException(status_code=404, detail="Tabla no encontrada")

        rows = await conn.fetch(
            "SELECT data FROM org_data_rows WHERE table_id = $1 ORDER BY created_at",
            table_uuid,
        )

    cols = table["columns_definition"]
    if isinstance(cols, str):
        cols = _json.loads(cols)
    col_names = [c["name"] for c in cols]

    output = io.StringIO()
    writer = _csv.writer(output)
    writer.writerow(col_names)

    for r in rows:
        data = r["data"]
        if isinstance(data, str):
            data = _json.loads(data)
        writer.writerow([data.get(cn, "") for cn in col_names])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{table["table_name"]}_datos.csv"'},
    )
