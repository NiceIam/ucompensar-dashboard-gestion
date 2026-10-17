"""Rango de fechas por columna contra un Postgres REAL desechable — PI0320251.

Mismo contrato que tests/test_date_ranges.py (BD emulada), pero con el SQL real del motor: el rango que se guarda
al cargar datos sale de data_query_engine.date_ranges y debe coincidir con lo que los filtros del motor leen.

Se OMITE por defecto: necesita un Postgres local, descartable y accesible sin contrasena (trust) cuyo puerto se
indica en CHAT_TOOLS_TEST_PG_PORT (usuario en CHAT_TOOLS_TEST_PG_USER, por defecto 'tester'). Solo acepta 127.0.0.1
y crea/borra su propia base 'date_ranges_test_<uuid>'. NUNCA apuntar a Neon ni a ningun servidor compartido.
Gemini no participa.

Ejemplo (PowerShell): $env:CHAT_TOOLS_TEST_PG_PORT=54872; pytest tests/test_date_ranges_pg.py
"""

import json
import os
import random
import uuid
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from app.services import data_query_engine as engine
from app.services import schema_agent_service as svc
from app.services.agent_tools_service import _catalog_prompt
from tests import query_oracle

PORT = os.environ.get("CHAT_TOOLS_TEST_PG_PORT")
pytestmark = pytest.mark.skipif(not PORT, reason="define CHAT_TOOLS_TEST_PG_PORT para usar un Postgres local desechable")

asyncpg = pytest.importorskip("asyncpg")

HOST = "127.0.0.1"  # fijo a proposito
TODAY = date(2026, 10, 16)

FECHAS = ["2026-03-15", "2026-03-15 10:00:00", "2026-03-15T10:00:00", "15/03/2026", "5-1-2026", "2026/1/5",
          "2025-12-31", "2026-02-28", "2024-02-29", "2026-02-30", "13/13/2026", "0000-01-01", "9999-12-31",
          "no es fecha", "", None, "MISSING", " 2026-01-07", "2026-1-9", "15/03/26", "01/12/31", "05/06/55",
          "2026-11", "2026-7", "20260704", "15-mar-2026", "٢٠٢٦-٠١-٠١"]


@pytest.fixture
async def pg():
    from app import database

    user = os.environ.get("CHAT_TOOLS_TEST_PG_USER", "tester")
    dbname = f"date_ranges_test_{uuid.uuid4().hex[:8]}"
    admin = await asyncpg.connect(host=HOST, port=int(PORT), user=user, database="postgres")
    await admin.execute(f'CREATE DATABASE "{dbname}"')
    pool = await asyncpg.create_pool(host=HOST, port=int(PORT), user=user, database=dbname, min_size=1, max_size=5,
                                     statement_cache_size=0)
    try:
        async with pool.acquire() as conn:
            await conn.execute(database.ORG_BASE_SCHEMA_SQL)

        async def get_org_pool(_org_id):
            return pool

        with patch("app.services.schema_agent_service.get_org_pool", get_org_pool), patch(
            "app.services.data_query_engine.today", return_value=TODAY
        ):
            yield pool
    finally:
        await pool.close()
        await admin.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        await admin.close()


async def add_table(pool, name="ventas", columns=None, rows=(), ranges=None) -> uuid.UUID:
    columns = columns or {"fecha": "date", "producto": "text", "total": "number"}
    definition = [{"name": c, "type": t, **({"range": ranges[c]} if ranges and c in ranges else {})}
                  for c, t in columns.items()]
    async with pool.acquire() as conn:
        table_id = await conn.fetchval(
            "INSERT INTO org_data_tables (table_name, display_name, columns_definition, row_count) "
            "VALUES ($1, $2, $3::jsonb, $4) RETURNING id", name, name.title(), json.dumps(definition), len(rows),
        )
        await conn.executemany(
            "INSERT INTO org_data_rows (table_id, data) VALUES ($1, $2::jsonb)",
            [(table_id, json.dumps(r, ensure_ascii=False)) for r in rows],
        )
    return table_id


