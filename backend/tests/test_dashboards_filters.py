"""Filtros globales del tablero (periodo + categorias) y sus opciones — PI0320251.

BD emulada + oraculo en pandas como motor. Valores esperados A MANO con el modulo `csv` de Python sobre
`brujula-demo/datos-expo/ventas.csv` (731 filas) y `test-data/ferreteria`:
- sin filtros: total 44.527.400 (731 ventas); credito 18.022.900 (119)
- septiembre de 2026: 6.687.300 (141): credito 2.564.100, efectivo 2.034.500, transferencia 1.204.900, tarjeta 883.800
- octubre de 2026 (hasta el 16): 5.742.100 (85)
- del 10 al 20 de julio de 2026: 2.672.300 (40); de esas, credito 1.738.700 (9)
- credito o efectivo: 27.398.200; en septiembre 4.598.600 (79)
"""

import csv
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
from app.services import dashboard_builder_service as builder
from app.services import dashboard_filter_options_service as options_service
from app.services import dashboard_filters as dfilters
from app.services.dashboard_drill_service import DrillError
from app.services.dashboard_render_service import render_dashboard
from tests.dash_support import FERRETERIA, ORG_A, ORG_B, catalog_of, env, gemini, load_ferreteria, read_csv, settings_stub  # noqa: F401
from tests.test_dashboards_drill import (  # noqa: F401
    DEMO, ROLES, TODAY, TYPES, W, USER, demo_rows, load_demo, login, make_board, make_board_custom, needs_demo,
)

REAL_TODAY_CO = dfilters.today_co          # antes del parche automatico de cada prueba
PRODUCTOS_TYPES = {"precio_compra": "number", "precio_venta": "number", "stock": "integer"}


@pytest.fixture(autouse=True)
def fixed_today():
    with patch("app.services.dashboard_filters.today_co", return_value=TODAY):
        yield


def between(rows, lo, hi, **where):
    """(suma de total, filas) de las ventas con lo <= fecha <= hi (ISO) y `col == valor`, calculado con csv."""
    picked = [r for r in rows if lo <= r["fecha"] <= hi and all(r[k] in (v if isinstance(v, tuple) else (v,)) for k, v in where.items())]
    return sum(int(r["total"]) for r in picked), len(picked)


def by_title(out):
    return {c["title"]: c for c in out["charts"]}


def kpi(out, label):
    return next(k for k in out["kpis"] if k["label"] == label)


