"""Edicion de tableros contra un Postgres REAL desechable — PI0320251.

Se OMITE por defecto: necesita un Postgres local, descartable y accesible sin contrasena (trust) cuyo puerto se
indica en CHAT_TOOLS_TEST_PG_PORT (usuario en CHAT_TOOLS_TEST_PG_USER, por defecto 'tester'). Solo acepta 127.0.0.1
y crea/borra sus propias bases 'dash_edit_<uuid>'. NUNCA apuntar a Neon ni a ningun servidor compartido. Gemini no
participa (cliente simulado).

Lo que la BD emulada no puede probar:
- concurrencia real: 25 ediciones simultaneas del mismo tablero (lock consultivo por tablero)
- el SQL real: jsonb, `data->>'seq'` sobre data_records, claves foraneas, rollback, arrays de la lista
- el flujo completo de la herramienta (chat simulado) sobre datos y motor reales
"""

import asyncio
import json
import os
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import chart_specs as cs
from app.services import dashboard_builder_service as builder
from app.services import dashboard_edit_service as editor
from app.services import data_query_engine as engine
from app.services.agent_tools_service import process_with_gemini
from tests.dash_support import FERRETERIA, PRODUCTOS_TYPES, VENTAS_TYPES, read_csv
from tests.fake_gemini import call_response, sent_function_responses, text_response, make_fake_genai
from tests.fake_org_db import FakeMainPool

PORT = os.environ.get("CHAT_TOOLS_TEST_PG_PORT")
pytestmark = pytest.mark.skipif(not PORT, reason="define CHAT_TOOLS_TEST_PG_PORT para usar un Postgres local desechable")

asyncpg = pytest.importorskip("asyncpg")
HOST = "127.0.0.1"  # fijo a proposito
ORG = "550e8400-e29b-41d4-a716-446655440000"

W_KPI = {"table": "ventas", "chart_type": "kpi", "y": "sum(total)"}
W_MES = {"table": "ventas", "chart_type": "line", "x": "month(fecha)", "y": "sum(total)"}
W_PRODUCTO = {"table": "ventas", "chart_type": "bar", "x": "producto", "y": "sum(total)", "top": 5}
W_METODO = {"table": "ventas", "chart_type": "pie", "x": "metodo_pago", "y": "sum(total)"}
BASE = [W_KPI, W_MES, W_PRODUCTO]
T_METODO = "Total por método de pago"


async def _database():
    from app import database

    user = os.environ.get("CHAT_TOOLS_TEST_PG_USER", "tester")
    dbname = f"dash_edit_{uuid.uuid4().hex[:8]}"
    admin = await asyncpg.connect(host=HOST, port=int(PORT), user=user, database="postgres")
    await admin.execute(f'CREATE DATABASE "{dbname}"')
    pool = await asyncpg.create_pool(host=HOST, port=int(PORT), user=user, database=dbname, min_size=1, max_size=40)
    async with pool.acquire() as conn:
        await conn.execute(database.ORG_BASE_SCHEMA_SQL)
    return admin, dbname, pool


@pytest.fixture
async def pg():
    admin, dbname, pool = await _database()
    try:
        yield pool
    finally:
        await pool.close()
        await admin.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        await admin.close()


@pytest.fixture
async def pg_b():
    admin, dbname, pool = await _database()
    try:
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


async def base_board(pool, name="Ventas por día", widgets=None):
    await load_ferreteria(pool)
    catalog = await catalog_of(pool)
    created, _ = await builder.build_dashboard(pool, catalog, name, BASE if widgets is None else widgets)
    return uuid.UUID(created["id"]), catalog


async def rows_of(pool, board_id):
    """Estado comparable del tablero tal como esta en Postgres."""
    async with pool.acquire() as conn:
        name = await conn.fetchval("SELECT name FROM dashboards WHERE id = $1", board_id)
        widgets = await conn.fetch(
            "SELECT id::text, title, widget_type, config::text, position_x, position_y, width, height, "
            "data_source_query::text AS dsq FROM widgets WHERE dashboard_id = $1 ORDER BY id", board_id)
    return name, [tuple(r.values()) for r in widgets]


async def versions_of(pool, board_id) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT count(*) FROM data_records WHERE table_name = $1", editor.VERSION_PREFIX + str(board_id))


def add(spec):
    return {"op": "add_widget", "spec": spec}