async def columns_of(pool, table_id) -> list[dict]:
    async with pool.acquire() as conn:
        raw = await conn.fetchval("SELECT columns_definition FROM org_data_tables WHERE id = $1", table_id)
    return json.loads(raw) if isinstance(raw, str) else raw


async def range_of(pool, table_id, name="fecha"):
    return next(c for c in await columns_of(pool, table_id) if c["name"] == name).get("range")


async def load(pool, table_id, fechas):
    df = pd.DataFrame({"fecha": fechas, "producto": ["x"] * len(fechas), "total": list(range(len(fechas)))})
    return await svc.load_csv_to_table(df, "org", str(table_id))


class TestRangoAlCargarEnPostgres:
    async def test_fechas_iso(self, pg):
        tid = await add_table(pg)
        await load(pg, tid, ["2026-03-15", "2026-01-05", "2026-06-28"])

        assert await range_of(pg, tid) == ["2026-01-05", "2026-06-28"]

    async def test_dia_mes_año_de_2_digitos_y_año_mes(self, pg):
        a, b = await add_table(pg, "a"), await add_table(pg, "b")
        await load(pg, a, ["15/03/26", "01/12/31", "05/06/55", "03/04/2024"])
        await load(pg, b, ["2026-11", "2026-02", "2026-7"])

        assert await range_of(pg, a) == ["1955-06-05", "2031-12-01"]     # ventana de 2026: 55 -> 1955, 31 -> 2031
        assert await range_of(pg, b) == ["2026-02-01", "2026-11-01"]

    async def test_celdas_ilegibles_se_ignoran_y_sin_fechas_no_hay_rango(self, pg):
        a, b = await add_table(pg, "a"), await add_table(pg, "b")
        await load(pg, a, ["no es fecha", "2026-02-30", "2026-04-10", "15-mar-2026", "13/13/2026", "0000-01-01"])
        result = await load(pg, b, ["mañana", "n/a", "2026-02-30"])

        assert await range_of(pg, a) == ["2026-04-10", "2026-04-10"]
        assert result["rows_inserted"] == 3 and await range_of(pg, b) is None

    async def test_conserva_el_resto_de_la_definicion(self, pg):
        tid = await add_table(pg)
        await load(pg, tid, ["2026-03-15"])

        assert await columns_of(pg, tid) == [
            {"name": "fecha", "type": "date", "range": ["2026-03-15", "2026-03-15"]},
            {"name": "producto", "type": "text"},
            {"name": "total", "type": "number"},
        ]

    async def test_cargas_posteriores_actualizan_el_rango(self, pg):
        tid = await add_table(pg)
        await load(pg, tid, ["2026-03-15", "2026-04-01"])
        await load(pg, tid, ["2026-01-05"])
        assert await range_of(pg, tid) == ["2026-01-05", "2026-04-01"]

        await load(pg, tid, ["2026-12-31"])
        assert await range_of(pg, tid) == ["2026-01-05", "2026-12-31"]

    async def test_tabla_vieja_sin_rango_se_calcula_sobre_todas_las_filas(self, pg):
        tid = await add_table(pg, rows=[{"fecha": "2024-01-10"}, {"fecha": "2025-07-01"}])

        await load(pg, tid, ["2026-03-15"])

        assert await range_of(pg, tid) == ["2024-01-10", "2026-03-15"]

    async def test_smart_upload_nueva_y_existente(self, pg):
        first = pd.DataFrame({"fecha": ["2026-03-15", "2026-03-20"], "producto": ["a", "b"], "total": [1, 2]})
        second = pd.DataFrame({"fecha": ["2025-12-01"], "producto": ["c"], "total": [3]})

        created = await svc.smart_upload(first, "org", "ventas.csv")
        assert await range_of(pg, uuid.UUID(created["table_id"])) == ["2026-03-15", "2026-03-20"]

        again = await svc.smart_upload(second, "org", "ventas2.csv")

        assert again["status"] == "loaded_to_existing"
        assert await range_of(pg, uuid.UUID(again["table_id"])) == ["2025-12-01", "2026-03-20"]

    async def test_modify_table_con_columna_de_fecha_que_ya_tiene_datos(self, pg):
        tid = await add_table(pg, columns={"nota": "text"}, rows=[{"cuando": "2026-05-01"}, {"cuando": "2026-08-09"}])

        await svc.modify_table("org", str(tid), add_columns=[{"name": "cuando", "type": "date"}])

        assert await range_of(pg, tid, "cuando") == ["2026-05-01", "2026-08-09"]

    async def test_el_tope_de_tiempo_del_rango_no_se_escapa_de_la_transaccion(self, pg):
        tid = await add_table(pg)
        await load(pg, tid, ["2026-03-15"])

        async with pg.acquire() as conn:
            assert await conn.fetchval("SHOW statement_timeout") in ("0", "0ms")


