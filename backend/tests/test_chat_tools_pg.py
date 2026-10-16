"""Motor de consultas del chat (data_query_engine) contra un Postgres REAL desechable — PI0320251.

Se OMITE por defecto: necesita un Postgres local, descartable y accesible sin contrasena (trust) cuyo puerto
se indica en CHAT_TOOLS_TEST_PG_PORT (usuario en CHAT_TOOLS_TEST_PG_USER, por defecto 'tester'). Solo acepta
127.0.0.1 y crea/borra su propia base 'chat_tools_test_<uuid>'. NUNCA apuntar a Neon ni a ningun servidor
compartido. Gemini no participa: se ejecutan las herramientas y el motor directamente.

Cubre lo que la BD emulada no puede, el SQL que compila el motor:
- Correccion numerica: cada plan corre en Postgres y en el oraculo pandas (tests/query_oracle.py) sobre LAS
  MISMAS filas (nulos, numeros viejos como texto, valores no numericos, fechas en varios formatos e invalidas,
  si/no, unicode) y los resultados deben coincidir.
- Inyeccion: valores y nombres maliciosos son inertes y los datos quedan intactos; la transaccion es de solo
  lectura y lleva statement_timeout.

Ejemplo (PowerShell): $env:CHAT_TOOLS_TEST_PG_PORT=54872; pytest tests/test_chat_tools_pg.py
"""

import json
import os
import random
import time
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.services import data_query_engine as engine
from tests import query_oracle

PORT = os.environ.get("CHAT_TOOLS_TEST_PG_PORT")
pytestmark = pytest.mark.skipif(not PORT, reason="define CHAT_TOOLS_TEST_PG_PORT para usar un Postgres local desechable")

asyncpg = pytest.importorskip("asyncpg")

HOST = "127.0.0.1"  # fijo a proposito

COLUMNS = {
    "codigo": "text", "producto": "text", "ciudad": "text", "total": "number", "cantidad": "integer",
    "fecha": "date", "activo": "boolean",
}
PRODUCTOS = ["Martillo", "Taladro", "Ñandú", "Café ☕", "sierra", "SIERRA", " Sierra ", "", "a|b", "100%_x",
             "O'Brien", "Árbol", "zeta", "Zeta"]
CIUDADES = ["Bogotá", "Medellín", "Cali", None, "bogotá"]
TOTALES = [100, 250.75, -30, 0, 0.1, 1e20, 10**25, "300", " 42.5 ", "1e3", "-.5", "+7", "5.", "1E-2",
           "n/a", "$1.200", "1,5", "", "NaN", "Infinity", "٣", "1e9999", True, None, "MISSING"]
FECHAS = ["2026-03-15", "2026-03-15 10:00:00", "2026-03-15T10:00:00", "15/03/2026", "5-1-2026", "2026/1/5",
          "2025-12-31", "2026-02-28", "2024-02-29", "2026-02-30", "13/13/2026", "0000-01-01", "9999-12-31",
          "no es fecha", "", None, "MISSING", " 2026-01-07", "2026-1-9"]
ACTIVOS = [True, False, "si", "no", "Sí", "1", "0", "tal vez", None, "MISSING"]


def make_rows(n: int, seed: int = 20261014) -> list[dict]:
    rnd = random.Random(seed)
    rows = []
    for i in range(n):
        row = {"codigo": f"C{i:05d}"}
        for col, choices in (("producto", PRODUCTOS), ("ciudad", CIUDADES), ("total", TOTALES),
                             ("fecha", FECHAS), ("activo", ACTIVOS)):
            value = rnd.choice(choices)
            if value != "MISSING":
                row[col] = value
        row["cantidad"] = rnd.choice([1, 2, 3, "4", " 5", None, "x", 10, 20])
        rows.append(row)
    rows.append(["no", "es", "objeto"])     # filas jsonb que no son objetos: no deben romper nada
    rows.append("texto suelto")
    return rows


