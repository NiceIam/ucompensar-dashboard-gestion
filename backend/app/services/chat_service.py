import json
import logging
import math
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from app.config import get_settings
from app.database import get_org_pool
from app.models.schemas import ChatHistoryResponse, ChatMessageResponse
from app.utils import with_retry

logger = logging.getLogger(__name__)


async def _build_context(org_id: str, file_id: str | None) -> str:
    """Construye contexto completo del cliente — memoria de la org."""
    from app.database import get_main_pool

    context_parts: list[str] = []

    # Info de la organizacion
    main_pool = await get_main_pool()
    async with main_pool.acquire() as conn:
        try:
            org_uuid = uuid.UUID(org_id)
        except ValueError:
            org_uuid = org_id
        org = await conn.fetchrow(
            "SELECT name, sector, size, city, business_type, plan_type FROM organizations WHERE id = $1",
            org_uuid,
        )
    if org:
        context_parts.append(
            f"Empresa: {org['name']} | Sector: {org['sector']} | Tamaño: {org['size']} | "
            f"Ciudad: {org['city']} | Tipo negocio: {org['business_type'] or 'no definido'}"
        )

    # Tablas y datos de la org
    pool = await get_org_pool(org_id)
    async with pool.acquire() as conn:
        tables = await conn.fetch(
            "SELECT id, table_name, display_name, row_count, columns_definition FROM org_data_tables"
        )
        total_records = sum((t["row_count"] or 0) for t in tables)

        context_parts.append(
            f"Tablas: {len(tables)} | Registros totales: {total_records}"
        )
        for t in tables:
            cols = t["columns_definition"]
            if isinstance(cols, str):
                cols = json.loads(cols)
            col_names = [c["name"] for c in cols] if cols else []
            context_parts.append(
                f"  - {t['display_name']} ({t['row_count'] or 0} filas): {', '.join(col_names[:8])}"
            )

        # Muestra de datos reales (primeras filas de cada tabla con datos)
        for t in tables:
            if (t["row_count"] or 0) > 0:
                rows = await conn.fetch(
                    "SELECT data FROM org_data_rows WHERE table_id = $1 LIMIT 3",
                    t["id"],
                )
                if rows:
                    samples = []
                    for r in rows:
                        data = r["data"]
                        if isinstance(data, str):
                            data = json.loads(data)
                        samples.append(str(data)[:200])
                    context_parts.append(
                        f"  Muestra {t['display_name']}: {'; '.join(samples)}"
                    )

        # ETL jobs recientes
        jobs = await conn.fetch(
            "SELECT filename, status, rows_loaded FROM etl_jobs ORDER BY created_at DESC LIMIT 5"
        )
        if jobs:
            context_parts.append(f"ETL recientes: {len(jobs)} jobs")

        # Historial de chat (ultimos 5 mensajes para contexto de conversacion)
        recent_msgs = await conn.fetch(
            "SELECT role, content FROM chat_messages ORDER BY created_at DESC LIMIT 5"
        )
        if recent_msgs:
            context_parts.append("Conversacion reciente:")
            for m in reversed(recent_msgs):
                context_parts.append(f"  {m['role']}: {m['content'][:150]}")

    return "\n".join(context_parts)


@with_retry(
    max_retries=3, retryable_exceptions=(ConnectionError, TimeoutError, OSError)
)
async def _call_gemini(system_context: str, user_message: str, org_id: str) -> str:
    """Llama a Gemini o genera respuesta local si no hay API key."""
    settings = get_settings()

    # Si no hay API key configurada, generar respuesta local
    if not settings.GOOGLE_API_KEY or settings.GOOGLE_API_KEY == "tu-google-api-key":
        return await _local_chat_response(system_context, user_message, org_id)

    try:
        from google import genai
        from google.genai import types as genai_types

        client = genai.Client(api_key=settings.GOOGLE_API_KEY)

        prompt = (
            "Eres un asistente de analisis de datos para una PYME. "
            "Responde en espanol de forma clara y concisa.\n\n"
            f"Contexto de datos de la empresa:\n{system_context}\n\n"
            f"Pregunta del usuario: {user_message}"
        )

        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                max_output_tokens=1024,
                temperature=0.4,
            ),
        )
        return response.text or "No pude generar una respuesta en este momento."

    except ConnectionError as e:
        logger.warning(
            "Connection error calling Gemini: %s. Falling back to local response.", e
        )
        return await _local_chat_response(system_context, user_message, org_id)
    except TimeoutError as e:
        logger.warning("Timeout calling Gemini: %s. Falling back to local response.", e)
        return await _local_chat_response(system_context, user_message, org_id)
    except Exception as exc:
        logger.error("Unexpected error calling Gemini: %s", exc)
        return await _local_chat_response(system_context, user_message, org_id)