class TestCoincideConElMotorEnPostgres:
    async def test_filtro_entre_min_y_max_devuelve_todas_las_filas_con_fecha_legible(self, pg):
        rnd = random.Random(20261016)
        # Sin 9999-12-31: parse_date_range no puede formar [inicio, fin) de ese dia (limite de date), asi que un
        # filtro con ese valor se rechaza; el rango SI lo guarda (ver test_date_ranges_coincide_con_el_oraculo).
        valores = [rnd.choice([f for f in FECHAS if f != "9999-12-31"]) for _ in range(400)]
        rows = [{"producto": "x", **({"fecha": v} if v != "MISSING" else {})} for v in valores]
        tid = await add_table(pg)
        await svc.load_csv_to_table(
            pd.DataFrame([{"fecha": r.get("fecha"), "producto": "x"} for r in rows]), "org", str(tid),
        )
        lo, hi = await range_of(pg, tid)

        async with pg.acquire() as conn:
            catalog = engine.build_catalog(await conn.fetch(
                "SELECT id, table_name, display_name, row_count, columns_definition FROM org_data_tables"
            ))
        table = catalog["ventas"]
        assert table.column("fecha").range == (lo, hi)                      # lo que vera el catalogo

        query_oracle._YEAR[0] = TODAY.year
        readable = sum(1 for r in rows if query_oracle.date_of(query_oracle.raw_text(r, "fecha")) is not None)
        assert readable > 100

        async def count(*filters):
            plan = engine.build_plan(table, filters=list(filters), aggregates=["count"])
            (result,) = await engine.run_plans(pg, [plan])
            return result.rows[0][0]

        assert await count(["fecha", ">=", lo], ["fecha", "<=", hi]) == readable
        assert await count(["fecha", "<", lo]) == 0 and await count(["fecha", ">", hi]) == 0
        assert await count(["fecha", "=", lo]) >= 1 and await count(["fecha", "=", hi]) >= 1    # justo, no holgado

    async def test_date_ranges_coincide_con_el_oraculo_en_pandas(self, pg):
        rnd = random.Random(7)
        cols = {"f1": "date", "f2": "date", "f3": "date"}
        rows = []
        for _ in range(300):
            row = {}
            for c in cols:
                v = rnd.choice(FECHAS)
                if v != "MISSING":
                    row[c] = v
            rows.append(row)
        tid = await add_table(pg, columns=cols, rows=rows)

        async with pg.acquire() as conn:
            got = await engine.date_ranges(conn, tid, list(cols))

        query_oracle._YEAR[0] = TODAY.year
        for c in cols:
            dates = [d for d in (query_oracle.date_of(query_oracle.raw_text(r, c)) for r in rows) if d is not None]
            assert got[c] == (min(dates), max(dates)), c