@pytest.fixture
async def pg():
    from app import database

    user = os.environ.get("CHAT_TOOLS_TEST_PG_USER", "tester")
    dbname = f"chat_tools_test_{uuid.uuid4().hex[:8]}"
    admin = await asyncpg.connect(host=HOST, port=int(PORT), user=user, database="postgres")
    await admin.execute(f'CREATE DATABASE "{dbname}"')
    pool = await asyncpg.create_pool(host=HOST, port=int(PORT), user=user, database=dbname, min_size=1, max_size=10)
    try:
        async with pool.acquire() as conn:
            await conn.execute(database.ORG_BASE_SCHEMA_SQL)
        yield pool
    finally:
        await pool.close()
        await admin.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        await admin.close()


async def add_table(pool, name: str, columns: dict, rows: list) -> uuid.UUID:
    async with pool.acquire() as conn:
        table_id = await conn.fetchval(
            "INSERT INTO org_data_tables (table_name, display_name, columns_definition, row_count) "
            "VALUES ($1, $2, $3::jsonb, $4) RETURNING id",
            name, name.title(), json.dumps([{"name": c, "type": t} for c, t in columns.items()]), len(rows),
        )
        await conn.executemany(
            "INSERT INTO org_data_rows (table_id, data) VALUES ($1, $2::jsonb)",
            [(table_id, json.dumps(r, ensure_ascii=False)) for r in rows],
        )
    return table_id


async def catalog_of(pool) -> dict:
    async with pool.acquire() as conn:
        records = await conn.fetch(
            "SELECT id, table_name, display_name, row_count, columns_definition FROM org_data_tables"
        )
    return engine.build_catalog(records)


def same(a, b) -> bool:
    if isinstance(a, Decimal) and isinstance(b, Decimal):
        return abs(a - b) <= Decimal("1e-12") * max(Decimal(1), abs(b))
    return a == b


def assert_same_result(pg_result, oracle_result, spec):
    assert pg_result.total == oracle_result.total, spec
    assert pg_result.bad == oracle_result.bad, spec
    assert len(pg_result.rows) == len(oracle_result.rows), (spec, pg_result.rows, oracle_result.rows)
    for got, want in zip(pg_result.rows, oracle_result.rows):
        assert len(got) == len(want) and all(same(g, w) for g, w in zip(got, want)), (spec, got, want)