async def _local_chat_response(context: str, user_message: str, org_id: str) -> str:
    """Respuesta local inteligente basada en datos reales sin LLM."""
    from app.database import get_main_pool

    pool = await get_org_pool(org_id)
    msg_lower = user_message.lower()

    # Obtener info de la org
    main_pool = await get_main_pool()
    try:
        org_uuid = uuid.UUID(org_id)
    except ValueError:
        org_uuid = org_id
    async with main_pool.acquire() as conn:
        org = await conn.fetchrow(
            "SELECT name, sector, size, city FROM organizations WHERE id = $1",
            org_uuid,
        )
    org_name = org["name"] if org else "tu empresa"

    async with pool.acquire() as conn:
        tables = await conn.fetch(
            "SELECT id, table_name, display_name, row_count FROM org_data_tables"
        )
        total_records = sum((t["row_count"] or 0) for t in tables)
        tables_info = [
            f"- {t['display_name']}: {t['row_count'] or 0} registros" for t in tables
        ]

        jobs = await conn.fetch(
            "SELECT status, filename FROM etl_jobs ORDER BY created_at DESC LIMIT 5"
        )
        messages_count = await conn.fetchval("SELECT count(*) FROM chat_messages")

        # Buscar datos reales relevantes al mensaje
        relevant_data = []
        for t in tables:
            if (t["row_count"] or 0) > 0 and (
                t["table_name"] in msg_lower
                or t["display_name"].lower() in msg_lower
                or any(w in msg_lower for w in t["table_name"].split("_"))
            ):
                rows = await conn.fetch(
                    "SELECT data FROM org_data_rows WHERE table_id = $1 LIMIT 5",
                    t["id"],
                )
                relevant_data.append(
                    {
                        "table": t["display_name"],
                        "count": t["row_count"],
                        "samples": [
                            r["data"]
                            if isinstance(r["data"], dict)
                            else json.loads(r["data"])
                            for r in rows
                        ],
                    }
                )

    # Si hay datos relevantes, mostrarlos
    if relevant_data:
        parts = [f"**Datos encontrados para '{user_message}':**\n"]
        for rd in relevant_data:
            parts.append(f"\n**{rd['table']}** ({rd['count']} registros):")
            for i, sample in enumerate(rd["samples"][:5], 1):
                vals = ", ".join(f"{k}: {v}" for k, v in list(sample.items())[:4])
                parts.append(f"  {i}. {vals}")
        parts.append(
            f"\nTotal en {org_name}: {total_records} registros en {len(tables)} tablas."
        )
        return "\n".join(parts)

    # Respuestas contextuales basadas en keywords
    if any(w in msg_lower for w in ["hola", "buenos", "hey", "saludos"]):
        return (
            f"Hola! Soy tu asistente de datos para **{org_name}**. "
            f"Tienes {len(tables)} tablas con {total_records} registros.\n\n"
            f"Tablas:\n" + "\n".join(tables_info) + "\n\n"
            "Preguntame sobre tus datos, sube archivos, o pide reportes."
        )

    if any(w in msg_lower for w in ["ventas", "venta", "vendido"]):
        return (
            f"**{org_name} — Datos disponibles:**\n" + "\n".join(tables_info) + "\n\n"
            f"Total: {total_records} registros\n\n"
            "Para analizar ventas, sube un CSV/Excel con el boton de adjuntar."
        )

    if any(w in msg_lower for w in ["datos", "tabla", "registros", "informacion"]):
        return (
            f"Resumen de tus datos:\n\n"
            f"Tablas configuradas: {len(tables)}\n" + "\n".join(tables_info) + "\n\n"
            f"Registros totales: {total_records}\n"
            f"Archivos ETL procesados: {len(jobs)}\n\n"
            "Para cargar mas datos, sube un archivo CSV, Excel o PDF."
        )

    if any(w in msg_lower for w in ["reporte", "informe", "resumen", "analisis"]):
        return (
            f"Resumen de tu empresa:\n\n"
            f"Tablas: {len(tables)}\n" + "\n".join(tables_info) + "\n"
            f"Registros totales: {total_records}\n"
            f"Jobs ETL: {len(jobs)} ({sum(1 for j in jobs if j['status'] == 'completed')} completados)\n\n"
            "Para generar un reporte mas detallado, carga datos primero y luego usa "
            "la seccion de Analisis IA."
        )

    if any(w in msg_lower for w in ["cargar", "subir", "importar", "archivo"]):
        return (
            "Para cargar datos a tu empresa:\n\n"
            "1. Haz clic en el boton de adjuntar archivo (icono de clip)\n"
            "2. Selecciona un archivo CSV, Excel (.xlsx) o PDF\n"
            "3. El sistema lo procesara automaticamente\n"
            "4. Los datos se cargaran en la tabla correspondiente\n\n"
            "Formatos soportados: CSV, Excel (.xlsx, .xls), PDF con tablas"
        )

    # Respuesta generica
    return (
        f"Entiendo tu pregunta. Aqui esta un resumen de tu empresa:\n\n"
        f"Tablas: {len(tables)}\n" + "\n".join(tables_info) + "\n\n"
        f"Total registros: {total_records}\n\n"
        "Para obtener analisis mas profundos, puedes:\n"
        "- Cargar datos usando archivos CSV/Excel\n"
        "- Usar la seccion de Analisis IA\n"
        "- Hacer preguntas especificas sobre tus ventas, productos o clientes"
    )


