"""Tableros creados por la IA contra un Postgres REAL desechable — PI0320251.

Se OMITE por defecto: necesita un Postgres local, descartable y accesible sin contrasena (trust) cuyo puerto se
indica en CHAT_TOOLS_TEST_PG_PORT (usuario en CHAT_TOOLS_TEST_PG_USER, por defecto 'tester'). Solo acepta
127.0.0.1 y crea/borra su propia base 'dash_test_<uuid>'. NUNCA apuntar a Neon ni a ningun servidor compartido.
Gemini no participa (suggest usa un modelo simulado).

Lo que la BD emulada no puede probar:
- concurrencia real: 25 pedidos identicos -> exactamente 1 tablero; 30 distintos con tope diario 5 -> exactamente 5
- el SQL real: `->>` sobre jsonb, subconsultas de la lista, lock consultivo, FK y rollback
- el calculo real contra el motor (valores de test-data/ferreteria y tablas grandes) y su tiempo
"""

import asyncio
import json
import os
import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import chart_specs as cs
from app.services import dashboard_builder_service as builder
from app.services import dashboard_suggest_service as suggest_service
from app.services import data_query_engine as engine
from tests.dash_support import FERRETERIA, PRODUCTOS_TYPES, VENTAS_TYPES, read_csv
from tests.fake_gemini import text_response

PORT = os.environ.get("CHAT_TOOLS_TEST_PG_PORT")
pytestmark = pytest.mark.skipif(not PORT, reason="define CHAT_TOOLS_TEST_PG_PORT para usar un Postgres local desechable")

asyncpg = pytest.importorskip("asyncpg")
HOST = "127.0.0.1"  # fijo a proposito
ORG = "550e8400-e29b-41d4-a716-446655440000"


@pytest.fixture
async def pg():
    from app import database

    user = os.environ.get("CHAT_TOOLS_TEST_PG_USER", "tester")
    dbname = f"dash_test_{uuid.uuid4().hex[:8]}"
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


async def add_table(pool, name, columns: dict, rows: list, display=None) -> uuid.UUID:
    async with pool.acquire() as conn:
        table_id = await conn.fetchval(
            "INSERT INTO org_data_tables (table_name, display_name, columns_definition, row_count) "
            "VALUES ($1, $2, $3::jsonb, $4) RETURNING id",
            name, display or name.title(), json.dumps([{"name": c, "type": t} for c, t in columns.items()]), len(rows),
        )
        await conn.executemany(
            "INSERT INTO org_data_rows (table_id, data) VALUES ($1, $2::jsonb)",
            [(table_id, json.dumps(r, ensure_ascii=False)) for r in rows],
        )
    return table_id


async def load_ferreteria(pool):
    for name, filename, types in (("ventas", "ventas.csv", VENTAS_TYPES), ("productos", "productos.csv", PRODUCTOS_TYPES)):
        columns, rows = read_csv(FERRETERIA / filename, types)
        await add_table(pool, name, {c: types.get(c, "text") for c in columns}, rows)


async def catalog_of(pool):
    async with pool.acquire() as conn:
        records = await conn.fetch(
            "SELECT id, table_name, display_name, row_count, columns_definition FROM org_data_tables"
        )
    return engine.build_catalog(records)


W_KPI = {"table": "ventas", "chart_type": "kpi", "y": "sum(total)"}
W_MES = {"table": "ventas", "chart_type": "line", "x": "month(fecha)", "y": "sum(total)"}
W_PIE = {"table": "ventas", "chart_type": "pie", "x": "metodo_pago", "y": "sum(total)"}


@pytest.fixture
def patched(pg):
    """Los servicios que piden el pool por org reciben el Postgres desechable."""
    async def get_pool(_org):
        return pg

    settings = SimpleNamespace(
        GOOGLE_API_KEY="", GEMINI_MODEL="m", DASHBOARD_SUGGEST_USE_LLM=True, DASHBOARD_SUGGEST_DAILY_CALLS=3,
        DASHBOARD_SUGGEST_MAX_OUTPUT_TOKENS=900, DASHBOARD_SUGGEST_TIMEOUT_SECONDS=12.0, DASHBOARD_AUTO_SUGGEST=True,
        DASHBOARD_RENDER_TIMEOUT_SECONDS=12.0, CHAT_DASHBOARD_MAX_WIDGETS=6, CHAT_DASHBOARD_DAILY_LIMIT=10,
        CHAT_DASHBOARD_MAX_TOTAL=50, DASHBOARD_CREATE_TIMEOUT_SECONDS=10.0,
    )
    suggest_service.reset_caches()
    with patch("app.services.dashboard_render_service.get_org_pool", get_pool), patch(
        "app.services.dashboard_render_service.get_settings", return_value=settings
    ), patch("app.services.dashboard_suggest_service.get_org_pool", get_pool), patch(
        "app.services.dashboard_suggest_service.get_settings", return_value=settings
    ), patch("app.services.dashboard_builder_service.get_settings", return_value=settings), patch(
        "app.services.dashboard_service.get_org_pool", get_pool
    ):
        yield settings