@needs_demo
class TestPeriodo:
    async def test_sin_filtros_el_resultado_es_el_de_siempre_y_no_agrega_nada(self, env):
        load_demo(env.dbs.db(ORG_A))
        did, _ = await make_board(env, ["kpi", "mes", "pago"])
        out = await render_dashboard(ORG_A, did)
        assert "filters" not in out and "notes" not in out
        assert kpi(out, "Total vendido")["value"] == 44_527_400
        assert all("notes" not in c and "empty" not in c for c in out["charts"])
        assert out == await render_dashboard(ORG_A, did, {}) == await render_dashboard(ORG_A, did, None)

    async def test_un_rango_de_fechas_cambia_todas_las_cifras_y_graficos(self, env):
        load_demo(env.dbs.db(ORG_A))
        did, _ = await make_board(env, ["kpi", "mes", "pago"])
        out = await render_dashboard(ORG_A, did, {"period": {"from": "2026-07-10", "to": "2026-07-20"}})
        total, n = between(demo_rows(), "2026-07-10", "2026-07-20")
        assert (total, n) == (2_672_300, 40)
        assert kpi(out, "Total vendido")["value"] == 2_672_300
        charts = by_title(out)
        assert [(p["name"], p["value"]) for p in charts["Ventas por mes"]["data"]] == [("2026-07", 2_672_300)]
        pie = {p["name"]: p["value"] for p in charts["Ventas por forma de pago"]["data"]}
        assert sum(pie.values()) == 2_672_300 and pie["credito"] == 1_738_700
        assert out["filters"] == {"period": {"preset": None, "label": None, "from": "2026-07-10", "to": "2026-07-20"}}

    async def test_los_extremos_del_rango_son_inclusivos(self, env):
        load_demo(env.dbs.db(ORG_A))
        did, _ = await make_board(env, ["kpi"])
        day = await render_dashboard(ORG_A, did, {"period": {"from": "2026-07-27", "to": "2026-07-27"}})
        assert kpi(day, "Total vendido")["value"] == 1_004_000

    async def test_rango_abierto_solo_desde_o_solo_hasta(self, env):
        load_demo(env.dbs.db(ORG_A))
        did, _ = await make_board(env, ["kpi"])
        rows = demo_rows()
        after = await render_dashboard(ORG_A, did, {"period": {"from": "2026-10-01"}})
        assert kpi(after, "Total vendido")["value"] == between(rows, "2026-10-01", "9999")[0] == 5_742_100
        before = await render_dashboard(ORG_A, did, {"period": {"to": "2026-05-31"}})
        assert kpi(before, "Total vendido")["value"] == between(rows, "0000", "2026-05-31")[0] == 8_555_300

    @pytest.mark.parametrize("preset, lo, hi", [
        ("last_7", "2026-10-13", "2026-10-19"),
        ("last_30", "2026-09-20", "2026-10-19"),
        ("last_90", "2026-07-22", "2026-10-19"),
        ("this_month", "2026-10-01", "2026-10-31"),
        ("last_month", "2026-09-01", "2026-09-30"),
        ("this_year", "2026-01-01", "2026-12-31"),
    ])
    async def test_los_atajos_se_resuelven_con_la_fecha_de_hoy_en_colombia(self, env, preset, lo, hi):
        load_demo(env.dbs.db(ORG_A))
        did, _ = await make_board(env, ["kpi"])
        out = await render_dashboard(ORG_A, did, {"period": {"preset": preset}})
        assert out["filters"]["period"]["from"] == lo and out["filters"]["period"]["to"] == hi
        assert kpi(out, "Total vendido")["value"] == between(demo_rows(), lo, hi)[0]

    async def test_valores_conocidos_de_los_atajos(self, env):
        load_demo(env.dbs.db(ORG_A))
        did, _ = await make_board(env, ["kpi"])
        sept = await render_dashboard(ORG_A, did, {"period": {"preset": "last_month"}})
        octo = await render_dashboard(ORG_A, did, {"period": {"preset": "this_month"}})
        assert kpi(sept, "Total vendido")["value"] == 6_687_300 and kpi(octo, "Total vendido")["value"] == 5_742_100

    async def test_todo_es_lo_mismo_que_sin_filtro(self, env):
        load_demo(env.dbs.db(ORG_A))
        did, _ = await make_board(env, ["kpi"])
        out = await render_dashboard(ORG_A, did, {"period": {"preset": "all"}})
        assert kpi(out, "Total vendido")["value"] == 44_527_400 and "filters" not in out

    def test_el_hoy_de_colombia_es_utc_menos_5(self):
        from datetime import datetime, timezone

        class Fixed(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 10, 20, 3, 30, tzinfo=timezone.utc).astimezone(tz)

        with patch.object(dfilters, "datetime", Fixed):
            assert REAL_TODAY_CO() == date(2026, 10, 19)          # 03:30 UTC del 20 = 22:30 del 19 en Colombia