SPECS = [
    {"aggregates": ["count", "count(total)", "count_distinct(total)", "sum(total)", "avg(total)", "min(total)",
                    "max(total)"]},
    {"aggregates": ["count_distinct(producto)", "min(producto)", "max(producto)", "min(fecha)", "max(fecha)",
                    "count(activo)", "count_distinct(fecha)"]},
    {"group_by": ["producto"], "aggregates": ["sum(total)", "avg(total)", "count"], "limit": 50},
    {"group_by": ["ciudad", "month(fecha)"], "aggregates": ["sum(total)", "count"], "limit": 50},
    {"group_by": ["week(fecha)"], "aggregates": ["count", "max(total)"], "limit": 50},
    {"group_by": ["day(fecha)"], "aggregates": ["count"], "order_by": ["-count"], "limit": 7},
    {"group_by": ["year(fecha)"], "aggregates": ["count", "avg(cantidad)"], "limit": 50},
    {"group_by": ["ciudad"], "order_by": ["-count"], "limit": 2},                          # top-N con empates
    {"group_by": ["cantidad"], "aggregates": ["count"], "order_by": ["cantidad"], "limit": 50},
    {"group_by": ["fecha"], "aggregates": ["count"], "order_by": ["-fecha"], "limit": 50},
    {"group_by": ["producto"], "aggregates": ["min(fecha)", "max(fecha)"], "order_by": ["-max(fecha)"], "limit": 50},
    {"group_by": ["activo"], "aggregates": ["count"], "limit": 50},
    {"filters": [["total", ">", "100"]], "aggregates": ["count", "sum(total)"]},
    {"filters": [["total", ">=", "42.5"], ["total", "<", 1000]], "aggregates": ["count", "sum(total)"]},
    {"filters": [["total", "in", "300", 42.5, "1000", "7"]], "aggregates": ["count"]},
    {"filters": [["total", "!=", "300"]], "aggregates": ["count"]},
    {"filters": [["total", "<", "0"]], "group_by": ["producto"], "aggregates": ["sum(total)"], "limit": 50},
    {"filters": [["fecha", "=", "2026-03"]], "aggregates": ["count"]},
    {"filters": [["fecha", ">=", "2026-01-01"], ["fecha", "<", "2026-03-15"]], "aggregates": ["count"]},
    {"filters": [["fecha", "<", "2026"]], "aggregates": ["count"]},
    {"filters": [["fecha", "<=", "2025"]], "aggregates": ["count"]},
    {"filters": [["fecha", ">", "2026-02"]], "aggregates": ["count"]},
    {"filters": [["fecha", "in", "2026-03", "05/01/2026"]], "aggregates": ["count"]},
    {"filters": [["fecha", "!=", "2026-03-15"]], "aggregates": ["count"]},
    {"filters": [["producto", "=", "sierra"]], "aggregates": ["count"]},
    {"filters": [["producto", "=", "ñandú"]], "aggregates": ["count"]},
    {"filters": [["producto", "!=", "Martillo"]], "aggregates": ["count"]},
    {"filters": [["producto", "in", "taladro", "café ☕", "o'brien"]], "aggregates": ["count"]},
    {"filters": [["producto", "contains", "ER"]], "aggregates": ["count"]},
    {"filters": [["producto", "contains", "%"]], "aggregates": ["count"]},
    {"filters": [["producto", "contains", "_"]], "aggregates": ["count"]},
    {"filters": [["producto", ">", "M"]], "aggregates": ["count"]},
    {"filters": [["codigo", ">", "C00100"]], "aggregates": ["count"]},
    {"filters": [["activo", "=", "true"]], "aggregates": ["count"]},
    {"filters": [["activo", "!=", "false"]], "aggregates": ["count"]},
    {"filters": [["activo", "in", "si", "no"]], "aggregates": ["count"]},
    {"filters": [["ciudad", "null"]], "aggregates": ["count"]},
    {"filters": [["ciudad", "notnull"], ["producto", "notnull"]], "group_by": ["ciudad"], "limit": 50},
    {"select": ["codigo", "total", "fecha"], "filters": [["total", ">", "0"]], "order_by": ["-total", "codigo"],
     "limit": 50},
    {"select": ["codigo", "producto"], "order_by": ["-fecha", "codigo"], "limit": 30},
    {"select": ["codigo", "month(fecha)"], "filters": [["fecha", "=", "2026"]], "order_by": ["codigo"], "limit": 10},
]


@pytest.fixture
async def ventas(pg):
    rows = make_rows(600)
    await add_table(pg, "ventas", COLUMNS, rows)
    await add_table(pg, "otra", {"total": "number"}, [{"total": 999999}] * 5)   # no debe colarse
    catalog = await catalog_of(pg)
    return rows, catalog


@pytest.mark.parametrize("spec", SPECS, ids=[json.dumps(s, ensure_ascii=False)[:60] for s in SPECS])
async def test_resultado_identico_al_oraculo_pandas(pg, ventas, spec):
    rows, catalog = ventas
    plan = engine.build_plan(catalog["ventas"], max_rows=50, **spec)

    (pg_result,) = await engine.run_plans(pg, [plan])
    oracle_result = query_oracle.run_plan(rows, plan)

    assert_same_result(pg_result, oracle_result, spec)
    # y el texto que recibiria el modelo es el mismo
    assert engine.format_result(plan, pg_result, max_chars=3000) == engine.format_result(
        plan, oracle_result, max_chars=3000
    )