class TestConcurrencia:
    async def test_25_pedidos_identicos_crean_exactamente_un_tablero(self, pg, patched):
        await load_ferreteria(pg)
        catalog = await catalog_of(pg)
        results = await asyncio.gather(*[
            builder.build_dashboard(pg, catalog, f"Ventas {i}", [W_KPI, W_MES, W_PIE]) for i in range(25)
        ])
        ids = {r[0]["id"] for r in results}
        assert len(ids) == 1
        assert sum(1 for r in results if not r[0]["existing"]) == 1
        async with pg.acquire() as conn:
            assert await conn.fetchval("SELECT count(*) FROM dashboards") == 1
            assert await conn.fetchval("SELECT count(*) FROM widgets") == 3

    async def test_30_tableros_distintos_con_tope_diario_5_crean_exactamente_5(self, pg, patched):
        await load_ferreteria(pg)
        catalog = await catalog_of(pg)
        limits = builder.Limits(daily=5)
        outcomes = await asyncio.gather(*[
            builder.build_dashboard(
                pg, catalog, f"T{i}", [{**W_KPI, "filters": [["total", ">", str(i)]]}], limits=limits,
            )
            for i in range(30)
        ], return_exceptions=True)
        created = [o for o in outcomes if not isinstance(o, Exception)]
        refused = [o for o in outcomes if isinstance(o, builder.DashboardLimitError)]
        assert len(created) == 5 and len(refused) == 25 and len(created) + len(refused) == 30
        async with pg.acquire() as conn:
            assert await conn.fetchval("SELECT count(*) FROM dashboards") == 5

    async def test_el_tope_diario_cuenta_los_borrados(self, pg, patched):
        await load_ferreteria(pg)
        catalog = await catalog_of(pg)
        limits = builder.Limits(daily=2)
        for i in range(2):
            board, _ = await builder.build_dashboard(
                pg, catalog, f"T{i}", [{**W_KPI, "filters": [["total", ">", str(i)]]}], limits=limits)
            async with pg.acquire() as conn:
                await conn.execute("UPDATE dashboards SET deleted_at = now() WHERE id = $1", uuid.UUID(board["id"]))
        with pytest.raises(builder.DashboardLimitError):
            await builder.build_dashboard(pg, catalog, "otro", [W_PIE], limits=limits)

    async def test_misma_peticion_tras_borrar_crea_uno_nuevo_y_el_nombre_se_reutiliza(self, pg, patched):
        await load_ferreteria(pg)
        catalog = await catalog_of(pg)
        a, _ = await builder.build_dashboard(pg, catalog, "Ventas", [W_KPI])
        async with pg.acquire() as conn:
            await conn.execute("UPDATE dashboards SET deleted_at = now() WHERE id = $1", uuid.UUID(a["id"]))
        b, _ = await builder.build_dashboard(pg, catalog, "Ventas", [W_KPI])
        assert b["id"] != a["id"] and b["name"] == "Ventas" and b["existing"] is False


class TestSQLReal:
    async def test_rollback_si_un_widget_falla_no_queda_tablero_huerfano(self, pg, patched):
        await load_ferreteria(pg)
        catalog = await catalog_of(pg)
        good, _ = await builder.validate_and_run(pg, catalog, [W_KPI, W_PIE], builder.Limits())
        bad_spec, bad_result = good[1]
        bad_result["chart"]["title"] = "x" * 500                      # VARCHAR(120): el INSERT del 2.o widget falla
        with pytest.raises(Exception):
            await builder.create_dashboard_from_specs(pg, title="Roto", widgets=good, source="assistant")
        async with pg.acquire() as conn:
            assert await conn.fetchval("SELECT count(*) FROM dashboards") == 0
            assert await conn.fetchval("SELECT count(*) FROM widgets") == 0

    async def test_lo_guardado_es_la_especificacion_y_la_lista_trae_la_tarjeta(self, pg, patched):
        from app.services.dashboard_service import list_dashboards

        await load_ferreteria(pg)
        catalog = await catalog_of(pg)
        await builder.build_dashboard(pg, catalog, "Ventas del año", [W_KPI, W_MES, W_PIE])
        async with pg.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data_source_query FROM widgets WHERE widget_type = 'line_chart'")
            stored = json.loads(row["data_source_query"])                # asyncpg entrega jsonb como texto
        assert stored["table"] == "ventas" and stored["x"] == "month(fecha)" and stored["by"] == "assistant"
        assert "Cemento" not in json.dumps(stored)
        (item,) = await list_dashboards(ORG)
        assert item.widget_count == 3 and item.source == "assistant"
        assert item.preview["type"] == "line"
        assert item.preview["points"] == [3315500, 3174500, 2994700, 750000]
        assert item.highlights == ["Suma de total por mes de fecha", "Suma de total por metodo_pago"]

    async def test_el_widget_viejo_o_hostil_escrito_por_rest_con_jsonb_raro_no_rompe_la_lista(self, pg, patched):
        from app.services.dashboard_service import list_dashboards

        async with pg.acquire() as conn:
            did = await conn.fetchval("INSERT INTO dashboards (name) VALUES ('x') RETURNING id")
            await conn.execute(
                "INSERT INTO widgets (dashboard_id, title, widget_type, config, data_source_query) "
                "VALUES ($1, 'g', 'bar_chart', '{\"preview\": \"texto\"}', '[1,2]')", did)
        (item,) = await list_dashboards(ORG)
        assert item.preview is None and item.source is None