@needs_demo
class TestCategorias:
    async def test_una_forma_de_pago_cambia_los_totales(self, env):
        load_demo(env.dbs.db(ORG_A))
        did, _ = await make_board(env, ["kpi", "mes", "pago"])
        out = await render_dashboard(ORG_A, did, {"where": [{"key": "metodo_pago", "values": ["credito"]}]})
        assert kpi(out, "Total vendido")["value"] == 18_022_900
        pie = {p["name"]: p["value"] for p in by_title(out)["Ventas por forma de pago"]["data"]}
        assert pie == {"credito": 18_022_900}
        assert out["filters"]["where"] == [{"key": "metodo_pago", "values": ["credito"]}]

    async def test_varios_valores_de_una_categoria_se_suman(self, env):
        load_demo(env.dbs.db(ORG_A))
        did, _ = await make_board(env, ["kpi"])
        out = await render_dashboard(ORG_A, did, {"where": [{"key": "metodo_pago", "values": ["credito", "efectivo"]}]})
        assert kpi(out, "Total vendido")["value"] == 27_398_200

    async def test_periodo_y_dos_categorias_se_combinan(self, env):
        load_demo(env.dbs.db(ORG_A))
        did, _ = await make_board(env, ["kpi", "pago"])
        out = await render_dashboard(ORG_A, did, {
            "period": {"from": "2026-09-01", "to": "2026-09-30"},
            "where": [{"key": "metodo_pago", "values": ["credito", "efectivo"]}]})
        assert kpi(out, "Total vendido")["value"] == 4_598_600
        pie = {p["name"]: p["value"] for p in by_title(out)["Ventas por forma de pago"]["data"]}
        assert pie == {"credito": 2_564_100, "efectivo": 2_034_500}
        both = await render_dashboard(ORG_A, did, {
            "where": [{"key": "metodo_pago", "values": ["credito"]}, {"key": "cliente", "values": ["Constructora Andes SAS"]}]})
        rows = demo_rows()
        expected = sum(int(r["total"]) for r in rows if r["metodo_pago"] == "credito" and r["cliente"] == "Constructora Andes SAS")
        assert kpi(both, "Total vendido")["value"] == expected > 0

    async def test_las_mayusculas_y_espacios_del_valor_no_importan(self, env):
        load_demo(env.dbs.db(ORG_A))
        did, _ = await make_board(env, ["kpi"])
        out = await render_dashboard(ORG_A, did, {"where": [{"key": "metodo_pago", "values": ["  CREDITO "]}]})
        assert kpi(out, "Total vendido")["value"] == 18_022_900

    async def test_la_clave_acepta_el_nombre_de_la_columna_sin_roles(self, env):
        load_demo(env.dbs.db(ORG_A), roles=False)
        did, _ = await make_board(env, ["kpi"])
        out = await render_dashboard(ORG_A, did, {"where": [{"key": "Metodo_Pago", "values": ["credito"]}]})
        assert kpi(out, "Suma de total")["value"] == 18_022_900

    async def test_los_filtros_se_suman_a_los_propios_del_widget_sin_pisarlos(self, env):
        load_demo(env.dbs.db(ORG_A))
        pool, catalog = await catalog_of(env)
        created, _ = await builder.build_dashboard(pool, catalog, "Solo efectivo", [
            {"table": "ventas", "chart_type": "kpi", "y": "sum(total)", "filters": [["metodo_pago", "=", "efectivo"]]},
            {"table": "ventas", "chart_type": "kpi", "y": "count"},
        ])
        solo = await render_dashboard(ORG_A, created["id"], {"period": {"from": "2026-09-01", "to": "2026-09-30"}})
        assert kpi(solo, "Total vendido")["value"] == 2_034_500                      # efectivo de septiembre
        assert kpi(solo, "Registros de Ventas")["value"] == 141
        contradict = await render_dashboard(ORG_A, created["id"], {"where": [{"key": "metodo_pago", "values": ["credito"]}]})
        zero = kpi(contradict, "Total vendido")
        assert zero["value"] == 0 and zero["empty"] is True and "error" not in zero

    async def test_sin_filas_el_grafico_es_vacio_con_su_titulo_no_un_error(self, env):
        load_demo(env.dbs.db(ORG_A))
        did, _ = await make_board(env, ["kpi", "mes", "producto"])
        out = await render_dashboard(ORG_A, did, {"period": {"from": "2027-01-01", "to": "2027-01-31"}})
        assert kpi(out, "Total vendido")["value"] == 0
        for chart in out["charts"]:
            assert chart["data"] == [] and chart["empty"] is True and chart["message"] == "Sin datos con estos filtros."
            assert "error" not in chart and chart["title"] and chart["drillable"] is True
        assert [c["title"] for c in out["charts"]] == ["Ventas por mes", "Ventas por producto"]

    async def test_el_promedio_sin_filas_queda_vacio_sin_inventar_un_cero(self, env):
        load_demo(env.dbs.db(ORG_A))
        pool, catalog = await catalog_of(env)
        created, _ = await builder.build_dashboard(pool, catalog, "Prom", [
            {"table": "ventas", "chart_type": "kpi", "y": "avg(total)"}])
        out = await render_dashboard(ORG_A, created["id"], {"period": {"from": "2027-01-01", "to": "2027-01-31"}})
        assert out["kpis"][0]["value"] is None and out["kpis"][0]["empty"] is True and out["kpis"][0]["label"] == "Venta promedio"


