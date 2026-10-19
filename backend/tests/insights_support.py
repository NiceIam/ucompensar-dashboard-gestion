"""Soporte de las pruebas de hallazgos de negocio — PI0320251.

Dos backends con la misma interfaz:
- oraculo: BD emulada (tests/fake_org_db.py) + el motor reemplazado por el oraculo pandas (tests/query_oracle.py).
- postgres: un Postgres REAL desechable (se OMITE salvo que se defina CHAT_TOOLS_TEST_PG_PORT; solo 127.0.0.1,
  base propia por organizacion, nunca Neon ni un servidor compartido). Ejecuta el SQL que compila el motor.

Gemini no participa en nada de esto: el servicio de hallazgos no lo usa.
"""

import csv
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from tests import query_oracle
from tests.fake_org_db import FakeOrgDBs

PG_PORT = os.environ.get("CHAT_TOOLS_TEST_PG_PORT")
PG_HOST = "127.0.0.1"   # fijo a proposito
ORG_A = "550e8400-e29b-41d4-a716-446655440000"
ORG_B = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
# Lunes 20 de octubre de 2025, 10:00 en Colombia
NOW = datetime(2025, 10, 20, 15, 0, tzinfo=timezone.utc)
FERRETERIA = Path(__file__).resolve().parents[2] / "test-data" / "ferreteria"

PROD_COLS = {"nombre": "text", "costo": "number", "stock": "integer"}
SALE_COLS = {"fecha": "date", "producto": "text", "cantidad": "integer", "precio_unitario": "number",
             "total": "number", "cliente": "text"}


class OracleBackend:
    name = "oraculo"

    def __init__(self) -> None:
        self.dbs = FakeOrgDBs()

    async def add_table(self, name: str, columns: dict, rows: list, display: str | None = None,
                        org: str = ORG_A) -> None:
        self.dbs.db(org).add_table(name, list(columns), rows, display_name=display or name.title(),
                                   column_types=columns)

    def patches(self):
        return [
            patch("app.services.business_insights_service.get_org_pool", self.dbs.get_org_pool),
            patch("app.services.data_query_engine.run_plans", query_oracle.fake_run_plans()),
        ]


class PostgresBackend:
    name = "postgres"

    def __init__(self, asyncpg, admin) -> None:
        self.asyncpg, self.admin = asyncpg, admin
        self.pools: dict[str, object] = {}
        self.dbnames: list[str] = []

    async def pool(self, org: str):
        if org not in self.pools:
            from app import database

            dbname = f"insights_test_{uuid.uuid4().hex[:8]}"
            user = os.environ.get("CHAT_TOOLS_TEST_PG_USER", "tester")
            await self.admin.execute(f'CREATE DATABASE "{dbname}"')
            self.dbnames.append(dbname)
            pool = await self.asyncpg.create_pool(host=PG_HOST, port=int(PG_PORT), user=user, database=dbname,
                                                  min_size=1, max_size=5)
            async with pool.acquire() as conn:
                await conn.execute(database.ORG_BASE_SCHEMA_SQL)
            self.pools[org] = pool
        return self.pools[org]

    async def add_table(self, name: str, columns: dict, rows: list, display: str | None = None,
                        org: str = ORG_A) -> None:
        pool = await self.pool(org)
        async with pool.acquire() as conn:
            table_id = await conn.fetchval(
                "INSERT INTO org_data_tables (table_name, display_name, columns_definition, row_count) "
                "VALUES ($1, $2, $3::jsonb, $4) RETURNING id",
                name, display or name.title(), json.dumps([{"name": c, "type": t} for c, t in columns.items()]),
                len(rows),
            )
            async with conn.transaction():
                for row in rows:
                    await conn.execute("INSERT INTO org_data_rows (table_id, data) VALUES ($1, $2::jsonb)",
                                       table_id, json.dumps(row, ensure_ascii=False))

    def patches(self):
        async def get_org_pool(org_id):
            return await self.pool(org_id)

        return [patch("app.services.business_insights_service.get_org_pool", get_org_pool)]

    async def close(self) -> None:
        for pool in self.pools.values():
            await pool.close()
        for dbname in self.dbnames:
            await self.admin.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        await self.admin.close()


async def make_backend(kind: str):
    """(backend, lista de patches a activar). Para 'postgres' se omite la prueba si no hay puerto."""
    if kind == "oraculo":
        backend = OracleBackend()
        return backend, backend.patches()
    if not PG_PORT:
        pytest.skip("define CHAT_TOOLS_TEST_PG_PORT para usar un Postgres local desechable")
    asyncpg = pytest.importorskip("asyncpg")
    user = os.environ.get("CHAT_TOOLS_TEST_PG_USER", "tester")
    admin = await asyncpg.connect(host=PG_HOST, port=int(PG_PORT), user=user, database="postgres")
    backend = PostgresBackend(asyncpg, admin)
    return backend, backend.patches()


# ---------------------------------------------------------------------------
# Constructores de datos
# ---------------------------------------------------------------------------

def prods(*rows) -> list[dict]:
    """(nombre, costo, stock) -> filas; None omite la clave (como la ingesta real)."""
    return [{k: v for k, v in zip(("nombre", "costo", "stock"), r) if v is not None} for r in rows]


def sales(*rows) -> list[dict]:
    """(fecha, producto, cantidad, precio_unitario[, cliente]) -> filas con total = cantidad x precio."""
    out = []
    for r in rows:
        fecha, producto, cantidad, precio = r[:4]
        cliente = r[4] if len(r) > 4 else None
        row = {"fecha": fecha, "producto": producto, "cantidad": cantidad, "precio_unitario": precio,
               "total": cantidad * precio, "cliente": cliente}
        out.append({k: v for k, v in row.items() if v is not None})
    return out


def stringify(rows: list[dict]) -> list[dict]:
    """Todos los numeros como texto: asi quedaron guardados en cargas antiguas."""
    return [{k: (str(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v) for k, v in r.items()}
            for r in rows]


def read_csv(name: str, as_text: bool = False) -> tuple[list[str], list[dict]]:
    """CSV de test-data/ferreteria -> (columnas, filas). Los numeros se guardan como numeros (flujo real) o texto."""
    with open(FERRETERIA / f"{name}.csv", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for r in reader:
            row = {}
            for k, v in r.items():
                if v == "":
                    continue
                if not as_text:
                    try:
                        v = int(v)
                    except ValueError:
                        try:
                            v = float(v) if re_float(v) else v
                        except ValueError:
                            pass
                row[k] = v
            rows.append(row)
        return reader.fieldnames, rows


def re_float(text: str) -> bool:
    import re
    return bool(re.fullmatch(r"-?\d+\.\d+", text))


def item(result: dict, rid: str) -> dict:
    found = [i for i in result["items"] if i["id"] == rid]
    assert found, f"no hay item {rid}; items={[i['id'] for i in result['items']]}, missing={result['missing']}"
    return found[0]


def metrics(it: dict) -> dict:
    return {m["label"]: m["value"] for m in it["metrics"]}


def missing(result: dict, rid: str) -> dict:
    found = [m for m in result["missing"] if m["id"] == rid]
    assert found, f"{rid} no esta en missing; items={[i['id'] for i in result['items']]}"
    return found[0]