class TestCalculoReal:
    async def test_valores_de_ferreteria_contra_el_motor_real(self, pg, patched):
        from app.services.dashboard_render_service import render_dashboard

        await load_ferreteria(pg)
        catalog = await catalog_of(pg)
        board, _ = await builder.build_dashboard(
            pg, catalog, "V", [W_KPI, W_MES, W_PIE, {"table": "ventas", "chart_type": "bar", "x": "producto",
                                                     "y": "sum(total)", "top": 3}])
        out = await render_dashboard(ORG, board["id"])
        assert out["kpis"][0]["value"] == 10_234_700 and out["kpis"][0]["unit"] == "money"
        line, pie, bar = out["charts"]
        assert [(p["name"], p["value"]) for p in line["data"]] == [
            ("2025-07", 3_315_500), ("2025-08", 3_174_500), ("2025-09", 2_994_700), ("2025-10", 750_000)]
        assert {p["name"]: p["value"] for p in pie["data"]} == {
            "transferencia": 4_941_700, "tarjeta": 3_109_000, "efectivo": 2_184_000}
        assert [(p["name"], p["value"]) for p in bar["data"]] == [
            ("Cemento Argos 50kg", 2_194_500), ("Pintura vinilo blanco 5gal", 1_344_000),
            ("Varilla corrugada 1/2 x 6m", 1_320_000)]

    async def test_tabla_grande_sin_limite_de_500_y_tiempo_de_apertura(self, pg, patched, capsys):
        from app.services.dashboard_render_service import render_dashboard

        n = 50_000
        rows = [{"fecha": f"2026-{i % 12 + 1:02d}-{i % 28 + 1:02d}", "categoria": f"c{i % 9}",
                 "total": (i % 9 + 1) * 1000} for i in range(n)]
        await add_table(pg, "ventas", {"fecha": "date", "categoria": "text", "total": "number"}, rows, "Ventas")
        catalog = await catalog_of(pg)
        board, _ = await builder.build_dashboard(pg, catalog, "Grande", [
            W_KPI, {"table": "ventas", "chart_type": "kpi", "y": "count"},
            W_MES, {"table": "ventas", "chart_type": "bar", "x": "categoria", "y": "sum(total)"},
            {"table": "ventas", "chart_type": "pie", "x": "categoria", "y": "count"}])
        started = time.monotonic()
        out = await render_dashboard(ORG, board["id"])
        elapsed = time.monotonic() - started
        # 50.000 = 5.555 ciclos de 9 + 5 filas: categorias 0..4 aparecen 5.556 veces; 5..8, 5.555
        expected_total = sum((k + 1) * 1000 * (5556 if k < 5 else 5555) for k in range(9))
        values = {k["label"]: k["value"] for k in out["kpis"]}
        assert values["Suma de total"] == expected_total and values["Registros de Ventas"] == n
        assert not any(c.get("error") for c in out["charts"])
        print(f"\n[rendimiento] apertura de un tablero de 5 widgets sobre {n} filas: {elapsed:.2f} s")
        assert elapsed < 12


class TestSugerirReal:
    async def test_suggest_con_regla_y_con_modelo_simulado_sobre_postgres(self, pg, patched):
        await load_ferreteria(pg)
        out = await suggest_service.suggest(ORG, auto=True)
        assert out["status"] == "created" and out["source"] == "rules" and len(out["dashboards"]) == 2
        again = await suggest_service.suggest(ORG, auto=True)
        assert again["status"] == "has_dashboards"
        explicit = await suggest_service.suggest(ORG)
        assert explicit["status"] == "exists"

    async def test_tope_diario_ia_cuenta_firmas_en_sql_real(self, pg, patched):
        from google.genai import types as genai_types

        await load_ferreteria(pg)
        patched.GOOGLE_API_KEY = "x" * 20
        patched.DASHBOARD_SUGGEST_DAILY_CALLS = 1
        good = json.dumps({"dashboards": [{"title": "IA", "widgets": [W_KPI, W_PIE]}]})
        fake_client = AsyncMock()
        fake_client.aio.models.generate_content = AsyncMock(return_value=text_response(good))
        fake_client.aio.aclose = AsyncMock()
        with patch("google.genai.Client", return_value=fake_client):
            first = await suggest_service.suggest(ORG)
            assert first["source"] == "ai"
            async with pg.acquire() as conn:
                await conn.execute("UPDATE dashboards SET deleted_at = now()")
                await add_table(pg, "extra", {"a": "text"}, [{"a": "x"}] * 3)
            second = await suggest_service.suggest(ORG)
        assert fake_client.aio.models.generate_content.await_count == 1 and second["source"] == "rules"