class TestHojasSinLaColumna:
    """Un widget cuya hoja no tiene la fecha o la categoria NO se rompe: se calcula sin ese filtro y se avisa."""

    async def board(self, env):
        db = env.dbs.db(ORG_A)
        load_ferreteria(db)
        return await make_board_custom(env, [
            {"table": "ventas", "chart_type": "kpi", "y": "sum(total)"},
            {"table": "productos", "chart_type": "kpi", "y": "count"},
            {"table": "productos", "chart_type": "bar", "x": "categoria", "y": "sum(stock)"},
        ])

    async def test_una_hoja_sin_fecha_se_calcula_completa_y_avisa(self, env):
        did, _ = await self.board(env)
        out = await render_dashboard(ORG_A, did, {"period": {"from": "2025-08-01", "to": "2025-08-31"}})
        assert kpi(out, "Suma de total")["value"] == 3_174_500        # ventas de agosto de 2025
        productos = kpi(out, "Registros de Productos")
        assert productos["value"] == 30 and productos["notes"][0]["code"] == "no_date"
        assert "no tiene fecha" in productos["notes"][0]["message"]
        bar = out["charts"][0]
        assert sum(p["value"] for p in bar["data"]) == 2_985 and bar["notes"][0]["code"] == "no_date"
        assert "notes" not in kpi(out, "Suma de total")

    async def test_una_categoria_que_la_hoja_no_tiene_se_ignora_con_aviso(self, env):
        did, _ = await self.board(env)
        out = await render_dashboard(ORG_A, did, {"where": [{"key": "metodo_pago", "values": ["tarjeta"]}]})
        assert kpi(out, "Suma de total")["value"] == 3_109_000        # tarjeta
        productos = kpi(out, "Registros de Productos")
        assert productos["value"] == 30 and productos["notes"] == [
            {"code": "no_dimension", "message": "Este gráfico no tiene «Metodo pago»: se muestra sin ese filtro."}]

    async def test_una_categoria_que_no_existe_en_ninguna_hoja_es_un_error_de_validacion(self, env):
        did, _ = await self.board(env)
        with pytest.raises(dfilters.FilterError, match="No puedo filtrar por «inventada»"):
            await render_dashboard(ORG_A, did, {"where": [{"key": "inventada", "values": ["x"]}]})

    async def test_la_clave_de_una_columna_numerica_no_es_filtrable(self, env):
        did, _ = await self.board(env)
        with pytest.raises(dfilters.FilterError):
            await render_dashboard(ORG_A, did, {"where": [{"key": "total", "values": ["1"]}]})

    async def test_tablero_antiguo_sin_especificaciones_con_filtros_no_muestra_cifras_que_no_cambian(self, env):
        db = env.dbs.db(ORG_A)
        load_ferreteria(db)
        did = db.add_dashboard("antiguo")
        plain = await render_dashboard(ORG_A, str(did))
        assert plain["legacy"] is True and plain["kpis"][0]["label"] == "Registros totales"
        out = await render_dashboard(ORG_A, str(did), {"period": {"from": "2025-08-01", "to": "2025-08-31"}})
        assert out["legacy"] is True and out["kpis"] == [] and out["notes"][0]["code"] == "legacy_filters"
        assert out["charts"] and all("drillable" not in c for c in out["charts"])         # sin id de widget no hay detalle
        month = next(c for c in out["charts"] if c["title"] == "Total por mes")
        assert [(p["name"], p["value"]) for p in month["data"]] == [("2025-08", 3_174_500)]