_ORG_QUOTA_WINDOW = timedelta(hours=24)

# Devuelve la fila numero `limite` (OFFSET limite-1) de los mensajes de usuario dentro de la ventana,
# de mas nuevo a mas viejo: existe <=> ya se alcanzo el tope, y su created_at es el mensaje que, al
# salir de la ventana, libera un cupo. Una sola consulta da "excedido?" y "cuando se libera".
_USER_QUOTA_SQL = (
    "SELECT created_at FROM chat_messages "
    "WHERE role = 'user' AND user_id = $1 AND created_at > $2 "
    "ORDER BY created_at DESC OFFSET $3 LIMIT 1"
)
_ORG_QUOTA_SQL = (
    "SELECT created_at FROM chat_messages "
    "WHERE role = 'user' AND created_at > $1 "
    "ORDER BY created_at DESC OFFSET $2 LIMIT 1"
)


def _quota_exceeded(
    code: str, message: str, limit: int, window: timedelta, release_at: datetime, now: datetime
) -> HTTPException:
    retry_after = max(1, math.ceil((release_at - now).total_seconds()))
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "code": code,
            "message": message.format(retry=_human_wait(retry_after), limit=limit, window=_human_wait(int(window.total_seconds()))),
            "retry_after_seconds": retry_after,
            "retry_at": release_at.astimezone(timezone.utc).isoformat(),
            "limit": limit,
        },
        headers={"Retry-After": str(retry_after)},
    )


def _human_wait(seconds: int) -> str:
    if seconds < 90:
        return f"{seconds} segundos"
    if seconds < 5400:
        return f"{math.ceil(seconds / 60)} minutos"
    return f"{math.ceil(seconds / 3600)} horas"


# Lock consultivo de transaccion que serializa "contar + insertar" de los mensajes de usuario. La BD ya
# es una por organizacion y los locks consultivos son por base de datos, asi que esta clave constante
# equivale a un lock por organizacion.
_QUOTA_LOCK_SQL = "SELECT pg_advisory_xact_lock(hashtext('chat_messages_quota'))"
_INSERT_USER_MESSAGE_SQL = """
    INSERT INTO chat_messages (id, user_id, role, content, created_at)
    VALUES ($1, $2, 'user', $3, $4)
    """


