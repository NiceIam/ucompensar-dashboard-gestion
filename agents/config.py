"""
Configuracion compartida para los agentes de IA del pipeline PI0320251.

Carga variables de entorno, configura conexiones psycopg2 a PostgreSQL local
(BD principal y BDs por organizacion), safety settings de Gemini,
y utilidades de retry.
"""

import os
import time
import asyncio
import logging
from functools import wraps
from typing import TypeVar, Callable

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from google.genai.types import HarmCategory, HarmBlockThreshold

load_dotenv()

logger = logging.getLogger("agents")

# ---------------------------------------------------------------------------
# Variables de entorno
# ---------------------------------------------------------------------------
GOOGLE_API_KEY: str = os.environ.get("GOOGLE_API_KEY", "")
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

# PostgreSQL
DB_HOST: str = os.environ.get("DATABASE_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DATABASE_PORT", "5432"))
DB_USER: str = os.environ.get("DATABASE_USER", "postgres")
DB_PASSWORD: str = os.environ.get("DATABASE_PASSWORD", "postgres")
DB_NAME: str = os.environ.get("DATABASE_NAME", "pi_main")

# ---------------------------------------------------------------------------
# Temperaturas por agente
# ---------------------------------------------------------------------------
AGENT_TEMPERATURES: dict[str, float] = {
    "data_cleaner": 0.0,
    "etl_agent": 0.1,
    "data_analyzer": 0.1,
    "insight_generator": 0.5,
    "dashboard_config": 0.3,
    "chat_agent": 0.4,
    "analytical_agent": 0.2,
}

# ---------------------------------------------------------------------------
# Safety settings para Gemini — permisivos para datos empresariales
# ---------------------------------------------------------------------------
SAFETY_SETTINGS: dict = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}


# ---------------------------------------------------------------------------
# Conexiones psycopg2
# ---------------------------------------------------------------------------
def get_main_conn():
    """Retorna una conexion a la BD principal (pi_main).

    Usa RealDictCursor para que fetchall()/fetchone() retornen dicts.
    Siempre usar con context manager: ``with get_main_conn() as conn:``
    """
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        cursor_factory=RealDictCursor,
    )


def get_org_conn(org_id: str):
    """Retorna una conexion a la BD de una organizacion (org_<uuid>).

    El nombre de la BD se genera reemplazando guiones del UUID por
    underscores: org_id='abc-def' -> dbname='org_abc_def'.

    Args:
        org_id: UUID de la organizacion (con o sin guiones).
    """
    db_name = f"org_{org_id.replace('-', '_')}"
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=db_name,
        cursor_factory=RealDictCursor,
    )


# ---------------------------------------------------------------------------
# Retry con backoff exponencial (sync)
# ---------------------------------------------------------------------------
T = TypeVar("T")


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_exceptions: tuple = (ConnectionError, TimeoutError, psycopg2.OperationalError),
) -> Callable:
    """Decorador para retry con backoff exponencial (sync)."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        logger.warning(
                            f"[Retry] {func.__name__} intento {attempt + 1}/{max_retries} "
                            f"fallo: {e}. Reintentando en {delay:.1f}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"[Retry] {func.__name__} agoto {max_retries} reintentos."
                        )
            raise last_exception  # type: ignore[misc]

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Retry con backoff exponencial (async)
# ---------------------------------------------------------------------------
def with_retry_async(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_exceptions: tuple = (ConnectionError, TimeoutError, psycopg2.OperationalError),
) -> Callable:
    """Decorador para retry con backoff exponencial (async)."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        logger.warning(
                            f"[Retry] {func.__name__} intento {attempt + 1}/{max_retries} "
                            f"fallo: {e}. Reintentando en {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"[Retry] {func.__name__} agoto {max_retries} reintentos."
                        )
            raise last_exception  # type: ignore[misc]

        return wrapper

    return decorator