class TestValidacion:
    @pytest.mark.parametrize("raw", [
        {"period": {"from": "2026-02-30"}}, {"period": {"from": "ayer"}}, {"period": {"to": 5}},
        {"period": {"preset": "nunca"}}, {"period": {"preset": "all", "to": "2026-01-01"}},
        {"period": {"from": "2026-09-30", "to": "2026-09-01"}}, {"period": {"from": "0001-01-01"}},
        {"period": {"desde": "2026-01-01"}}, {"period": []}, {"period": "hoy"},
        {"where": "producto"}, {"where": [{"key": "a"}]}, {"where": [{"values": ["a"]}]},
        {"where": [{"key": "a", "values": "x"}]}, {"where": [{"key": "a", "values": [True]}]},
        {"where": [{"key": "a", "values": [["x"]]}]}, {"where": [{"key": "a", "values": ["x"], "op": "="}]},
        {"where": [{"key": "a", "values": ["x"] * 26}]},
        {"where": [{"key": "a'; DROP", "values": ["x"]}]}, {"where": [{"key": "a" * 80, "values": ["x"]}]},
        {"where": [{"key": "a", "values": ["x"]}, {"key": "A", "values": ["y"]}]},
        {"where": [{"key": k, "values": ["x"]} for k in "abcd"]},
        {"where": [{"key": "a", "values": [chr(0)]}]}, {"where": [{"key": "a", "values": ["   "]}]},
        {"extra": 1}, "texto", 7, [1],
    ])
    def test_cada_filtro_invalido_es_un_error_en_lenguaje_llano(self, raw):
        with pytest.raises(dfilters.FilterError) as error:
            dfilters.parse_filters(raw, TODAY)
        assert str(error.value) and "Traceback" not in str(error.value)

    def test_formas_validas(self):
        gf = dfilters.parse_filters({"period": {"preset": "last_30"},
                                     "where": [{"key": "Metodo Pago", "values": ["a", "a", " b ", 3]}]}, TODAY)
        assert (gf.date_from, gf.date_to, gf.preset) == (date(2026, 9, 20), TODAY, "last_30")
        assert gf.where == (("metodo_pago", ("a", "b", "3")),)          # sin repetidos, recortados, texto
        assert dfilters.parse_filters(None, TODAY) is dfilters.NO_FILTERS and not dfilters.parse_filters({}, TODAY).active

    @pytest.mark.parametrize("today, preset, lo, hi", [
        (date(2026, 1, 15), "last_month", date(2025, 12, 1), date(2025, 12, 31)),
        (date(2026, 3, 31), "last_month", date(2026, 2, 1), date(2026, 2, 28)),
        (date(2024, 3, 31), "last_month", date(2024, 2, 1), date(2024, 2, 29)),
        (date(2026, 12, 31), "this_month", date(2026, 12, 1), date(2026, 12, 31)),
        (date(2026, 2, 10), "this_month", date(2026, 2, 1), date(2026, 2, 28)),
        (date(2026, 1, 1), "last_7", date(2025, 12, 26), date(2026, 1, 1)),
        (date(2026, 6, 5), "this_year", date(2026, 1, 1), date(2026, 12, 31)),
    ])
    def test_atajos_en_los_bordes_del_calendario(self, today, preset, lo, hi):
        assert dfilters.resolve_preset(preset, today) == (lo, hi)


