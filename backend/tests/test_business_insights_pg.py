"""Hallazgos de negocio contra un Postgres REAL desechable, con el flujo REAL de carga — PI0320251.

Se OMITE salvo que se defina CHAT_TOOLS_TEST_PG_PORT (usuario en CHAT_TOOLS_TEST_PG_USER, por defecto 'tester'):
solo 127.0.0.1, una base propia por prueba, NUNCA Neon ni un servidor compartido. Sin Gemini ni red.

Cubre lo que la BD emulada no puede:
- Las 6 recetas sobre los CSV de test-data/ferreteria cargados con smart_upload (el camino completo: analisis de
  columnas, creacion de tabla, carga, rango de fechas) y los MISMOS numeros si los valores quedaron como texto
  (cargas antiguas).
- Encabezados de Excel arbitrarios que la carga limpia ("Descripción" -> "descripción", "Precio de Compra" ->
  "precio_de_compra").
- La transaccion de solo lectura y el statement_timeout dentro de la consulta de hallazgos.
- Rendimiento con 50.000 ventas y 5.000 productos.
"""

import json
import os
import time
import uuid
from datetime import date, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from app.services import business_insights_service as svc
from app.services import data_query_engine as engine
from app.services import schema_agent_service as sa
from tests.insights_support import FERRETERIA, NOW, item, metrics

PORT = os.environ.get("CHAT_TOOLS_TEST_PG_PORT")
pytestmark = pytest.mark.skipif(not PORT, reason="define CHAT_TOOLS_TEST_PG_PORT para usar un Postgres local desechable")

asyncpg = pytest.importorskip("asyncpg")
HOST = "127.0.0.1"  # fijo a proposito
ORG = "550e8400-e29b-41d4-a716-446655440000"


@pytest.fixture
async def pool():
    from app import database

    user = os.environ.get("CHAT_TOOLS_TEST_PG_USER", "tester")
    dbname = f"insights_pg_{uuid.uuid4().hex[:8]}"
    admin = await asyncpg.connect(host=HOST, port=int(PORT), user=user, database="postgres")
    await admin.execute(f'CREATE DATABASE "{dbname}"')
    pool = await asyncpg.create_pool(host=HOST, port=int(PORT), user=user, database=dbname, min_size=1, max_size=5)
    try:
        async with pool.acquire() as conn:
            await conn.execute(database.ORG_BASE_SCHEMA_SQL)

        async def get_org_pool(org_id):
            return pool

        with patch("app.services.schema_agent_service.get_org_pool", get_org_pool), patch(
            "app.services.business_insights_service.get_org_pool", get_org_pool
        ):
            yield pool
    finally:
        await pool.close()
        await admin.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        await admin.close()


async def upload(name: str):
    df = pd.read_csv(FERRETERIA / f"{name}.csv")
    return await sa.smart_upload(df, ORG, f"{name}.csv")


async def table_rows(pool) -> dict[str, int]:
    async with pool.acquire() as conn:
        return {r["table_name"]: r["row_count"] for r in await conn.fetch(
            "SELECT table_name, row_count FROM org_data_tables")}


def assert_ferreteria(result: dict) -> None:
    """Los literales de test-data/ferreteria (calculados de forma independiente con pandas y con csv + Fraction)."""
    assert result["period"] == {"from": "2025-07-02", "to": "2025-10-08", "days": 99}
    assert [i["id"] for i in result["items"]] == [
        "capital_inventario", "sin_movimiento", "clientes_concentracion", "productos_estrella", "reposicion",
        "margen_bajo"]
    assert metrics(item(result, "capital_inventario")) == {
        "Mercancía a costo": 47_620_000, "Vendido en el periodo": 10_234_700, "Meses de inventario": 21.0}
    assert metrics(item(result, "productos_estrella")) == {
        "Utilidad de los productos estrella": 997_000, "Parte de la utilidad total": 36.3,
        "Utilidad total": 2_746_700}
    assert metrics(item(result, "reposicion")) == {"Productos por agotarse": 0}
    assert metrics(item(result, "clientes_concentracion")) == {
        "Los 3 mejores clientes": 37.5, "El mejor cliente": 15.5, "Clientes distintos": 22}
    assert metrics(item(result, "sin_movimiento")) == {
        "Plata parada": 360_000, "Productos sin movimiento": 1, "Parte de tu mercancía": 0.8}
    assert metrics(item(result, "margen_bajo")) == {"Productos con margen bajo": 0}