@pytest.fixture
def patched(pg):
    async def get_pool(_org):
        return pg

    settings = SimpleNamespace(
        GOOGLE_API_KEY="AIzaSy-PG-TEST", GEMINI_MODEL="m", GEMINI_TIMEOUT_SECONDS=25.0, GEMINI_CHAT_MAX_OUTPUT_TOKENS=1024,
        GEMINI_THINKING_LEVEL="", CHAT_MAX_TOOL_ROUNDS=4, CHAT_TOOL_MAX_ROWS=50, CHAT_TOOL_MAX_CHARS=3000,
        CHAT_DASHBOARD_TOOL_ENABLED=True, DASHBOARD_THINKING_LEVEL="low", DASHBOARD_CHAT_MAX_OUTPUT_TOKENS=1024,
        CHAT_DASHBOARD_MAX_WIDGETS=6, CHAT_DASHBOARD_DAILY_LIMIT=10, CHAT_DASHBOARD_MAX_TOTAL=50,
        DASHBOARD_CREATE_TIMEOUT_SECONDS=10.0, DASHBOARD_RENDER_TIMEOUT_SECONDS=12.0,
        CHAT_DASHBOARD_EDIT_ENABLED=True, CHAT_DASHBOARD_EDIT_MAX_OPS=4, CHAT_DASHBOARD_EDIT_MAX_WIDGETS=12,
        DASHBOARD_EDIT_VERSIONS_KEPT=10, DASHBOARD_EDIT_MAX_OUTPUT_TOKENS=768,
    )
    main = FakeMainPool()
    main.orgs[ORG] = {"name": "Ferreteria Alfa", "sector": "comercio", "city": "Bogota"}
    with patch("app.services.agent_tools_service.get_org_pool", get_pool), patch(
        "app.services.agent_tools_service.get_main_pool", main.get_main_pool
    ), patch("app.services.agent_tools_service.get_settings", return_value=settings), patch(
        "app.services.agent_tools_service._today_co", return_value=date(2026, 10, 16)
    ), patch("app.services.dashboard_render_service.get_org_pool", get_pool), patch(
        "app.services.dashboard_render_service.get_settings", return_value=settings
    ), patch("app.services.dashboard_builder_service.get_settings", return_value=settings), patch(
        "app.services.dashboard_edit_service.get_settings", return_value=settings
    ):
        yield settings