@needs_demo
class TestOpciones:
    async def test_categorias_con_sus_valores_mas_frecuentes_y_el_rango_de_fechas(self, env):
        load_demo(env.dbs.db(ORG_A))
        did, _ = await make_board(env, ["kpi", "mes"])
        out = await options_service.filter_options(ORG_A, did)
        rows = demo_rows()
        assert out["today"] == "2026-10-19"
        assert [p["id"] for p in out["presets"]] == ["last_7", "last_30", "last_90", "this_month", "last_month", "this_year", "all"]
        assert out["date"] == {"column": "fecha", "label": "Fecha de la venta", "min": "2026-05-04", "max": "2026-10-16",
                               "tables": ["ventas"]}
        dims = {d["key"]: d for d in out["dimensions"]}
        assert list(dims) == ["producto", "cliente", "metodo_pago"]
        assert dims["metodo_pago"]["label"] == "Forma de pago" and dims["metodo_pago"]["distinct"] == 4
        from collections import Counter

        pay = Counter(r["metodo_pago"] for r in rows)
        assert [(v["value"], v["count"]) for v in dims["metodo_pago"]["values"]] == pay.most_common()
        prod = Counter(r["producto"] for r in rows)
        assert dims["producto"]["distinct"] == 51 == len(prod)
        assert len(dims["producto"]["values"]) == 25 and dims["producto"]["more"] == 26
        assert [v["count"] for v in dims["producto"]["values"]] == sorted((c for _, c in prod.most_common(25)), reverse=True)
        cli = Counter(r["cliente"] for r in rows if r["cliente"])
        assert dims["cliente"]["distinct"] == 18 == len(cli) and dims["cliente"]["more"] == 0
        assert (dims["cliente"]["values"][0]["value"], dims["cliente"]["values"][0]["count"]) == cli.most_common(1)[0]

    async def test_la_busqueda_encuentra_valores_fuera_de_los_25_primeros(self, env):
        load_demo(env.dbs.db(ORG_A))
        did, _ = await make_board(env, ["kpi"])
        out = await options_service.filter_options(ORG_A, did, key="producto", q="  PVC")
        (dim,) = out["dimensions"]
        expected = sorted({r["producto"] for r in demo_rows() if "pvc" in r["producto"].lower()})
        assert dim["key"] == "producto" and sorted(v["value"] for v in dim["values"]) == expected and len(expected) >= 2
        assert out["date"] is None                                        # una busqueda no recalcula las fechas
        assert (await options_service.filter_options(ORG_A, did, key="producto", q="zzzz"))["dimensions"][0]["values"] == []

    async def test_busquedas_hostiles_y_claves_que_no_existen(self, env):
        load_demo(env.dbs.db(ORG_A))
        did, _ = await make_board(env, ["kpi"])
        for q in ("%", "_", "'; DROP TABLE x; --", "\\", "💥" * 100):
            out = await options_service.filter_options(ORG_A, did, key="producto", q=q)
            assert out["dimensions"][0]["values"] == []         # % y _ se buscan como texto literal
        assert len(demo_rows()) == len(env.dbs.db(ORG_A).rows)
        for key in ("total", "no_existe", "'; DROP"):
            with pytest.raises(DrillError):
                await options_service.filter_options(ORG_A, did, key=key)

    async def test_una_hoja_sin_categorias_ni_fecha_no_ofrece_nada(self, env):
        env.dbs.db(ORG_A).add_table("t", ["a", "b"], [{"a": 1, "b": 2}], column_types={"a": "number", "b": "number"})
        did, _ = await make_board_custom(env, [{"table": "t", "chart_type": "kpi", "y": "sum(a)"}])
        out = await options_service.filter_options(ORG_A, did)
        assert out["dimensions"] == [] and out["date"] is None

    async def test_con_dos_hojas_la_misma_categoria_se_une(self, env):
        db = env.dbs.db(ORG_A)
        db.add_table("ventas", ["fecha", "cliente", "total"],
                     [{"fecha": "2026-01-05", "cliente": "Ana", "total": 10}, {"fecha": "2026-02-05", "cliente": "Luis", "total": 5}],
                     column_types={"fecha": "date", "total": "number"}, sheet_kind="ventas",
                     roles={"fecha": "fecha", "cliente": "cliente", "total": "total"})
        db.add_table("fiados", ["desde", "cliente", "cuanto_debe"],
                     [{"desde": "2026-03-01", "cliente": "ana", "cuanto_debe": 7}, {"desde": "2026-04-01", "cliente": "Zoe", "cuanto_debe": 9}],
                     column_types={"desde": "date", "cuanto_debe": "number"}, sheet_kind="cuentas_por_cobrar",
                     roles={"desde": "fecha_emision", "cliente": "cliente", "cuanto_debe": "valor"})
        did, _ = await make_board_custom(env, [
            {"table": "ventas", "chart_type": "kpi", "y": "sum(total)"},
            {"table": "fiados", "chart_type": "kpi", "y": "sum(cuanto_debe)"}])
        out = await options_service.filter_options(ORG_A, did)
        (dim,) = out["dimensions"]
        assert dim["key"] == "cliente" and sorted(dim["tables"]) == ["fiados", "ventas"]
        assert {v["value"].lower(): v["count"] for v in dim["values"]} == {"ana": 2, "luis": 1, "zoe": 1}      # Ana y ana: una sola
        assert out["date"]["min"] == "2026-01-05" and out["date"]["max"] == "2026-04-01"
        # y un filtro por esa categoria llega a las dos hojas
        filtered = await render_dashboard(ORG_A, did, {"where": [{"key": "cliente", "values": ["Ana"]}]})
        assert {k["label"]: k["value"] for k in filtered["kpis"]} == {"Total vendido": 10, "Total que te deben": 7}


