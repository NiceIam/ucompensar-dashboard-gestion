"""Detalle (drill) y filtros globales contra un Postgres REAL desechable — PI0320251.

Se OMITE por defecto: define CHAT_TOOLS_TEST_PG_PORT (ver test_dashboards_pg.py). Aqui el motor es el REAL (SQL
con `->>`, fechas por regex, LATERAL, agrupacion normalizada), asi que prueba lo que el oraculo en pandas no puede:
que los mismos valores esperados A MANO (modulo `csv` sobre `brujula-demo/datos-expo/ventas.csv`, 731 filas, y
`test-data/ferreteria`) salgan del SQL de verdad. Mismas cifras que test_dashboards_drill.py / test_dashboards_filters.py.
"""

import json
import os
import time
import uuid
from collections import Counter
from datetime import date
from unittest.mock import patch

import pytest

from app.services import dashboard_builder_service as builder
from app.services import dashboard_drill_service as drill_service
from app.services import dashboard_filter_options_service as options_service
from app.services import data_query_engine as engine
from app.services.dashboard_drill_service import DrillError
from app.services.dashboard_render_service import render_dashboard
from tests.dash_support import FERRETERIA, PRODUCTOS_TYPES, VENTAS_TYPES, read_csv
from tests.test_dashboards_drill import DEMO, ROLES, TODAY, TYPES, W, demo_rows, needs_demo
from tests.test_dashboards_pg import catalog_of, pg, patched  # noqa: F401  (fixtures y ayudantes del Postgres desechable)

PORT = os.environ.get("CHAT_TOOLS_TEST_PG_PORT")
pytestmark = pytest.mark.skipif(not PORT, reason="define CHAT_TOOLS_TEST_PG_PORT para usar un Postgres local desechable")


@pytest.fixture(autouse=True)
def fixed_today():
    with patch("app.services.dashboard_filters.today_co", return_value=TODAY):
        yield


async def add_demo_ventas(pool, *, roles: bool = True) -> uuid.UUID:
    """ventas.csv de la demo, con numeros como numeros y (opcional) la metadata de la carga inteligente."""
    from app.services import intake_ontology as onto

    columns, rows = read_csv(DEMO, TYPES)
    cols = [{"name": c, "type": TYPES.get(c, "text"), **({"role": ROLES[c], "role_confidence": 0.9, "label": c} if roles and c in ROLES else {})}
            for c in columns]
    if roles:
        cols = onto.with_sheet_meta(cols, onto.make_sheet_meta("ventas", 0.9, "user", None))
    async with pool.acquire() as conn:
        table_id = await conn.fetchval(
            "INSERT INTO org_data_tables (table_name, display_name, columns_definition, row_count) "
            "VALUES ('ventas', 'Ventas', $1::jsonb, $2) RETURNING id", json.dumps(cols), len(rows))
        await conn.executemany("INSERT INTO org_data_rows (table_id, data) VALUES ($1, $2::jsonb)",
                               [(table_id, json.dumps(r, ensure_ascii=False)) for r in rows])
    return table_id


async def make_board(pool, names):
    catalog = await catalog_of(pool)
    created, omitted = await builder.build_dashboard(pool, catalog, "Tablero PG", [W[n] if isinstance(n, str) else n for n in names])
    assert not omitted
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, widget_type, data_source_query FROM widgets WHERE dashboard_id = $1", uuid.UUID(created["id"]))
    widgets = {}
    for r in rows:
        dsq = json.loads(r["data_source_query"]) if isinstance(r["data_source_query"], str) else r["data_source_query"]
        widgets[(r["widget_type"], dsq.get("x") or "kpi")] = str(r["id"])
    return created["id"], widgets


def kpi(out, label):
    return next(k for k in out["kpis"] if k["label"] == label)