async def test_el_dataset_ejercita_los_casos_dificiles(pg, ventas):
    """Guardia del test anterior: si el dataset dejara de tener estos casos, la comparacion valdria menos."""
    rows, catalog = ventas
    plan = engine.build_plan(catalog["ventas"], aggregates=["count", "count(total)", "sum(total)", "count(fecha)"],
                             max_rows=50)
    (result,) = await engine.run_plans(pg, [plan])

    assert result.bad["total"] > 30                         # celdas no numericas ignoradas y reportadas
    count, with_total, _sum, with_fecha = result.rows[0]
    assert count == 602 and with_total < count and with_fecha < count
    (by_month,) = await engine.run_plans(pg, [engine.build_plan(
        catalog["ventas"], group_by=["month(fecha)"], max_rows=50)])
    labels = [r[0] for r in by_month.rows]
    assert None in labels and "2026-03" in labels and "2026-01" in labels and "9999-12" in labels


async def test_las_herramientas_completas_dan_el_mismo_texto_en_postgres_y_en_el_oraculo(pg, ventas):
    from app.services.agent_tools_service import _Limits, _build_tools

    rows, catalog = ventas
    calls = [
        ("describe_table", {"table": "ventas"}),
        ("query_table", {"table": "ventas", "group_by": ["month(fecha)"], "aggregates": ["sum(total)"]}),
        ("query_table", {"table": "ventas", "select": ["codigo", "producto", "total"], "order_by": ["codigo"],
                         "limit": 1000}),
        ("create_chart", {"table": "ventas", "chart_type": "line", "x": "month(fecha)", "y": "sum(total)"}),
    ]

    async def run(pool):
        charts: list = []
        tools = _build_tools(pool, catalog, charts, _Limits(rows=50, chars=3000))
        return [await tools[name](**args) for name, args in calls], charts

    class OraclePool:
        db = type("db", (), {"rows_of": staticmethod(lambda tid: rows if tid == catalog["ventas"].id else [])})

    pg_out = await run(pg)
    with patch("app.services.data_query_engine.run_plans", query_oracle.fake_run_plans()):
        oracle_out = await run(OraclePool())

    assert pg_out == oracle_out
    assert "(mostrando" in pg_out[0][2]["result"]             # el select de 1000 se acoto


INJECTIONS = [
    "' OR 1=1 --", "x'); DROP TABLE org_data_rows; --", "(SELECT data FROM org_data_rows LIMIT 1)",
    "ü'; DELETE FROM org_data_tables; --", "\\'; SELECT pg_sleep(5); --", "$$; DROP TABLE x; $$",
    "%' OR '%'='", "Martillo' UNION SELECT data::text FROM org_data_rows --",
]


async def _row_counts(pool):
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT count(*) FROM org_data_rows"), await conn.fetchval(
            "SELECT count(*) FROM org_data_tables"
        )


@pytest.mark.parametrize("value", INJECTIONS)
async def test_valores_maliciosos_son_inertes(pg, ventas, value):
    _rows, catalog = ventas
    before = await _row_counts(pg)
    plans = [
        engine.build_plan(catalog["ventas"], filters=[[col, op, value]], aggregates=["count"], max_rows=50)
        for col, op in (("producto", "="), ("producto", "contains"), ("producto", "in"), ("producto", "<"),
                        ("producto", "!="))
    ]

    results = await engine.run_plans(pg, plans)

    eq, contains, in_, lt, ne = (r.rows[0][0] for r in results)
    assert (eq, contains, in_) == (0, 0, 0)
    assert lt + ne > 0                                      # comparaciones normales, no un error ni un 1=1
    assert await _row_counts(pg) == before


@pytest.mark.parametrize("name", INJECTIONS + ['total"', "producto'", "a;b"])
async def test_nombres_de_columna_maliciosos_viajan_como_parametro_aunque_salten_la_validacion(pg, ventas, name):
    _rows, catalog = ventas
    before = await _row_counts(pg)
    evil = engine.Column(name, "n")
    plan = engine.Plan(
        catalog["ventas"].id,
        (engine.Key(f"month({name})", evil, "month"),),
        (engine.Agg(f"sum({name})", "sum", evil, "n"), engine.Agg("count", "count", None)),
        (engine.Filter(evil, "notnull", "k", ()),),
        (engine.Order(1, True, "out"),),
        10,
    )

    (result,) = await engine.run_plans(pg, [plan])

    assert result.rows == [] and result.total == 0          # ninguna fila tiene esa clave
    assert await _row_counts(pg) == before