# ---------------------------------------------------------------------------
# Cartera: unidad monetaria por rol (defecto visto en la prueba real) y nombres legibles de punta a punta
# ---------------------------------------------------------------------------

class TestCarteraYNombres:
    FIADOS = [
        {"quien": "Doris", "cuanto_debe": 1_250_000, "desde": "2026-07-03"},
        {"quien": "Hernan", "cuanto_debe": 1_250_000, "desde": "2026-08-10"},
        {"quien": "Luz", "cuanto_debe": 3_100_000, "desde": "2026-09-01"},
    ]

    async def test_el_kpi_de_cartera_sin_rol_ni_palabra_de_dinero_en_el_nombre_sale_en_pesos(self, env):
        env.dbs.db(ORG_A).add_table("fiados", ["quien", "cuanto_debe", "desde"], self.FIADOS, display_name="Fiados",
                                    column_types={"cuanto_debe": "number", "desde": "date"})
        did, _ = await make_board_custom(env, [{"table": "fiados", "chart_type": "kpi", "y": "sum(cuanto_debe)"}])
        out = await render_dashboard(ORG_A, did)
        (k,) = out["kpis"]
        assert (k["value"], k["unit"], k["icon"], k["label"]) == (5_600_000, "money", "DollarSign", "Suma de cuánto debe")

    async def test_con_rol_la_unidad_es_pesos_aunque_el_nombre_sea_raro_y_los_titulos_hablan_del_negocio(self, env):
        env.dbs.db(ORG_A).add_table(
            "fiados", ["quien", "xq", "desde"],
            [{"quien": r["quien"], "xq": r["cuanto_debe"], "desde": r["desde"]} for r in self.FIADOS], display_name="Fiados",
            column_types={"xq": "number", "desde": "date"}, sheet_kind="cuentas_por_cobrar",
            roles={"quien": "cliente", "xq": "valor", "desde": "fecha_emision"}, labels={"xq": "¿Cuánto debe?", "desde": "Desde"})
        did, _ = await make_board_custom(env, [
            {"table": "fiados", "chart_type": "kpi", "y": "sum(xq)"},
            {"table": "fiados", "chart_type": "line", "x": "month(desde)", "y": "sum(xq)"},
            {"table": "fiados", "chart_type": "bar", "x": "quien", "y": "sum(xq)"}])
        out = await render_dashboard(ORG_A, did)
        (k,) = out["kpis"]
        assert (k["label"], k["unit"], k["value"]) == ("Total que te deben", "money", 5_600_000)
        assert [(c["title"], c["unit"], c["x_label"], c["y_label"]) for c in out["charts"]] == [
            ("Cartera por cobrar por mes", "money", "Mes", "Cartera por cobrar"),
            ("Cartera por cobrar por cliente", "money", "Cliente", "Cartera por cobrar")]
        assert all("xq" not in c["title"] and "desde" not in c["title"] for c in out["charts"])

    async def test_los_titulos_nuevos_no_cambian_la_huella_de_idempotencia(self, env):
        from app.services import chart_specs as cs

        env.dbs.db(ORG_A).add_table("fiados", ["quien", "xq"], [{"quien": "A", "xq": 1}], display_name="Fiados",
                                    column_types={"xq": "number"}, sheet_kind="cuentas_por_cobrar",
                                    roles={"quien": "cliente", "xq": "valor"}, labels={"xq": "¿Cuánto debe?"})
        pool, catalog = await catalog_of(env)
        widgets = [{"table": "fiados", "chart_type": "bar", "x": "quien", "y": "sum(xq)"}]
        first, _ = await builder.build_dashboard(pool, catalog, "Cartera", widgets)
        again, _ = await builder.build_dashboard(pool, catalog, "Otro titulo", widgets)
        assert again["existing"] is True and again["id"] == first["id"]                 # misma huella: no duplica
        stored = next(w for w in env.dbs.db(ORG_A).widgets)["data_source_query"]
        assert stored["x"] == "quien" and stored["y"] == "sum(xq)" and stored["table"] == "fiados"   # nombres canonicos
        spec = cs.parse_spec(catalog, widgets[0])
        assert stored["fp"] == cs.fingerprint([spec])
        assert "Cartera" not in json.dumps(spec.canonical()) and "Cuánto" not in json.dumps(spec.canonical())


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

