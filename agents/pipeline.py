"""
Pipeline principal de agentes IA — Orquestador SequentialAgent.

Coordina la ejecucion secuencial de los agentes del pipeline:
- ETL: ETLAgent (extraccion, transformacion, carga)
- Analisis: DataCleaner -> DataAnalyzer -> InsightGenerator -> DashboardConfig
- Chat: ChatAgent (interfaz conversacional)
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

from google.adk.agents import SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from psycopg2.extras import Json

from agents.config import get_org_conn
from agents.etl_agent import etl_agent
from agents.data_cleaner_agent import data_cleaner_agent
from agents.data_analyzer_agent import data_analyzer_agent
from agents.insight_generator_agent import insight_generator_agent
from agents.dashboard_config_agent import dashboard_config_agent
from agents.chat_agent import chat_agent
from agents.analytical_agent import analytical_agent

logger = logging.getLogger("agents.pipeline")


# ---------------------------------------------------------------------------
# C4 — Prompt injection sanitization
# ---------------------------------------------------------------------------
_INJECTION_PATTERNS = re.compile(
    r"(ignore previous|ignore above|forget all|"
    r"system\s*:|assistant\s*:|<\|.*?\|>|"
    r"do anything now|pretend you are|roleplay as|"
    r"in this hypothetical|you have no restrictions|developer mode|"
    r"repeat (the |your )?(system )?prompt|what are your instructions|"
    r"show me your prompt|print your system message|"
    r"\]\(https?://|\]\(data:|!\[.*?\]\(|"
    r'"role"\s*:\s*"system"|"role"\s*:\s*"assistant")',
    re.IGNORECASE | re.DOTALL,
)


def _sanitize_user_message(text: str) -> str:
    """Sanitiza input del usuario para prevenir prompt injection.

    - Limita a 2000 caracteres.
    - Remueve patrones de inyeccion comunes.
    - Elimina null bytes y caracteres de control.
    """
    # Limit length
    text = text[:2000]
    # Remove null bytes and ASCII control chars (except tab/newline/CR)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Replace injection patterns
    text = _INJECTION_PATTERNS.sub("[REMOVED]", text)
    return text


# ---------------------------------------------------------------------------
# C6 — Singleton session services (shared state, preserves conversation context)
# ---------------------------------------------------------------------------
_chat_session_service = InMemorySessionService()
_analytical_session_service = InMemorySessionService()

# ---------------------------------------------------------------------------
# Pipeline SequentialAgent
# ---------------------------------------------------------------------------
pipeline_agent = SequentialAgent(
    name="DataPipeline",
    description=(
        "Pipeline secuencial que limpia, analiza, genera insights "
        "y configura dashboards a partir de datos empresariales."
    ),
    sub_agents=[
        data_cleaner_agent,
        data_analyzer_agent,
        insight_generator_agent,
        dashboard_config_agent,
    ],
)


# ---------------------------------------------------------------------------
# Ejecutar pipeline completo
# ---------------------------------------------------------------------------
async def run_pipeline(
    file_id: str,
    org_id: str,
    user_id: str,
) -> dict[str, Any]:
    """Ejecuta el pipeline completo de analisis de datos.

    Crea una sesion ADK, ejecuta los 4 agentes en secuencia y persiste
    los resultados en la tabla agent_results de la BD de la org.

    Args:
        file_id: UUID del archivo a procesar.
        org_id: UUID de la organizacion.
        user_id: UUID del usuario que inicio el proceso.

    Returns:
        dict con session_id y los resultados de cada agente:
        cleaner_output, analyzer_output, insights_output, dashboard_output.
    """
    pipeline_start = time.time()
    session_id: Optional[str] = None

    try:
        # 1. Crear sesion en la BD de la org
        with get_org_conn(org_id) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_sessions (org_id, user_id, file_id, status, started_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    RETURNING id
                    """,
                    (org_id, user_id, file_id, "running"),
                )
                session_id = str(cur.fetchone()["id"])

                # Actualizar archivo a processing
                cur.execute(
                    "UPDATE uploaded_files SET status = %s WHERE id = %s",
                    ("processing", file_id),
                )
            conn.commit()

        # 2. Configurar ADK session y runner.
        # IMPORTANTE: guardamos org_id/user_id/file_id autenticados en el
        # estado de la sesion como "trusted context". Los tools NO deben
        # confiar en parametros de org_id pasados por el LLM, deben leer
        # este valor desde tool_context.state (authenticated_org_id) y
        # rechazar si no coincide. Defensa en profundidad contra prompt
        # injection que intente pivotar a otra org.
        session_service = InMemorySessionService()
        adk_session = await session_service.create_session(
            app_name="data_pipeline",
            user_id=user_id,
            state={
                "authenticated_org_id": org_id,
                "authenticated_user_id": user_id,
                "file_id": file_id,
            },
        )

        runner = Runner(
            agent=pipeline_agent,
            app_name="data_pipeline",
            session_service=session_service,
        )

        # 3. Mensaje inicial con file_id y org_id
        initial_message = Content(
            role="user",
            parts=[
                Part(
                    text=(
                        f"Procesa el archivo con file_id={file_id} "
                        f"de la organizacion org_id={org_id}. "
                        f"Limpia los datos, analiza estadisticamente, "
                        f"genera insights de negocio y configura el dashboard."
                    )
                )
            ],
        )

        # 4. Ejecutar pipeline
        final_response = None
        async for event in runner.run_async(
            user_id=user_id,
            session_id=adk_session.id,
            new_message=initial_message,
        ):
            if event.is_final_response():
                final_response = event

        # 5. Extraer resultados del session state
        session_state = (await session_service.get_session(
            app_name="data_pipeline",
            user_id=user_id,
            session_id=adk_session.id,
        )).state

        results = {
            "cleaner_output": _extract_state_value(session_state, "cleaner_output"),
            "analyzer_output": _extract_state_value(session_state, "analyzer_output"),
            "insights_output": _extract_state_value(session_state, "insights_output"),
            "dashboard_output": _extract_state_value(session_state, "dashboard_output"),
        }

        # 6. Persistir resultados en agent_results
        pipeline_end = time.time()
        total_time_ms = int((pipeline_end - pipeline_start) * 1000)

        agent_names = [
            ("data_cleaner", "cleaner_output"),
            ("data_analyzer", "analyzer_output"),
            ("insight_generator", "insights_output"),
            ("dashboard_config", "dashboard_output"),
        ]

        with get_org_conn(org_id) as conn:
            with conn.cursor() as cur:
                for agent_name, state_key in agent_names:
                    output = results.get(state_key, {})
                    if output and not isinstance(output, str):
                        cur.execute(
                            """
                            INSERT INTO agent_results (session_id, org_id, agent_name, output, execution_time_ms)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (session_id, org_id, agent_name, Json(output), total_time_ms // 4),
                        )

                # 7. Marcar sesion como completada
                cur.execute(
                    """
                    UPDATE agent_sessions
                    SET status = %s, completed_at = NOW(), gemini_tokens_used = %s
                    WHERE id = %s
                    """,
                    ("completed", 0, session_id),
                )
            conn.commit()

        results["session_id"] = session_id
        results["total_time_ms"] = total_time_ms

        logger.info(
            f"Pipeline completado en {total_time_ms}ms para file={file_id}"
        )
        return results

    except Exception as e:
        logger.error(f"Error en pipeline: {e}", exc_info=True)

        # Marcar sesion como fallida
        if session_id:
            with get_org_conn(org_id) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE agent_sessions
                        SET status = %s, error_message = %s, completed_at = NOW()
                        WHERE id = %s
                        """,
                        ("failed", str(e)[:500], session_id),
                    )

                    # Marcar archivo como error
                    cur.execute(
                        "UPDATE uploaded_files SET status = %s, error_message = %s WHERE id = %s",
                        ("error", str(e)[:500], file_id),
                    )
                conn.commit()

        raise