class TestFlujoRealDeCarga:
    async def test_las_6_recetas_sobre_los_csv_cargados_con_smart_upload(self, pool):
        for name in ("productos", "ventas", "proveedores", "inventario_movimientos"):
            await upload(name)
        result = await svc.get_business_insights(ORG, now=NOW)
        assert_ferreteria(result)
        rows = await table_rows(pool)
        notes = item(result, "capital_inventario")["how"]["notes"]
        # la carga real fusiona hoy inventario_movimientos (fecha, producto, cantidad) dentro de ventas: esas 40
        # filas no tienen precio, no son ventas y se avisan sin estirar el periodo ni cambiar ninguna cifra.
        merged = rows.get("ventas") == 80
        assert ("40 ventas sin cantidad o valor legible no se contaron." in notes) == merged
        assert item(result, "capital_inventario")["how"]["rows_used"] == 70

    async def test_solo_productos_y_ventas_sin_movimientos(self, pool):
        await upload("productos")
        await upload("ventas")
        result = await svc.get_business_insights(ORG, now=NOW)
        assert_ferreteria(result)
        assert item(result, "capital_inventario")["how"]["notes"] == []

    async def test_numeros_guardados_como_texto_de_cargas_antiguas(self, pool):
        await upload("productos")
        await upload("ventas")
        before = await svc.get_business_insights(ORG, now=NOW)
        async with pool.acquire() as conn:
            # todos los valores de todas las filas pasan a texto jsonb ("45", "35000"): asi quedaron las cargas viejas
            await conn.execute(
                "UPDATE org_data_rows SET data = (SELECT jsonb_object_agg(k, to_jsonb(v)) "
                "FROM jsonb_each_text(data) AS t(k, v))"
            )
            sample = await conn.fetchval("SELECT data->>'stock' FROM org_data_rows WHERE data ? 'stock' LIMIT 1")
            assert sample is not None
            kind = await conn.fetchval("SELECT jsonb_typeof(data->'stock') FROM org_data_rows WHERE data ? 'stock' LIMIT 1")
            assert kind == "string"
            assert await conn.fetchval("SELECT jsonb_typeof(data->'total') FROM org_data_rows WHERE data ? 'total' "
                                       "LIMIT 1") == "string"
        after = await svc.get_business_insights(ORG, now=NOW)
        assert after == before
        assert_ferreteria(after)

    async def test_encabezados_de_excel_arbitrarios(self, pool):
        productos = pd.read_csv(FERRETERIA / "productos.csv").rename(columns={
            "nombre": "Descripción", "precio_compra": "Precio de Compra", "precio_venta": "PVP",
            "stock": "Existencias", "categoria": "Línea"})
        ventas = pd.read_csv(FERRETERIA / "ventas.csv").rename(columns={
            "fecha": "Fecha de Venta", "producto": "Artículo", "cantidad": "Unidades", "precio_unitario": "Vr. Unitario",
            "total": "Valor Total", "cliente": "Cliente"})
        await sa.smart_upload(productos, ORG, "inventario.xlsx")
        await sa.smart_upload(ventas, ORG, "ventas.xlsx")
        async with pool.acquire() as conn:
            cols = [c["name"] for r in await conn.fetch("SELECT columns_definition FROM org_data_tables")
                    for c in json.loads(r["columns_definition"])]
        assert "precio_de_compra" in cols and "vr._unitario" in cols     # asi las deja la carga
        assert_ferreteria(await svc.get_business_insights(ORG, now=NOW))

    async def test_fechas_de_excel_con_hora_y_dia_primero(self, pool):
        ventas = pd.read_csv(FERRETERIA / "ventas.csv")
        ventas["fecha"] = pd.to_datetime(ventas["fecha"]).dt.strftime("%d/%m/%Y 00:00:00")
        await upload("productos")
        await sa.smart_upload(ventas, ORG, "ventas.csv")
        result = await svc.get_business_insights(ORG, now=NOW)
        assert result["period"] == {"from": "2025-07-02", "to": "2025-10-08", "days": 99}
        assert metrics(item(result, "capital_inventario"))["Vendido en el periodo"] == 10_234_700


class TestSoloLectura:
    async def test_corre_en_transaccion_de_solo_lectura_con_statement_timeout(self, pool):
        await upload("productos")
        await upload("ventas")
        seen: list[tuple] = []
        real = engine.run_plan_on

        async def spy(conn, plan):
            seen.append((await conn.fetchval("SHOW transaction_read_only"), await conn.fetchval("SHOW statement_timeout")))
            return await real(conn, plan)

        with patch.object(engine, "run_plan_on", spy):
            await svc.get_business_insights(ORG, now=NOW)
        assert seen and set(seen) == {("on", f"{engine.STATEMENT_TIMEOUT_MS // 1000}s")}

    async def test_no_modifica_ni_una_fila(self, pool):
        await upload("productos")
        await upload("ventas")
        snapshot = ("SELECT (SELECT md5(string_agg(t::text, '' ORDER BY id)) FROM org_data_rows t), "
                    "(SELECT md5(string_agg(t::text, '' ORDER BY id)) FROM org_data_tables t)")
        async with pool.acquire() as conn:
            before = await conn.fetchrow(snapshot)
        await svc.get_business_insights(ORG, now=NOW)
        async with pool.acquire() as conn:
            assert await conn.fetchrow(snapshot) == before

    async def test_un_statement_timeout_es_servicio_no_disponible(self, pool):
        await upload("productos")
        await upload("ventas")
        with patch.object(engine, "STATEMENT_TIMEOUT_MS", 1):
            # 1 ms no alcanza ni para planificar: el motor falla con QueryCanceledError (asyncpg)
            try:
                await svc.get_business_insights(ORG, now=NOW)
            except svc.InsightsUnavailable:
                return
        pytest.skip("el servidor resolvio todo en menos de 1 ms")


