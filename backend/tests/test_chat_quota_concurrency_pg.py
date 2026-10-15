"""Concurrencia REAL de la cuota del chat contra un Postgres desechable — PI0320251.

Se OMITE por defecto: necesita un Postgres local, descartable y accesible sin contrasena (trust) cuyo
puerto se indica en CHAT_QUOTA_TEST_PG_PORT (usuario en CHAT_QUOTA_TEST_PG_USER, por defecto 'tester').
Solo acepta 127.0.0.1 y crea/borra su propia base 'chat_quota_test_<uuid>'. NUNCA apuntar a Neon ni a
ningun servidor compartido. Gemini sigue mockeado: nunca hay red externa.

Ejemplo (PowerShell): $env:CHAT_QUOTA_TEST_PG_PORT=54871; pytest tests/test_chat_quota_concurrency_pg.py
"""

import asyncio
import os
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

PORT = os.environ.get("CHAT_QUOTA_TEST_PG_PORT")
pytestmark = pytest.mark.skipif(not PORT, reason="define CHAT_QUOTA_TEST_PG_PORT para usar un Postgres local desechable")

asyncpg = pytest.importorskip("asyncpg")

HOST = "127.0.0.1"  # fijo a proposito
REPETITIONS = 5


@pytest.fixture
async def pg_pool():
    from app import database

    user = os.environ.get("CHAT_QUOTA_TEST_PG_USER", "tester")
    dbname = f"chat_quota_test_{uuid.uuid4().hex[:8]}"
    admin = await asyncpg.connect(host=HOST, port=int(PORT), user=user, database="postgres")
    await admin.execute(f'CREATE DATABASE "{dbname}"')
    pool = await asyncpg.create_pool(host=HOST, port=int(PORT), user=user, database=dbname, min_size=1, max_size=40)
    try:
        async with pool.acquire() as conn:
            await conn.execute(database.ORG_BASE_SCHEMA_SQL)
        yield pool
    finally:
        await pool.close()
        await admin.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        await admin.close()


async def _run(pool, users: list[str], *, user_cap: int, org_cap: int):
    from app.services import chat_service as cs

    gemini_calls = 0

    async def fake_gemini(org_id, content, history):
        nonlocal gemini_calls
        gemini_calls += 1
        await asyncio.sleep(0.2)
        return {"text": "ok"}

    async def get_pool(_org):
        return pool

    settings = SimpleNamespace(CHAT_USER_MAX_MESSAGES=user_cap, CHAT_USER_WINDOW_SECONDS=60, CHAT_ORG_DAILY_MESSAGES=org_cap)
    with patch.object(cs, "get_org_pool", get_pool), patch.object(cs, "get_settings", return_value=settings), patch(
        "app.services.agent_tools_service.process_with_gemini", fake_gemini
    ):
        results = await asyncio.gather(
            *[cs.send_message("org", u, f"m{i}") for i, u in enumerate(users)], return_exceptions=True
        )
    ok = sum(1 for r in results if not isinstance(r, Exception))
    rejected = sum(1 for r in results if isinstance(r, HTTPException) and r.status_code == 429)
    other = [r for r in results if isinstance(r, Exception) and not (isinstance(r, HTTPException) and r.status_code == 429)]
    return ok, rejected, gemini_calls, other


@pytest.mark.parametrize("rep", range(REPETITIONS))
async def test_30_concurrentes_de_un_usuario_con_tope_5_dejan_pasar_exactamente_5(pg_pool, rep):
    user = str(uuid.uuid4())

    ok, rejected, gemini_calls, other = await _run(pg_pool, [user] * 30, user_cap=5, org_cap=300)

    assert (ok, rejected, gemini_calls, other) == (5, 25, 5, [])
    assert await pg_pool.fetchval("SELECT count(*) FROM chat_messages WHERE role = 'user'") == 5


@pytest.mark.parametrize("rep", range(REPETITIONS))
async def test_30_concurrentes_de_30_usuarios_con_tope_diario_de_org_5_dejan_pasar_exactamente_5(pg_pool, rep):
    users = [str(uuid.uuid4()) for _ in range(30)]

    ok, rejected, gemini_calls, other = await _run(pg_pool, users, user_cap=100, org_cap=5)

    assert (ok, rejected, gemini_calls, other) == (5, 25, 5, [])
    assert await pg_pool.fetchval("SELECT count(*) FROM chat_messages WHERE role = 'user'") == 5