# ---------------------------------------------------------------------------
# Ejecutar ETL pipeline
# ---------------------------------------------------------------------------
async def run_etl_pipeline(
    org_id: str,
    user_id: str,
    file_path: str,
    source_type: str,
    target_table: str = "",
) -> dict[str, Any]:
    """Ejecuta el ETLAgent para procesar un archivo de datos.

    Args:
        org_id: UUID de la organizacion.
        user_id: UUID del usuario.
        file_path: Ruta local del archivo a procesar.
        source_type: Tipo de fuente ('pdf', 'csv', 'excel').
        target_table: Tabla destino opcional (si no se especifica, el agente la determina).

    Returns:
        dict con etl_output y session_id.
    """
    try:
        session_service = InMemorySessionService()
        adk_session = await session_service.create_session(
            app_name="etl_pipeline",
            user_id=user_id,
            state={
                # authenticated_* son el contexto de confianza, no modificable
                # por el LLM. Los tools deben validar contra estos valores.
                "authenticated_org_id": org_id,
                "authenticated_user_id": user_id,
                "org_id": org_id,
                "user_id": user_id,
                "file_path": file_path,
                "source_type": source_type,
                "target_table": target_table,
            },
        )

        runner = Runner(
            agent=etl_agent,
            app_name="etl_pipeline",
            session_service=session_service,
        )

        message_text = (
            f"Procesa el archivo en '{file_path}' (tipo: {source_type}) "
            f"para la organizacion org_id={org_id}."
        )
        if target_table:
            message_text += f" Carga los datos en la tabla '{target_table}'."

        initial_message = Content(
            role="user",
            parts=[Part(text=message_text)],
        )

        response_text = ""
        async for event in runner.run_async(
            user_id=user_id,
            session_id=adk_session.id,
            new_message=initial_message,
        ):
            if event.is_final_response():
                if event.content and event.content.parts:
                    response_text = event.content.parts[0].text

        # Extract ETL output from state
        session = await session_service.get_session(
            app_name="etl_pipeline",
            user_id=user_id,
            session_id=adk_session.id,
        )
        etl_output = _extract_state_value(session.state, "etl_output")

        return {
            "etl_output": etl_output,
            "response": response_text,
            "session_id": adk_session.id,
        }

    except Exception as e:
        logger.error(f"Error en ETL pipeline: {e}", exc_info=True)
        raise