@needs_demo
class TestDetalleSQLReal:
    async def test_dia_por_producto_cliente_y_forma_de_pago(self, pg, patched):
        await add_demo_ventas(pg)
        did, w = await make_board(pg, ["dia"])
        widget = w[("line_chart", "day(fecha)")]
        out = await drill_service.drill("o", did, widget, {"value": "2026-07-27"})
        assert out["title"] == "Ventas del 27 de julio de 2026" and out["total"] == 1_004_000 and out["records"] == 19
        assert out["by"]["by"] == "producto" and out["groups"] == 15
        assert [(r["name"], r["value"]) for r in out["rows"][:3]] == [
            ("Tubería PVC presión 1/2 x 6m", 400_500), ("Pintura vinilo blanco galón", 156_600), ("Cemento gris Argos 50kg", 68_000)]
        assert sum(r["value"] for r in out["rows"]) == 1_004_000
        by_client = await drill_service.drill("o", did, widget, {"value": "2026-07-27", "by": "cliente"})
        assert [(r["name"], r["value"]) for r in by_client["rows"]] == [
            ("Remodelaciones Acosta e Hijos", 465_000), ("Constructora Andes SAS", 362_300), ("Mostrador", 66_000),
            ("(sin dato)", 42_200), ("Nelly Patricia Roa", 31_500), ("Luz Marina Cifuentes", 23_800),
            ("Conjunto Residencial Los Almendros", 13_200)]
        by_pay = await drill_service.drill("o", did, widget, {"value": "2026-07-27", "by": "metodo_pago"})
        assert [(r["name"], r["value"]) for r in by_pay["rows"]] == [("efectivo", 574_200), ("credito", 362_300), ("tarjeta", 67_500)]

    async def test_mes_truncamiento_y_dia_cronologico(self, pg, patched):
        await add_demo_ventas(pg)
        did, w = await make_board(pg, ["mes"])
        widget = w[("line_chart", "month(fecha)")]
        out = await drill_service.drill("o", did, widget, {"value": "2026-09"})
        assert out["total"] == 6_687_300 and out["records"] == 141 and out["groups"] == 39 and out["shown"] == 20
        assert out["message"] == "Mostrando 20 de 39" and out["rest"] == {"groups": 19, "value": 844_300}
        by_day = await drill_service.drill("o", did, widget, {"value": "2026-09", "by": "day(fecha)"})
        expected = Counter()
        for r in demo_rows():
            if r["fecha"].startswith("2026-09"):
                expected[r["fecha"]] += int(r["total"])
        assert by_day["groups"] == 28 and [(r["name"], r["value"]) for r in by_day["rows"]] == sorted(expected.items())

    async def test_semana_y_ano(self, pg, patched):
        await add_demo_ventas(pg)
        did, w = await make_board(pg, [
            {"table": "ventas", "chart_type": "line", "x": "week(fecha)", "y": "sum(total)"},
            {"table": "ventas", "chart_type": "bar", "x": "year(fecha)", "y": "sum(total)"}])
        week = await drill_service.drill("o", did, w[("line_chart", "week(fecha)")], {"value": "2026-07-27"})
        assert week["total"] == 1_427_200 and week["records"] == 40 and week["title"] == "Ventas de la semana del 27 de julio de 2026"
        year = await drill_service.drill("o", did, w[("bar_chart", "year(fecha)")], {"value": "2026", "by": "month(fecha)"})
        assert year["total"] == 44_527_400 and [r["value"] for r in year["rows"]] == [
            8_555_300, 7_321_600, 7_926_900, 8_294_200, 6_687_300, 5_742_100]
        with pytest.raises(DrillError):
            await drill_service.drill("o", did, w[("line_chart", "week(fecha)")], {"value": "2026-07-28"})       # no es lunes

    async def test_categoria_pastel_otros_y_sin_dato(self, pg, patched):
        await add_demo_ventas(pg)
        did, w = await make_board(pg, ["producto", "torta_producto", "cliente", "pago"])
        cem = await drill_service.drill("o", did, w[("bar_chart", "producto")], {"value": "cemento GRIS argos 50kg"})
        assert cem["total"] == 2_802_400 and cem["records"] == 22 and cem["by"]["by"] == "cliente"
        months = await drill_service.drill("o", did, w[("bar_chart", "producto")], {"value": "Cemento gris Argos 50kg", "by": "month(fecha)"})
        assert [r["value"] for r in months["rows"]] == [304_100, 810_000, 305_000, 336_000, 505_800, 541_500]
        otros = await drill_service.drill("o", did, w[("pie_chart", "producto")], {"other": True})
        assert otros["total"] == 13_282_800 and otros["groups"] == 42 and sum(r["value"] for r in otros["rows"]) == 13_282_800
        none = await drill_service.drill("o", did, w[("bar_chart", "cliente")], {"value": None})
        assert none["total"] == 5_869_200 and none["records"] == 211 and none["title"] == "Ventas sin cliente"
        credit = await drill_service.drill("o", did, w[("pie_chart", "metodo_pago")], {"value": "credito"})
        assert credit["total"] == 18_022_900 and credit["records"] == 119

    async def test_clave_exacta_de_un_nombre_largo(self, pg, patched):
        await add_demo_ventas(pg)
        did, w = await make_board(pg, [{"table": "ventas", "chart_type": "bar", "x": "producto", "y": "sum(total)", "top": 20}])
        bar = (await render_dashboard("o", did))["charts"][0]
        point = next(p for p in bar["data"] if p["name"].startswith("Grifería lavamanos"))
        assert point["key"] == "Grifería lavamanos monocontrol cromo"
        out = await drill_service.drill("o", did, bar["id"], {"value": point["key"]})
        assert out["total"] == 6_472_000

    async def test_filtros_en_el_detalle(self, pg, patched):
        await add_demo_ventas(pg)
        did, w = await make_board(pg, ["producto", "mes"])
        cem = w[("bar_chart", "producto")]
        july = await drill_service.drill("o", did, cem, {"value": "Cemento gris Argos 50kg",
                                                        "filters": {"period": {"from": "2026-07-01", "to": "2026-07-31"}}})
        assert july["total"] == 305_000 and july["records"] == 4
        both = await drill_service.drill("o", did, cem, {"value": "Cemento gris Argos 50kg", "filters": {
            "period": {"from": "2026-07-01", "to": "2026-07-31"}, "where": [{"key": "cliente", "values": ["constructora andes sas"]}]}})
        assert both["total"] == 168_000 and both["records"] == 1
        sept = await drill_service.drill("o", did, w[("line_chart", "month(fecha)")], {
            "value": "2026-09", "filters": {"where": [{"key": "metodo_pago", "values": ["credito", "efectivo"]}]}})
        assert sept["total"] == 4_598_600 and sept["records"] == 79

    async def test_valores_hostiles_no_tocan_los_datos(self, pg, patched):
        await add_demo_ventas(pg)
        did, w = await make_board(pg, ["producto", "dia"])
        for value in ("'; DROP TABLE org_data_rows; --", "x' OR '1'='1", "%", "_", "\\", "Cemento%' UNION SELECT data FROM org_data_rows --"):
            out = await drill_service.drill("o", did, w[("bar_chart", "producto")], {"value": value})
            assert out["records"] == 0 and out["rows"] == []
            out = await options_service.filter_options("o", did, key="producto", q=value)
            assert out["dimensions"][0]["values"] == []
        for by in ("'; DROP TABLE x; --", "month(precio_unitario)", "fecha", "total"):
            with pytest.raises(DrillError):
                await drill_service.drill("o", did, w[("bar_chart", "producto")], {"value": "x", "by": by})
        async with pg.acquire() as conn:
            assert await conn.fetchval("SELECT count(*) FROM org_data_rows") == 731

    async def test_es_rapido_y_solo_lectura(self, pg, patched):
        await add_demo_ventas(pg)
        did, w = await make_board(pg, ["mes"])
        started = time.monotonic()
        await drill_service.drill("o", did, w[("line_chart", "month(fecha)")], {"value": "2026-09"})
        assert time.monotonic() - started < 3
        async with pg.acquire() as conn:
            assert await conn.fetchval("SELECT count(*) FROM org_data_rows") == 731
            before = await conn.fetchval("SELECT string_agg(data_source_query::text, '|' ORDER BY id) FROM widgets")
        await drill_service.drill("o", did, w[("line_chart", "month(fecha)")], {"value": "2026-09", "filters": {"period": {"preset": "last_30"}}})
        await render_dashboard("o", did, {"period": {"preset": "last_30"}})
        async with pg.acquire() as conn:
            assert await conn.fetchval("SELECT string_agg(data_source_query::text, '|' ORDER BY id) FROM widgets") == before