async def reserve_user_message(pool, user_id: str | None, content: str, now: datetime) -> str:
    """Verifica los topes de uso del chat Y guarda el mensaje del usuario, de forma atomica.

    Devuelve el id del mensaje guardado. Si se excede un tope: 429 y NO se guarda nada. Se llama antes de
    cualquier gasto (Gemini); lo usan el chat y analytics/query, que consumen la misma cuota.
    - Los topes se cuentan en Postgres para que valgan entre instancias serverless.
    - Chequeo + INSERT van en UNA transaccion con pg_advisory_xact_lock: sin eso, peticiones simultaneas
      pasaban todas el chequeo antes de que alguna insertara (30 concurrentes con tope 5 llamaron a
      Gemini 13 veces). El lock solo cubre estas consultas (milisegundos); la llamada a Gemini ocurre
      despues, fuera de la transaccion, y NO se serializa.
    - Se revisa primero el tope diario de la organizacion (protege la API key compartida): si ambos
      estan excedidos, avisar solo del de 1 minuto seria enganoso porque el diario sigue bloqueando.
    - `now` es la hora UTC de la aplicacion, la misma con la que se guarda created_at.
    - Politica ante error de BD: NO se captura. Fallar cerrado protege el costo, y con la BD caida
      el resto de send_message falla igual.
    - Limitacion conocida: /chat/upload guarda una fila role='user' por archivo, y chat_messages no tiene
      ninguna columna que distinga mensajes de archivo (solo id, user_id, role, content, created_at), asi
      que cada subida tambien cuenta para estos topes sin llamar a Gemini.
    """
    settings = get_settings()
    org_limit = settings.CHAT_ORG_DAILY_MESSAGES
    user_limit = settings.CHAT_USER_MAX_MESSAGES
    user_window = timedelta(seconds=settings.CHAT_USER_WINDOW_SECONDS)
    user_msg_id = str(uuid.uuid4())

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(_QUOTA_LOCK_SQL)
            if org_limit > 0:
                row = await conn.fetchrow(_ORG_QUOTA_SQL, now - _ORG_QUOTA_WINDOW, org_limit - 1)
                if row:
                    raise _quota_exceeded(
                        "quota_org_daily",
                        "La organización alcanzó el límite diario de {limit} mensajes del asistente. "
                        "Se libera en aproximadamente {retry}.",
                        org_limit, _ORG_QUOTA_WINDOW, row["created_at"] + _ORG_QUOTA_WINDOW, now,
                    )
            if user_limit > 0 and user_id:
                row = await conn.fetchrow(_USER_QUOTA_SQL, user_id, now - user_window, user_limit - 1)
                if row:
                    raise _quota_exceeded(
                        "rate_limit_user",
                        "Alcanzaste el límite de {limit} mensajes del asistente cada {window}. "
                        "Intenta de nuevo en {retry}.",
                        user_limit, user_window, row["created_at"] + user_window, now,
                    )
            await conn.execute(_INSERT_USER_MESSAGE_SQL, user_msg_id, user_id, content, now)
    return user_msg_id


async def send_message(
    org_id: str,
    user_id: str,
    content: str,
    file_id: str | None = None,
) -> tuple[ChatMessageResponse, ChatMessageResponse]:
    """Envía mensaje al ChatAgent y retorna par (user_msg, assistant_msg)."""
    pool = await get_org_pool(org_id)
    now = datetime.now(timezone.utc)

    # Historial reciente para contexto. Se lee ANTES de guardar el mensaje actual:
    # process_with_gemini ya envia `content` como mensaje nuevo, y leerlo despues lo
    # duplicaria como ultimo turno del historial.
    async with pool.acquire() as conn:
        recent = await conn.fetch(
            "SELECT role, content FROM chat_messages ORDER BY created_at DESC LIMIT 8"
        )
    chat_history = [
        {"role": r["role"], "content": r["content"]} for r in reversed(recent)
    ]

    # Verifica topes y guarda el mensaje del usuario (atomico); si hay 429 no se guarda nada ni se llama a Gemini.
    user_msg_id = await reserve_user_message(pool, user_id, content, now)

    # Usar Gemini con tools
    from app.services.agent_tools_service import process_with_gemini

    result = await process_with_gemini(org_id, content, chat_history)

    ai_response = result["text"]

    # Si hay charts, agregarlos como bloques especiales en el contenido
    if result.get("charts"):
        for chart in result["charts"]:
            ai_response += f"\n```chart\n{json.dumps(chart, ensure_ascii=False)}\n```"

    # Tableros creados en este mensaje: el bloque (con el id) lo arma SOLO el servidor; cualquier bloque
    # equivalente escrito por el modelo ya se descarto en process_with_gemini.
    for board in result.get("dashboards") or []:
        ai_response += f"\n```dashboard\n{json.dumps(board, ensure_ascii=False)}\n```"

    # Guardar respuesta del asistente
    assistant_msg_id = str(uuid.uuid4())
    completed_at = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, created_at) VALUES ($1, $2, 'assistant', $3, $4)",
            assistant_msg_id,
            user_id,
            ai_response,
            completed_at,
        )

    user_response = ChatMessageResponse(
        message_id=user_msg_id,
        role="user",
        content=content,
        created_at=now,
    )
    assistant_response = ChatMessageResponse(
        message_id=assistant_msg_id,
        role="assistant",
        content=ai_response,
        created_at=completed_at,
    )

    return user_response, assistant_response