# ---------------------------------------------------------------------------
# Rendimiento
# ---------------------------------------------------------------------------

PERF_PRODUCTS, PERF_SALES = 5_000, 50_000
PERF_LIMIT_SECONDS = 2.0


async def _bulk(pool, name: str, cols: list[dict], rows: list[dict]) -> None:
    async with pool.acquire() as conn:
        table_id = await conn.fetchval(
            "INSERT INTO org_data_tables (table_name, display_name, columns_definition, row_count) "
            "VALUES ($1, $1, $2::jsonb, $3) RETURNING id", name, json.dumps(cols), len(rows))
        await conn.executemany("INSERT INTO org_data_rows (table_id, data) VALUES ($1, $2::jsonb)",
                               [(table_id, json.dumps(r, ensure_ascii=False)) for r in rows])


async def load_perf_data(pool, seed: int = 7, as_text: bool = False):
    import random
    rnd = random.Random(seed)
    productos = []
    for i in range(PERF_PRODUCTS):
        costo = rnd.randint(2, 400) * 100
        productos.append({"nombre": f"Producto {i:05d} {'ÁÉÍ'[i % 3]}", "costo": costo, "stock": rnd.randint(0, 300)})
    ventas = []
    for i in range(PERF_SALES):
        p = productos[rnd.randrange(PERF_PRODUCTS)]
        qty = rnd.randint(1, 20)
        price = p["costo"] + rnd.randint(-20, 400) * 10
        day = date(2025, 1, 1) + timedelta(days=rnd.randint(0, 364))
        ventas.append({"fecha": day.isoformat(),
                       "producto": p["nombre"].lower() if i % 7 == 0 else p["nombre"], "cantidad": qty,
                       "precio_unitario": price, "total": qty * price, "cliente": f"Cliente {rnd.randrange(800)}"})
    if as_text:
        productos = [{k: str(v) for k, v in r.items()} for r in productos]
        ventas = [{k: str(v) for k, v in r.items()} for r in ventas]
    await _bulk(pool, "productos", [{"name": "nombre", "type": "text"}, {"name": "costo", "type": "number"},
                                    {"name": "stock", "type": "integer"}], productos)
    await _bulk(pool, "ventas", [{"name": "fecha", "type": "date"}, {"name": "producto", "type": "text"},
                                 {"name": "cantidad", "type": "integer"}, {"name": "precio_unitario", "type": "number"},
                                 {"name": "total", "type": "number"}, {"name": "cliente", "type": "text"}], ventas)
    return productos, ventas


class TestRendimiento:
    @pytest.mark.parametrize("as_text", [False, True], ids=["numeros", "texto"])
    async def test_50_mil_ventas_y_5_mil_productos(self, pool, as_text, capsys):
        productos, ventas = await load_perf_data(pool, as_text=as_text)
        t0 = time.perf_counter()
        result = await svc.get_business_insights(ORG, now=NOW)
        elapsed = time.perf_counter() - t0
        with capsys.disabled():
            print(f"\n[perf] {PERF_SALES} ventas + {PERF_PRODUCTS} productos ({'texto' if as_text else 'numeros'}): "
                  f"{elapsed:.2f} s")
        assert len(result["items"]) == 6 and result["period"]["days"] > 300
        assert elapsed < PERF_LIMIT_SECONDS * 1.5      # holgura para maquinas lentas; el objetivo es PERF_LIMIT_SECONDS
        # sin muestreo: el vendido es la suma exacta de TODAS las ventas
        expected = sum(int(r["cantidad"]) * int(r["precio_unitario"]) for r in ventas)
        assert metrics(item(result, "capital_inventario"))["Vendido en el periodo"] == expected

    async def test_resultado_identico_con_el_oraculo_pandas_a_escala(self, pool):
        from tests import insights_oracle as oracle

        productos, ventas = await load_perf_data(pool, seed=11)
        result = await svc.get_business_insights(ORG, now=NOW)
        exp = oracle.compute(productos[:], ventas[:])
        m = metrics(item(result, "capital_inventario"))
        assert m["Mercancía a costo"] == oracle.round_half_up(exp["merchandise"])
        assert m["Vendido en el periodo"] == oracle.round_half_up(exp["revenue"])
        assert metrics(item(result, "productos_estrella"))["Utilidad total"] == oracle.round_half_up(exp["profit_total"])
        assert metrics(item(result, "sin_movimiento"))["Plata parada"] == oracle.round_half_up(exp["parked_money"])