async def test_el_locale_de_la_bd_compara_sin_mayusculas_en_unicode(pg):
    """Requisito de locale del motor (ver docstring de data_query_engine): '=', 'in', group_by y contains
    usan lower()/ILIKE. Con un locale "C" de libc esto da false y 'Ñandú' = 'ñandú' dejaria de coincidir."""
    async with pg.acquire() as conn:
        assert await conn.fetchval("SELECT lower('ÑANDÚ') = 'ñandú' AND 'Ñandú' ILIKE '%ÑAN%'") is True


async def test_la_tabla_de_otra_tabla_no_se_mezcla(pg, ventas):
    _rows, catalog = ventas
    plan = engine.build_plan(catalog["otra"], aggregates=["sum(total)", "count"], max_rows=50)

    (result,) = await engine.run_plans(pg, [plan])

    assert result.rows == [(Decimal(999999 * 5), 5)]


async def test_la_transaccion_es_de_solo_lectura_y_con_statement_timeout(pg, ventas):
    _rows, catalog = ventas
    plan = engine.Plan(catalog["ventas"].id, (), (engine.Agg("count", "count", None),), (), (), 1)
    before = await _row_counts(pg)

    with patch.object(engine, "compile_plan", return_value=(
        "SELECT current_setting('statement_timeout') AS o0, "
        "current_setting('transaction_read_only') AS o1, 1 AS total__", [],
    )):
        two_cols = engine.Plan(plan.table_id, (), (engine.Agg("a", "count", None), engine.Agg("b", "count", None)),
                               (), (), 1)
        (result,) = await engine.run_plans(pg, [two_cols])
    assert result.rows == [("8s", "on")]

    with patch.object(engine, "compile_plan", return_value=("DELETE FROM org_data_rows RETURNING 1 AS o0", [])):
        with pytest.raises(asyncpg.exceptions.ReadOnlySQLTransactionError):
            await engine.run_plans(pg, [plan])
    assert await _row_counts(pg) == before


async def test_rendimiento_de_referencia_50k_filas(pg, capsys):
    rows = make_rows(50_000, seed=7)
    started = time.monotonic()
    await add_table(pg, "grande", COLUMNS, rows)
    loaded = time.monotonic() - started
    catalog = await catalog_of(pg)
    table = catalog["grande"]
    timings = {}
    for label, spec in {
        "sum+avg sin agrupar": {"aggregates": ["sum(total)", "avg(total)", "count"]},
        "group_by month(fecha)": {"group_by": ["month(fecha)"], "aggregates": ["sum(total)"]},
        "group_by producto + filtro fecha": {"group_by": ["producto"], "aggregates": ["sum(total)"],
                                             "filters": [["fecha", ">=", "2026-01"]]},
    }.items():
        plan = engine.build_plan(table, max_rows=50, **spec)
        started = time.monotonic()
        await engine.run_plans(pg, [plan])
        timings[label] = time.monotonic() - started
    started = time.monotonic()
    await engine.describe(pg, table, max_chars=3000)
    timings["describe_table"] = time.monotonic() - started

    with capsys.disabled():
        print(f"\n[perf 50k filas] carga {loaded:.2f}s; " + "; ".join(f"{k} {v * 1000:.0f} ms" for k, v in timings.items()))
    assert all(v < engine.STATEMENT_TIMEOUT_MS / 1000 for v in timings.values())

    # Un statement_timeout real (1 ms) llega al modelo como error corto y accionable, no "error interno".
    from google.genai import types as genai_types

    from app.services.agent_tools_service import _Limits, _build_tools, _execute_call

    tools = _build_tools(pg, catalog, [], _Limits(rows=50, chars=3000))
    call = genai_types.FunctionCall(name="describe_table", args={"table": "grande"})
    with patch.object(engine, "STATEMENT_TIMEOUT_MS", 1):
        response = await _execute_call(call, tools)
    assert response == {"error": "la consulta tardó demasiado: filtra, agrupa o pide menos columnas"}