async def send_file_message(
    org_id: str,
    user_id: str,
    file,
    user_message: str | None = None,
) -> ChatMessageResponse:
    """Procesa un archivo subido via chat con el Schema Agent."""
    from app.services.file_service import parse_file
    from app.services.schema_agent_service import smart_upload

    pool = await get_org_pool(org_id)
    now = datetime.now(timezone.utc)
    filename = file.filename or "archivo.csv"

    # Guardar mensaje del usuario. OJO: esta fila role='user' cuenta para los topes de uso del chat
    # (ver reserve_user_message) aunque aqui no se llame a Gemini; no hay columna para distinguirla.
    user_text = user_message or f"Subiendo archivo: {filename}"
    user_msg_id = str(uuid.uuid4())
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, created_at) VALUES ($1, $2, 'user', $3, $4)",
            user_msg_id,
            user_id,
            user_text,
            now,
        )

    # Procesar archivo con Schema Agent
    try:
        df = await parse_file(file)

        # Guardar archivo en uploaded_files + carpeta local
        from app.services.file_service import store_file, validate_file, _infer_columns

        file_type, size_bytes = await validate_file(file, df)
        columns = _infer_columns(df)
        file_id = await store_file(
            upload=file,
            org_id=org_id,
            file_type=file_type,
            columns=columns,
            rows_count=len(df),
            size_bytes=size_bytes,
        )

        result = await smart_upload(df, org_id, filename)

        # Actualizar status del archivo
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE uploaded_files SET status = 'ready', rows_count = $1 WHERE id = $2",
                result.get("rows_inserted", len(df)),
                file_id,
            )

        # Si la organizacion aun no tiene tableros, se sugieren (no lanza ni espera mas que su tope de tiempo).
        if result.get("rows_inserted"):
            from app.services.dashboard_suggest_service import auto_suggest_after_upload
            await auto_suggest_after_upload(org_id)

        # Construir respuesta descriptiva
        actions_text = "\n".join(f"- {a['detail']}" for a in result["actions"])
        analysis = result["analysis"]
        cols_text = ", ".join(c["clean_name"] for c in analysis["columns"][:8])
        if len(analysis["columns"]) > 8:
            cols_text += f" y {len(analysis['columns']) - 8} mas"

        if result["status"] == "created_new_table":
            response_text = (
                f"**Archivo procesado: {filename}**\n\n"
                f"Analice el archivo y cree una nueva tabla **{result['table_name']}** "
                f"con {analysis['column_count']} columnas.\n\n"
                f"**Columnas detectadas:** {cols_text}\n\n"
                f"**Acciones realizadas:**\n{actions_text}\n\n"
                f"**Resultado:** {result['rows_inserted']} registros cargados exitosamente. "
                f"Total en tabla: {result['total_rows']} registros."
            )
        else:
            response_text = (
                f"**Archivo procesado: {filename}**\n\n"
                f"Analice el archivo y encontre que coincide con la tabla existente "
                f"**{result['table_name']}** (coincidencia: {int(result.get('match_score', 0) * 100)}%).\n\n"
                f"**Columnas detectadas:** {cols_text}\n\n"
                f"**Acciones realizadas:**\n{actions_text}\n\n"
                f"**Resultado:** {result['rows_inserted']} registros cargados exitosamente. "
                f"Total en tabla: {result['total_rows']} registros."
            )

    except Exception as exc:
        logger.error("Error procesando archivo en chat: %s", exc)
        response_text = (
            f"**Error al procesar {filename}**\n\n"
            f"No pude procesar el archivo: {str(exc)[:200]}\n\n"
            "Asegurate de que sea un CSV o Excel valido con encabezados en la primera fila."
        )

    # Guardar respuesta
    assistant_msg_id = str(uuid.uuid4())
    completed_at = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, created_at) VALUES ($1, $2, 'assistant', $3, $4)",
            assistant_msg_id,
            user_id,
            response_text,
            completed_at,
        )

    return ChatMessageResponse(
        message_id=assistant_msg_id,
        role="assistant",
        content=response_text,
        created_at=completed_at,
    )


async def get_history(org_id: str, limit: int = 50) -> ChatHistoryResponse:
    pool = await get_org_pool(org_id)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, role, content, created_at
            FROM chat_messages
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )

    # Se piden los ULTIMOS `limit` mensajes (DESC) y se devuelven en orden cronologico.
    rows = list(reversed(rows))

    messages = [
        ChatMessageResponse(
            message_id=str(row["id"]),
            role=row["role"],
            content=row["content"],
            created_at=row["created_at"],
        )
        for row in rows
    ]

    return ChatHistoryResponse(messages=messages, total=len(messages))