class TestSQLReal:
    async def test_agregar_reemplazar_quitar_renombrar_en_postgres(self, pg, patched):
        from app.services.dashboard_render_service import render_dashboard

        bid, catalog = await base_board(pg)
        out = await editor.edit_dashboard(pg, catalog, "ventas por dia", [
            add(W_METODO), {"op": "replace_widget", "target": "barras", "spec": {**W_METODO, "y": "count"}},
            {"op": "remove_widget", "target": "cifra"}, {"op": "rename", "title": "Resumen 2025"},
        ])
        assert out["name"] == "Resumen 2025" and out["widgets"] == 3 and out["noop"] is False
        name, widgets = await rows_of(pg, bid)
        assert name == "Resumen 2025" and sorted(w[1] for w in widgets) == sorted(
            ["Total por mes", "Número de registros por método de pago", T_METODO])
        rendered = await render_dashboard(ORG, str(bid))
        by_title = {c["title"]: {p["name"]: p["value"] for p in c["data"]} for c in rendered["charts"]}
        assert by_title[T_METODO] == {"transferencia": 4_941_700, "tarjeta": 3_109_000, "efectivo": 2_184_000}
        assert by_title["Número de registros por método de pago"] == {"efectivo": 16, "transferencia": 14, "tarjeta": 10}
        assert by_title["Total por mes"] == {
            "2025-07": 3_315_500, "2025-08": 3_174_500, "2025-09": 2_994_700, "2025-10": 750_000}
        assert rendered["kpis"] == []                                               # la cifra se quito

    async def test_deshacer_restaura_exactamente_en_postgres(self, pg, patched):
        bid, catalog = await base_board(pg)
        before = await rows_of(pg, bid)
        out = await editor.edit_dashboard(pg, catalog, "Ventas por día", [
            add(W_METODO), {"op": "remove_widget", "target": "barras"}, {"op": "rename", "title": "Otro"},
        ])
        assert await rows_of(pg, bid) != before and await versions_of(pg, bid) == 1
        done = await editor.undo_edit(pg, bid, out["version"])
        assert done["widgets"] == 3 and await rows_of(pg, bid) == before            # incluye ids, jsonb y posiciones
        assert await versions_of(pg, bid) == 0

    async def test_dos_ediciones_se_deshacen_en_orden_y_el_tope_de_versiones(self, pg, patched):
        bid, catalog = await base_board(pg)
        states, versions = [await rows_of(pg, bid)], []
        for i in range(12):
            name = "Ventas por día" if i == 0 else f"Ventas {i}"
            out = await editor.edit_dashboard(pg, catalog, name, [{"op": "rename", "title": f"Ventas {i + 1}"}])
            versions.append(out["version"])
            states.append(await rows_of(pg, bid))
        assert await versions_of(pg, bid) == 10
        # las dos mas viejas se podaron
        for old in versions[:2]:
            with pytest.raises(editor.UndoError) as exc:
                await editor.undo_edit(pg, bid, old)
            assert exc.value.status == 404
        for i in range(11, 1, -1):                                                  # de la mas nueva a la mas vieja
            await editor.undo_edit(pg, bid, versions[i])
            assert await rows_of(pg, bid) == states[i]
        assert await versions_of(pg, bid) == 0

    async def test_version_de_otra_base_de_datos_se_rechaza(self, pg, pg_b, patched):
        bid, catalog = await base_board(pg)
        bid_b, _ = await base_board(pg_b)
        out = await editor.edit_dashboard(pg, catalog, "Ventas por día", [add(W_METODO)])
        before_b = await rows_of(pg_b, bid_b)
        for board in (bid, bid_b):
            with pytest.raises(editor.UndoError) as exc:
                await editor.undo_edit(pg_b, board, out["version"])
            assert exc.value.status == 404
        assert await rows_of(pg_b, bid_b) == before_b

    async def test_las_versiones_no_aparecen_como_datos_de_archivos_ni_de_tablas(self, pg, patched):
        bid, catalog = await base_board(pg)
        await editor.edit_dashboard(pg, catalog, "Ventas por día", [add(W_METODO)])
        async with pg.acquire() as conn:
            tables = await conn.fetchval("SELECT count(*) FROM org_data_tables WHERE table_name LIKE 'dashboard_edit:%'")
            files = await conn.fetchval("SELECT count(*) FROM data_records WHERE table_name NOT LIKE 'dashboard_edit:%'")
        assert tables == 0 and files == 0

    async def test_la_lista_y_las_versiones_leen_bien_los_arrays_y_el_jsonb(self, pg, patched):
        bid, catalog = await base_board(pg)
        boards = await editor.list_boards(pg)
        assert len(boards) == 1 and boards[0].count == 3
        assert boards[0].titles == ["Suma de total", "Total por mes", "Total por producto"]
        assert boards[0].kinds == ["kpi_card", "line_chart", "bar_chart"]
        await editor.edit_dashboard(pg, catalog, "Ventas por día", [add(W_METODO)])
        (v,) = await editor.list_versions(pg, bid)
        assert v["widgets"] == 3 and v["summary"]["added"] == 1

    async def test_un_error_a_mitad_de_la_escritura_revierte_todo_en_postgres(self, pg, patched):
        bid, catalog = await base_board(pg)
        before = await rows_of(pg, bid)
        original = cs.Spec.stored

        def boom(self, **extra):
            raise RuntimeError("falla simulada a mitad de la escritura")

        with patch.object(cs.Spec, "stored", boom):
            with pytest.raises(RuntimeError):
                await editor.edit_dashboard(pg, catalog, "Ventas por día", [
                    {"op": "remove_widget", "target": "cifra"}, add(W_METODO)])
        assert await rows_of(pg, bid) == before and await versions_of(pg, bid) == 0
        assert cs.Spec.stored is original

    async def test_idempotencia_en_postgres(self, pg, patched):
        bid, catalog = await base_board(pg)
        before = await rows_of(pg, bid)
        out = await editor.edit_dashboard(pg, catalog, "Ventas por día", [add(W_MES)])
        assert out["noop"] is True and out["unchanged"] == ["Total por mes"]
        assert await rows_of(pg, bid) == before and await versions_of(pg, bid) == 0