@needs_demo
class TestFiltrosSQLReal:
    async def test_periodo_y_categorias_cambian_los_totales(self, pg, patched):
        await add_demo_ventas(pg)
        did, _ = await make_board(pg, ["kpi", "mes", "pago"])
        assert kpi(await render_dashboard("o", did), "Total vendido")["value"] == 44_527_400
        rng = await render_dashboard("o", did, {"period": {"from": "2026-07-10", "to": "2026-07-20"}})
        assert kpi(rng, "Total vendido")["value"] == 2_672_300
        pie = next(c for c in rng["charts"] if c["type"] == "pie")
        assert {p["name"]: p["value"] for p in pie["data"]}["credito"] == 1_738_700
        assert kpi(await render_dashboard("o", did, {"period": {"preset": "last_month"}}), "Total vendido")["value"] == 6_687_300
        assert kpi(await render_dashboard("o", did, {"period": {"preset": "this_month"}}), "Total vendido")["value"] == 5_742_100
        cred = await render_dashboard("o", did, {"where": [{"key": "metodo_pago", "values": ["credito"]}]})
        assert kpi(cred, "Total vendido")["value"] == 18_022_900
        combo = await render_dashboard("o", did, {"period": {"from": "2026-09-01", "to": "2026-09-30"},
                                                  "where": [{"key": "metodo_pago", "values": ["credito", "efectivo"]}]})
        assert kpi(combo, "Total vendido")["value"] == 4_598_600
        empty = await render_dashboard("o", did, {"period": {"from": "2027-01-01", "to": "2027-01-31"}})
        assert kpi(empty, "Total vendido")["value"] == 0 and all(c["empty"] for c in empty["charts"])

    async def test_hojas_sin_fecha_o_sin_categoria_no_se_rompen(self, pg, patched):
        await add_demo_ventas(pg)
        columns, rows = read_csv(FERRETERIA / "productos.csv", PRODUCTOS_TYPES)
        async with pg.acquire() as conn:
            tid = await conn.fetchval(
                "INSERT INTO org_data_tables (table_name, display_name, columns_definition, row_count) "
                "VALUES ('productos', 'Productos', $1::jsonb, $2) RETURNING id",
                json.dumps([{"name": c, "type": PRODUCTOS_TYPES.get(c, "text")} for c in columns]), len(rows))
            await conn.executemany("INSERT INTO org_data_rows (table_id, data) VALUES ($1, $2::jsonb)",
                                   [(tid, json.dumps(r, ensure_ascii=False)) for r in rows])
        did, _ = await make_board(pg, ["kpi", {"table": "productos", "chart_type": "kpi", "y": "count"}])
        out = await render_dashboard("o", did, {"period": {"preset": "last_month"}, "where": [{"key": "metodo_pago", "values": ["credito"]}]})
        prod = kpi(out, "Registros de Productos")
        assert prod["value"] == 30 and {n["code"] for n in prod["notes"]} == {"no_date", "no_dimension"}
        assert kpi(out, "Total vendido")["value"] == 2_564_100 and "notes" not in kpi(out, "Total vendido")

    async def test_opciones_de_filtro(self, pg, patched):
        await add_demo_ventas(pg)
        did, _ = await make_board(pg, ["kpi", "mes"])
        out = await options_service.filter_options("o", did)
        dims = {d["key"]: d for d in out["dimensions"]}
        rows = demo_rows()
        assert out["date"]["min"] == "2026-05-04" and out["date"]["max"] == "2026-10-16"
        pay = Counter(r["metodo_pago"] for r in rows)
        assert [(v["value"], v["count"]) for v in dims["metodo_pago"]["values"]] == pay.most_common()
        assert dims["producto"]["distinct"] == 51 and len(dims["producto"]["values"]) == 25 and dims["producto"]["more"] == 26
        assert dims["cliente"]["distinct"] == 18
        found = await options_service.filter_options("o", did, key="producto", q="pvc")
        assert sorted(v["value"] for v in found["dimensions"][0]["values"]) == sorted({r["producto"] for r in rows if "pvc" in r["producto"].lower()})

    async def test_sin_roles_se_comporta_igual_con_nombres_legibles(self, pg, patched):
        await add_demo_ventas(pg, roles=False)
        did, w = await make_board(pg, ["kpi", "mes", "pago"])
        out = await render_dashboard("o", did, {"where": [{"key": "metodo_pago", "values": ["credito"]}]})
        assert kpi(out, "Suma de total")["value"] == 18_022_900
        assert [c["title"] for c in out["charts"]] == ["Total por mes", "Total por método de pago"]
        drill = await drill_service.drill("o", did, w[("line_chart", "month(fecha)")], {"value": "2026-09"})
        assert drill["total"] == 6_687_300 and drill["by"]["by"] == "producto"