@needs_demo
class TestHttp:
    @pytest.fixture
    async def api(self, client: TestClient, login, env):
        login()
        load_demo(env.dbs.db(ORG_A))
        did, w = await make_board(env, ["kpi", "mes"])
        return client, did

    async def test_execute_acepta_sin_cuerpo_con_cuerpo_vacio_y_con_filtros(self, api):
        client, did = api
        plain = client.post(f"/api/v1/dashboards/{did}/execute").json()
        assert client.post(f"/api/v1/dashboards/{did}/execute", json={}).json() == plain
        filtered = client.post(f"/api/v1/dashboards/{did}/execute", json={"filters": {"period": {"preset": "last_month"}}}).json()
        assert next(k for k in plain["kpis"])["value"] == 44_527_400
        assert next(k for k in filtered["kpis"])["value"] == 6_687_300
        assert filtered["filters"]["period"]["label"] == "Mes anterior"

    async def test_filtros_invalidos_son_422_con_mensaje(self, api):
        client, did = api
        for filters in ({"period": {"from": "2026-13-01"}}, {"where": [{"key": "inventada", "values": ["x"]}]}, {"x": 1}):
            r = client.post(f"/api/v1/dashboards/{did}/execute", json={"filters": filters})
            assert r.status_code == 422 and isinstance(r.json()["detail"], str) and r.json()["detail"]

    async def test_filter_options_http(self, api, login):
        client, did = api
        body = client.get(f"/api/v1/dashboards/{did}/filter-options").json()
        assert [d["key"] for d in body["dimensions"]] == ["producto", "cliente", "metodo_pago"] and body["date"]["min"] == "2026-05-04"
        found = client.get(f"/api/v1/dashboards/{did}/filter-options", params={"key": "cliente", "q": "andes"}).json()
        assert [v["value"] for v in found["dimensions"][0]["values"]] == ["Constructora Andes SAS"]
        assert client.get(f"/api/v1/dashboards/{did}/filter-options", params={"key": "total"}).status_code == 422
        assert client.get(f"/api/v1/dashboards/{did}/filter-options", params={"q": "x" * 200}).status_code == 422
        assert client.get("/api/v1/dashboards/00000000-0000-4000-8000-000000000000/filter-options").status_code == 404
        login(ORG_B)
        assert client.get(f"/api/v1/dashboards/{did}/filter-options").status_code == 404

    async def test_otra_organizacion_no_puede_calcular_con_filtros(self, api, login):
        client, did = api
        login(ORG_B)
        assert client.post(f"/api/v1/dashboards/{did}/execute", json={"filters": {"period": {"preset": "all"}}}).status_code == 404