# ---------------------------------------------------------------------------
# Ejecutar chat
# ---------------------------------------------------------------------------
async def run_chat(
    message: str,
    org_id: str,
    user_id: str,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """Ejecuta el ChatAgent para responder una pregunta del usuario.

    Args:
        message: Pregunta del usuario en lenguaje natural.
        org_id: UUID de la organizacion.
        user_id: UUID del usuario.
        session_id: ID de sesion ADK existente (para mantener contexto).

    Returns:
        dict con 'response' (texto de respuesta), 'session_id' (para continuidad).
    """
    try:
        # C6: use module-level singleton to preserve conversation context
        session_service = _chat_session_service

        if session_id:
            # Intentar recuperar sesion existente
            existing = await session_service.get_session(
                app_name="chat",
                user_id=user_id,
                session_id=session_id,
            )
            if not existing:
                session_id = None

        if not session_id:
            adk_session = await session_service.create_session(
                app_name="chat",
                user_id=user_id,
                state={
                    "authenticated_org_id": org_id,
                    "authenticated_user_id": user_id,
                    "org_id": org_id,
                },
            )
            session_id = adk_session.id

        runner = Runner(
            agent=chat_agent,
            app_name="chat",
            session_service=session_service,
        )

        # C4: sanitize user message before embedding in prompt
        safe_message = _sanitize_user_message(message)
        user_message = Content(
            role="user",
            parts=[
                Part(
                    text=(
                        f"[org_id={org_id}] {safe_message}"
                    )
                )
            ],
        )

        response_text = ""
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=user_message,
        ):
            if event.is_final_response():
                if event.content and event.content.parts:
                    response_text = event.content.parts[0].text

        # C5: use asyncio.to_thread to avoid blocking the event loop with
        # the sync psycopg2 connection (same pattern as run_analytical).
        def _persist_chat_message():
            with get_org_conn(org_id) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO chat_messages (org_id, user_id, role, content)
                        VALUES (%s, %s, %s, %s), (%s, %s, %s, %s)
                        """,
                        (
                            org_id, user_id, "user", message,
                            org_id, user_id, "assistant", response_text,
                        ),
                    )
                conn.commit()

        await asyncio.to_thread(_persist_chat_message)

        return {
            "response": response_text,
            "session_id": session_id,
        }

    except Exception as e:
        logger.error("Error en run_chat", exc_info=True)
        return {
            "response": (
                "Lo siento, hubo un error al procesar tu pregunta. "
                "Por favor intenta de nuevo."
            ),
            "error": "internal_error",
            "message": "No pudimos procesar tu solicitud. Intenta de nuevo.",
        }


# ---------------------------------------------------------------------------
# Ejecutar analytical agent
# ---------------------------------------------------------------------------
async def run_analytical(
    message: str,
    org_id: str,
    user_id: str,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """Ejecuta el AnalyticalAgent para analisis profundo de datos.

    Args:
        message: Pregunta o solicitud de analisis del usuario.
        org_id: UUID de la organizacion.
        user_id: UUID del usuario.
        session_id: ID de sesion ADK existente (para mantener contexto).

    Returns:
        dict con 'response' (texto de respuesta), 'session_id' (para continuidad).
    """
    try:
        # C6: use module-level singleton to preserve conversation context
        session_service = _analytical_session_service

        if session_id:
            existing = await session_service.get_session(
                app_name="analytical",
                user_id=user_id,
                session_id=session_id,
            )
            if not existing:
                session_id = None

        if not session_id:
            adk_session = await session_service.create_session(
                app_name="analytical",
                user_id=user_id,
                state={
                    "authenticated_org_id": org_id,
                    "authenticated_user_id": user_id,
                    "org_id": org_id,
                },
            )
            session_id = adk_session.id

        runner = Runner(
            agent=analytical_agent,
            app_name="analytical",
            session_service=session_service,
        )

        # C4: sanitize user message before embedding in prompt
        safe_message = _sanitize_user_message(message)
        user_message = Content(
            role="user",
            parts=[
                Part(
                    text=(
                        f"[org_id={org_id}] {safe_message}"
                    )
                )
            ],
        )

        response_text = ""
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=user_message,
        ):
            if event.is_final_response():
                if event.content and event.content.parts:
                    response_text = event.content.parts[0].text

        # Guardar en chat_messages (BD de la org).
        # Usamos asyncio.to_thread para no bloquear el event loop de
        # FastAPI con la conexion sync psycopg2.
        def _persist_analytical_messages():
            with get_org_conn(org_id) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO chat_messages (org_id, user_id, role, content)
                        VALUES (%s, %s, %s, %s), (%s, %s, %s, %s)
                        """,
                        (
                            org_id, user_id, "user", message,
                            org_id, user_id, "analytical_agent", response_text,
                        ),
                    )
                conn.commit()

        await asyncio.to_thread(_persist_analytical_messages)

        return {
            "response": response_text,
            "session_id": session_id,
        }

    except Exception as e:
        logger.error("Error en run_analytical", exc_info=True)
        return {
            "response": (
                "Lo siento, hubo un error al procesar tu solicitud de analisis. "
                "Por favor intenta de nuevo."
            ),
            "error": "internal_error",
            "message": "No pudimos procesar tu solicitud. Intenta de nuevo.",
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _extract_state_value(state: dict, key: str) -> dict | str:
    """Extrae un valor del state, parseando JSON si es necesario."""
    value = state.get(key, {})
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value