class TestConcurrencia:
    async def test_25_ediciones_identicas_agregan_exactamente_un_grafico(self, pg, patched):
        bid, catalog = await base_board(pg)
        results = await asyncio.gather(*[
            editor.edit_dashboard(pg, catalog, "Ventas por día", [add(W_METODO)]) for _ in range(25)
        ])
        assert sum(1 for r in results if r["added"]) == 1 and sum(1 for r in results if r["noop"]) == 24
        name, widgets = await rows_of(pg, bid)
        assert len(widgets) == 4 and [w[1] for w in widgets].count(T_METODO) == 1
        assert await versions_of(pg, bid) == 1
        fps = {json.loads(w[8])["fp"] for w in widgets}
        assert len(fps) == 1                                                        # un solo contenido, una sola huella

    async def test_25_ediciones_distintas_del_mismo_tablero_no_se_pisan_y_respetan_el_tope_de_12(self, pg, patched):
        bid, catalog = await base_board(pg)
        specs = [
            {"table": "ventas", "chart_type": "kpi", "y": fn}
            for fn in ("avg(total)", "max(total)", "min(total)", "count", "sum(cantidad)", "avg(cantidad)",
                       "max(precio_unitario)")
        ] + [
            {"table": "ventas", "chart_type": "bar", "x": "producto", "y": "count", "top": n} for n in range(1, 11)
        ] + [
            {"table": "ventas", "chart_type": "bar", "x": x, "y": y}
            for x in ("cliente", "metodo_pago", "month(fecha)") for y in ("count", "sum(cantidad)")
        ] + [W_METODO, {"table": "productos", "chart_type": "bar", "x": "categoria", "y": "count"}]
        specs = specs[:25]
        assert len(specs) == 25
        outcomes = await asyncio.gather(*[
            editor.edit_dashboard(pg, catalog, "Ventas por día", [add(s)]) for s in specs
        ], return_exceptions=True)
        ok = [o for o in outcomes if not isinstance(o, Exception)]
        refused = [o for o in outcomes if isinstance(o, editor.EditError)]
        assert len(ok) + len(refused) == 25 and len(ok) == 9 and len(refused) == 16
        assert all("máximo es 12" in str(r) for r in refused)
        name, widgets = await rows_of(pg, bid)
        assert len(widgets) == 12
        keys = [cs.fingerprint([cs.parse_stored(catalog, json.loads(w[8]), w[2])]) for w in widgets]
        assert len(set(keys)) == 12                                                 # ningun grafico repetido
        # cada edicion aplicada vio el resultado de la anterior: ningun traslape y las versiones suman lo aplicado
        rects = [(w[4], w[5], w[6], w[7]) for w in widgets]
        for i, (x, y, w_, h) in enumerate(rects):
            for ox, oy, ow, oh in rects[i + 1:]:
                assert not (x < ox + ow and ox < x + w_ and y < oy + oh and oy < y + h)
        assert await versions_of(pg, bid) == min(9, 10)

    async def test_25_renombres_simultaneos_dejan_un_nombre_valido_y_cada_version_es_consistente(self, pg, patched):
        bid, catalog = await base_board(pg)
        results = await asyncio.gather(*[
            editor.edit_dashboard(pg, catalog, "ventas", [{"op": "rename", "title": f"Nombre {i}"}]) for i in range(25)
        ], return_exceptions=True)
        errors = [r for r in results if isinstance(r, Exception)]
        # tras el primer renombre el tablero ya no se llama "Ventas por dia": las demas no lo encuentran (error limpio)
        assert all(isinstance(e, editor.EditError) and "no encontré el tablero" in str(e) for e in errors)
        applied = [r for r in results if not isinstance(r, Exception)]
        assert len(applied) >= 1
        name, widgets = await rows_of(pg, bid)
        assert name.startswith("Nombre ") and len(widgets) == 3

    async def test_ediciones_simultaneas_de_varios_tipos_dejan_un_estado_coherente(self, pg, patched):
        bid, catalog = await base_board(pg)
        ops = [
            [add(W_METODO)], [{"op": "remove_widget", "target": "cifra"}],
            [{"op": "replace_widget", "target": "barras", "spec": W_METODO}], [{"op": "rename", "title": "Nuevo"}],
        ] * 6
        results = await asyncio.gather(*[
            editor.edit_dashboard(pg, catalog, "Ventas por día" if i % 4 != 3 else "Ventas por día", o)
            for i, o in enumerate(ops)
        ], return_exceptions=True)
        for r in results:
            assert not isinstance(r, Exception) or isinstance(r, editor.EditError)      # nunca un error crudo de la BD
        name, widgets = await rows_of(pg, bid)
        ids = [w[0] for w in widgets]
        assert len(ids) == len(set(ids)) and 1 <= len(widgets) <= 4
        titles = [w[1] for w in widgets]
        assert titles.count(T_METODO) <= 1                                          # el mismo grafico nunca dos veces
        assert await versions_of(pg, bid) <= 10

    async def test_dos_deshacer_de_la_misma_version_solo_uno_gana(self, pg, patched):
        bid, catalog = await base_board(pg)
        before = await rows_of(pg, bid)
        out = await editor.edit_dashboard(pg, catalog, "Ventas por día", [add(W_METODO), {"op": "rename", "title": "X"}])
        results = await asyncio.gather(*[editor.undo_edit(pg, bid, out["version"]) for _ in range(10)], return_exceptions=True)
        wins = [r for r in results if not isinstance(r, Exception)]
        losses = [r for r in results if isinstance(r, editor.UndoError)]
        assert len(wins) == 1 and len(losses) == 9 and all(l.status == 404 for l in losses)
        assert await rows_of(pg, bid) == before

    async def test_editar_y_deshacer_a_la_vez_no_deja_el_tablero_a_medias(self, pg, patched):
        bid, catalog = await base_board(pg)
        first = await editor.edit_dashboard(pg, catalog, "Ventas por día", [add(W_METODO)])
        tasks = [editor.undo_edit(pg, bid, first["version"])] + [
            editor.edit_dashboard(pg, catalog, "Ventas por día",
                                  [add({"table": "productos", "chart_type": "bar", "x": "categoria", "y": "count"})])
            for _ in range(5)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert not any(isinstance(r, Exception) and not isinstance(r, (editor.EditError, editor.UndoError)) for r in results)
        name, widgets = await rows_of(pg, bid)
        titles = [w[1] for w in widgets]
        assert titles.count("Número de registros por categoría") <= 1 and len(set(w[0] for w in widgets)) == len(widgets)
        assert len(widgets) in (3, 4, 5)

    async def test_el_lock_es_por_tablero_uno_ocupado_no_frena_a_otro(self, pg, patched):
        bid, catalog = await base_board(pg)
        other, _ = await builder.build_dashboard(pg, catalog, "Clientes", [W_METODO, W_KPI])
        async with pg.acquire() as holder:
            tx = holder.transaction()
            await tx.start()
            await holder.execute(editor.LOCK_SQL, f"dashboard_edit:{bid}")            # alguien edita Ventas por día
            blocked = asyncio.ensure_future(editor.edit_dashboard(pg, catalog, "Ventas por día", [add(W_METODO)]))
            free = await asyncio.wait_for(
                editor.edit_dashboard(pg, catalog, "Clientes", [{"op": "rename", "title": "Clientes 2"}]), timeout=5)
            assert free["name"] == "Clientes 2"                                       # el otro tablero avanza
            await asyncio.sleep(0.4)
            assert not blocked.done()                                                 # este espera su turno
            await tx.rollback()
        out = await asyncio.wait_for(blocked, timeout=10)
        assert out["added"] == [T_METODO]


class TestFlujoCompleto:
    async def test_herramienta_del_chat_sobre_postgres_real_con_gemini_simulado(self, pg, patched):
        from app.services.dashboard_render_service import render_dashboard

        bid, catalog = await base_board(pg)
        fake = make_fake_genai()
        fake.send.side_effect = [
            call_response(("edit_dashboard", {"dashboard": "ventas por dia", "operations": [
                add(W_METODO), {"op": "replace_widget", "target": "línea", "spec": {
                    "table": "ventas", "chart_type": "line", "x": "month(fecha)", "y": "count"}},
                {"op": "rename", "title": "Ventas 2025"},
            ]})),
            text_response("Listo."),
        ]
        with patch("google.genai.Client", return_value=fake.client):
            result = await process_with_gemini(ORG, "edita el tablero ventas por dia: agrega la torta de pagos, cambia la línea por conteo y renómbralo Ventas 2025")
        (edit,) = result["dashboard_edits"]
        assert edit["name"] == "Ventas 2025" and edit["widgets"] == 4 and edit["added"] == [T_METODO]
        assert edit["replaced"] == [{"from": "Total por mes", "to": "Número de registros por mes"}]
        (fr,) = sent_function_responses(fake.send, 1)
        assert fr.response == {"ok": True, "tablero": "Ventas 2025", "graficos": 4,
                               "cambios": "agregados 1, reemplazados 1, renombrado"}
        rendered = await render_dashboard(ORG, str(bid))
        by_title = {c["title"]: {p["name"]: p["value"] for p in c["data"]} for c in rendered["charts"]}
        assert by_title["Número de registros por mes"] == {"2025-07": 12, "2025-08": 12, "2025-09": 12, "2025-10": 4}
        out = await editor.undo_edit(pg, bid, edit["version"])
        assert out["name"] == "Ventas por día" and out["widgets"] == 3
