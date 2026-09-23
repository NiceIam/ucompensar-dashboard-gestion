import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status

from app.config import get_settings
from app.database import get_org_pool
from app.models.schemas import AgentResultDetail, AgentSessionResponse


async def _fetch_file_data(file_id: str, org_id: str) -> dict[str, Any]:
    """Obtiene metadata y registros del archivo para pasarlos al pipeline."""
    pool = await get_org_pool(org_id)

    async with pool.acquire() as conn:
        file_row = await conn.fetchrow(
            """
            SELECT id, filename, original_name, mime_type, size_bytes, rows_count, status
            FROM uploaded_files
            WHERE id = $1
            """,
            file_id,
        )
        if not file_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado.")

        record_rows = await conn.fetch(
            """
            SELECT data FROM data_records
            WHERE table_name = $1
            ORDER BY created_at
            LIMIT 10000
            """,
            file_id,
        )

    records: list[dict] = []
    for r in record_rows:
        data = r["data"]
        if isinstance(data, str):
            data = json.loads(data)
        records.append(data)

    return {
        "file": dict(file_row),
        "records": records,
    }


async def _run_adk_pipeline(
    file_data: dict[str, Any],
    org_id: str,
    user_id: str,
    session_id: str,
) -> dict[str, Any]:
    """Ejecuta el pipeline de agentes Google ADK y retorna los resultados del state."""
    try:
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types as genai_types

        import sys
        import os
        agents_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "agents")
        if agents_path not in sys.path:
            sys.path.insert(0, agents_path)

        from pipeline import create_pipeline

        pipeline_agent = create_pipeline()
        session_service = InMemorySessionService()
        runner = Runner(
            agent=pipeline_agent,
            app_name="ucompensar-pipeline",
            session_service=session_service,
        )

        session = await session_service.create_session(
            app_name="ucompensar-pipeline",
            user_id=user_id,
            state={
                "file_id": str(file_data["file"]["id"]),
                "org_id": org_id,
                "user_id": user_id,
                "session_id": session_id,
                "file_metadata": file_data["file"],
                "records": file_data["records"],
            },
        )

        initial_message = genai_types.Content(
            role="user",
            parts=[
                genai_types.Part(
                    text=(
                        f"Analiza el archivo '{file_data['file']['filename']}' "
                        f"con {len(file_data['records'])} registros para la organización {org_id}."
                    )
                )
            ],
        )

        final_state: dict[str, Any] = {}
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=initial_message,
        ):
            if hasattr(event, "is_final") and event.is_final:
                final_state = session_service._sessions.get(session.id, {}).get("state", {})

        return {
            "cleaner_output": final_state.get("cleaner_output"),
            "analyzer_output": final_state.get("analyzer_output"),
            "insights_output": final_state.get("insights_output"),
            "dashboard_output": final_state.get("dashboard_output"),
        }

    except ImportError:
        return {
            "cleaner_output": {"status": "pipeline_not_configured"},
            "analyzer_output": None,
            "insights_output": None,
            "dashboard_output": None,
        }
    except Exception as exc:
        raise RuntimeError(f"Error en pipeline ADK: {exc}") from exc


async def run_pipeline(file_id: str, org_id: str, user_id: str) -> AgentSessionResponse:
    """Crea sesión de agente, ejecuta pipeline ADK en background y persiste resultados."""
    pool = await get_org_pool(org_id)

    async with pool.acquire() as conn:
        file_row = await conn.fetchrow(
            "SELECT id, status, filename FROM uploaded_files WHERE id = $1",
            file_id,
        )

    if not file_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado.")

    if file_row["status"] not in ("uploaded", "ready", "processing"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El archivo tiene estado '{file_row['status']}' y no puede ser analizado.",
        )

    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        session_row = await conn.fetchrow(
            """
            INSERT INTO agent_sessions (id, user_id, file_id, status, started_at)
            VALUES ($1, $2, $3, 'running', $4)
            RETURNING id, status, started_at
            """,
            session_id,
            user_id,
            file_id,
            now,
        )

    asyncio.create_task(_execute_and_persist(session_id, file_id, org_id, user_id))

    return AgentSessionResponse(
        session_id=session_id,
        file_id=file_id,
        org_id=org_id,
        status="running",
        started_at=session_row["started_at"],
    )


async def _execute_and_persist(
    session_id: str, file_id: str, org_id: str, user_id: str
) -> None:
    """Tarea en background: ejecuta pipeline y guarda resultados."""
    pool = await get_org_pool(org_id)
    now = datetime.now(timezone.utc)

    try:
        file_data = await _fetch_file_data(file_id, org_id)
        results = await _run_adk_pipeline(file_data, org_id, user_id, session_id)

        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE agent_sessions SET status = 'completed', completed_at = $1 WHERE id = $2",
                now,
                session_id,
            )

            # Insertar un resultado por agente
            for agent_name, output in results.items():
                if output is not None:
                    await conn.execute(
                        """
                        INSERT INTO agent_results (session_id, agent_name, output)
                        VALUES ($1, $2, $3::jsonb)
                        """,
                        session_id,
                        agent_name,
                        json.dumps(output),
                    )

    except Exception as exc:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE agent_sessions
                SET status = 'error', completed_at = $1, error_message = $2
                WHERE id = $3
                """,
                now,
                str(exc)[:500],
                session_id,
            )


async def get_session_results(session_id: str, org_id: str) -> AgentResultDetail:
    pool = await get_org_pool(org_id)

    async with pool.acquire() as conn:
        session_row = await conn.fetchrow(
            "SELECT * FROM agent_sessions WHERE id = $1",
            session_id,
        )

    if not session_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sesión no encontrada.")

    # Reconstruir outputs por nombre de agente
    outputs: dict[str, Any] = {
        "cleaner_output": None,
        "analyzer_output": None,
        "insights_output": None,
        "dashboard_output": None,
    }

    if session_row["status"] == "completed":
        async with pool.acquire() as conn:
            result_rows = await conn.fetch(
                "SELECT agent_name, output FROM agent_results WHERE session_id = $1",
                session_id,
            )
        for r in result_rows:
            key = r["agent_name"]
            val = r["output"]
            if isinstance(val, str):
                val = json.loads(val)
            if key in outputs:
                outputs[key] = val

    file_id = str(session_row["file_id"]) if session_row["file_id"] else ""

    return AgentResultDetail(
        session_id=session_id,
        file_id=file_id,
        org_id=org_id,
        status=session_row["status"],
        started_at=session_row["started_at"],
        completed_at=session_row.get("completed_at"),
        cleaner_output=outputs["cleaner_output"],
        analyzer_output=outputs["analyzer_output"],
        insights_output=outputs["insights_output"],
        dashboard_output=outputs["dashboard_output"],
    )


async def list_sessions(org_id: str) -> list[AgentSessionResponse]:
    pool = await get_org_pool(org_id)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, user_id, file_id, status, started_at, completed_at, error_message
            FROM agent_sessions
            ORDER BY started_at DESC
            LIMIT 50
            """
        )

    return [
        AgentSessionResponse(
            session_id=str(row["id"]),
            file_id=str(row["file_id"]) if row["file_id"] else "",
            org_id=org_id,
            status=row["status"],
            started_at=row["started_at"],
            completed_at=row.get("completed_at"),
            error_message=row.get("error_message"),
        )
        for row in rows
    ]