class TestFallasEnPostgres:
    async def test_un_error_de_postgres_en_el_rango_no_aborta_la_carga(self, pg):
        """El rango corre en un savepoint: si Postgres lo rechaza, filas y row_count se confirman igual."""
        tid = await add_table(pg)

        async def boom(conn, table_id, names):
            await conn.execute("SELECT 1/0")

        with patch("app.services.data_query_engine.date_ranges", boom):
            result = await load(pg, tid, ["2026-03-15", "2026-04-01"])

        assert result["rows_inserted"] == 2 and result["total_rows"] == 2
        async with pg.acquire() as conn:
            assert await conn.fetchval("SELECT count(*) FROM org_data_rows WHERE table_id = $1", tid) == 2
            assert await conn.fetchval("SELECT row_count FROM org_data_tables WHERE id = $1", tid) == 2
        assert await range_of(pg, tid) is None

    async def test_un_fallo_del_rango_no_ensucia_la_siguiente_carga(self, pg):
        tid = await add_table(pg)

        async def boom(conn, table_id, names):
            await conn.execute("SELECT 1/0")

        with patch("app.services.data_query_engine.date_ranges", boom):
            await load(pg, tid, ["2026-03-15"])
        await load(pg, tid, ["2026-04-01"])

        assert await range_of(pg, tid) == ["2026-03-15", "2026-04-01"]

    async def test_la_carga_con_error_de_filas_no_deja_rango(self, pg):
        tid = await add_table(pg)
        df = pd.DataFrame({"fecha": ["2026-03-15"], "producto": ["x"], "total": [1]})

        with patch("app.services.schema_agent_service._parse_columns_definition", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                await svc.load_csv_to_table(df, "org", str(tid))

        async with pg.acquire() as conn:
            assert await conn.fetchval("SELECT count(*) FROM org_data_rows WHERE table_id = $1", tid) == 0
        assert await range_of(pg, tid) is None


class TestBackfillEnPostgres:
    async def test_dry_run_no_escribe_y_aplicar_si(self, pg):
        ventas = await add_table(pg, "ventas", rows=[{"fecha": "2026-01-05"}, {"fecha": "15/03/26"}, {"fecha": "n/a"}])
        await add_table(pg, "vacia")
        con_rango = await add_table(
            pg, "citas", columns={"cuando": "date"}, rows=[{"cuando": "2026-02-02"}],
            ranges={"cuando": ["2020-01-01", "2020-12-31"]},
        )

        dry = await svc.backfill_date_ranges("org")

        assert dry == [{
            "table": "ventas", "rows": 3, "ranges": {"fecha": ["2026-01-05", "2026-03-15"]},
            "changed": True, "applied": False,
        }]
        assert await range_of(pg, ventas) is None

        applied = await svc.backfill_date_ranges("org", dry_run=False)

        assert applied[0]["applied"] is True and await range_of(pg, ventas) == ["2026-01-05", "2026-03-15"]
        assert await range_of(pg, con_rango, "cuando") == ["2020-01-01", "2020-12-31"]
        assert await svc.backfill_date_ranges("org", dry_run=False) == []

        refreshed = await svc.backfill_date_ranges("org", dry_run=False, refresh=True)

        assert {r["table"] for r in refreshed if r["changed"]} == {"citas"}
        assert await range_of(pg, con_rango, "cuando") == ["2026-02-02", "2026-02-02"]

    async def test_el_catalogo_del_chat_muestra_el_rango_calculado(self, pg):
        await add_table(pg, rows=[{"fecha": "2026-01-05", "producto": "a"}, {"fecha": "2026-06-28", "producto": "b"}])
        await svc.backfill_date_ranges("org", dry_run=False)

        async with pg.acquire() as conn:
            catalog = engine.build_catalog(await conn.fetch(
                "SELECT id, table_name, display_name, row_count, columns_definition FROM org_data_tables"
            ))

        assert "ventas[2]: fecha:f[2026-01-05→2026-06-28] producto:t total:n" in _catalog_prompt("X", catalog)
