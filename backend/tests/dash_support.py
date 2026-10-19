"""Soporte de las pruebas de tableros creados por la IA — PI0320251.

- `load_csv`: carga un CSV REAL del repo (test-data/ferreteria) en la BD emulada, con numeros como numeros
  (como los deja la ingesta).
- `env`: BDs en memoria + oraculo en pandas como motor + ajustes con la herramienta de tableros ENCENDIDA.
- Valores esperados A MANO: se calcularon con el modulo `csv` de Python sobre los mismos archivos (sin el motor)
  y estan escritos como literales en las pruebas.
"""

import csv
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.fake_gemini import make_fake_genai
from tests.fake_org_db import FakeMainPool, FakeOrgDBs
from tests.query_oracle import fake_run_plans

ORG_A = "550e8400-e29b-41d4-a716-446655440000"
ORG_B = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
SECRET_KEY = "AIzaSy-TEST-SECRET-KEY-123"
FERRETERIA = Path(__file__).resolve().parents[2] / "test-data" / "ferreteria"

VENTAS_TYPES = {"fecha": "date", "cantidad": "integer", "precio_unitario": "number", "total": "number"}
PRODUCTOS_TYPES = {"precio_compra": "number", "precio_venta": "number", "stock": "integer"}


def _cast(value: str, kind: str):
    if value == "":
        return None
    if kind == "integer":
        return int(value)
    if kind == "number":
        number = float(value)
        return int(number) if number == int(number) else number
    return value


def read_csv(path: Path, types: dict) -> tuple[list[str], list[dict]]:
    with open(path, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = [{c: _cast(r[c], types.get(c, "text")) for c in columns} for r in reader]
    return columns, rows


def load_csv(db, name: str, filename: str, types: dict, display: str | None = None):
    columns, rows = read_csv(FERRETERIA / filename, types)
    return db.add_table(name, columns, rows, display_name=display or name.title(), column_types=types)


def load_ferreteria(db):
    """ventas (40 filas) y productos (30) de test-data/ferreteria."""
    ventas = load_csv(db, "ventas", "ventas.csv", VENTAS_TYPES, "Ventas")
    productos = load_csv(db, "productos", "productos.csv", PRODUCTOS_TYPES, "Productos")
    return ventas, productos


@pytest.fixture
def settings_stub():
    return SimpleNamespace(
        GOOGLE_API_KEY=SECRET_KEY, GEMINI_MODEL="gemini-test-model", GEMINI_TIMEOUT_SECONDS=25.0,
        GEMINI_CHAT_MAX_OUTPUT_TOKENS=1024, GEMINI_THINKING_LEVEL="", CHAT_MAX_TOOL_ROUNDS=4,
        CHAT_TOOL_MAX_ROWS=50, CHAT_TOOL_MAX_CHARS=3000, CHAT_DASHBOARD_TOOL_ENABLED=True,
        DASHBOARD_THINKING_LEVEL="low", DASHBOARD_CHAT_MAX_OUTPUT_TOKENS=512, CHAT_DASHBOARD_MAX_WIDGETS=6, CHAT_DASHBOARD_DAILY_LIMIT=10, CHAT_DASHBOARD_MAX_TOTAL=50,
        DASHBOARD_CREATE_TIMEOUT_SECONDS=10.0, DASHBOARD_RENDER_TIMEOUT_SECONDS=12.0,
        DASHBOARD_SUGGEST_USE_LLM=True, DASHBOARD_SUGGEST_DAILY_CALLS=3, DASHBOARD_SUGGEST_MAX_OUTPUT_TOKENS=900,
        DASHBOARD_SUGGEST_TIMEOUT_SECONDS=12.0, DASHBOARD_AUTO_SUGGEST=True,
    )


@pytest.fixture
def gemini():
    """Reemplaza el cliente google.genai COMPLETO. Ningun test toca la red."""
    fake = make_fake_genai()
    with patch("google.genai.Client", return_value=fake.client) as ctor:
        yield SimpleNamespace(
            client=fake.client, chat=fake.chat, ctor=ctor, create=fake.create, send=fake.send, aclose=fake.aclose,
            generate=fake.client.aio.models.generate_content,
        )


@pytest.fixture
def env(settings_stub, gemini):
    """BDs en memoria como get_org_pool de TODOS los servicios de tableros + oraculo como motor de consultas."""
    from datetime import date

    dbs = FakeOrgDBs()
    main = FakeMainPool()
    main.orgs[ORG_A] = {"name": "Ferreteria Alfa", "sector": "comercio", "city": "Bogota"}
    main.orgs[ORG_B] = {"name": "Restaurante Beta", "sector": "comercio", "city": "Cali"}
    plans: list = []
    stack = [
        patch("app.services.agent_tools_service.get_org_pool", dbs.get_org_pool),
        patch("app.services.agent_tools_service.get_main_pool", main.get_main_pool),
        patch("app.services.agent_tools_service.get_settings", return_value=settings_stub),
        patch("app.services.agent_tools_service._today_co", return_value=date(2026, 10, 16)),
        patch("app.services.dashboard_service.get_org_pool", dbs.get_org_pool),
        patch("app.services.dashboard_render_service.get_org_pool", dbs.get_org_pool),
        patch("app.services.dashboard_render_service.get_settings", return_value=settings_stub),
        patch("app.services.dashboard_builder_service.get_settings", return_value=settings_stub),
        patch("app.services.dashboard_suggest_service.get_org_pool", dbs.get_org_pool),
        patch("app.services.dashboard_suggest_service.get_settings", return_value=settings_stub),
        patch("app.services.data_query_engine.run_plans", fake_run_plans(plans)),
    ]
    from app.services import dashboard_suggest_service as suggest_service
    suggest_service.reset_caches()
    try:
        for p in stack:
            p.start()
        yield SimpleNamespace(dbs=dbs, main=main, plans=plans, settings=settings_stub)
    finally:
        for p in reversed(stack):
            p.stop()


async def catalog_of(env, org: str = ORG_A):
    """(pool, catalogo del motor) de una org de la BD emulada."""
    from app.services import data_query_engine as engine

    pool = await env.dbs.get_org_pool(org)
    async with pool.acquire() as conn:
        records = await conn.fetch(
            "SELECT id, table_name, display_name, row_count, columns_definition FROM org_data_tables"
        )
    return pool, engine.build_catalog(records)
