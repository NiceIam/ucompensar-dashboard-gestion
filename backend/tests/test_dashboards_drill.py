"""Detalle al tocar un dato (drill-down) de un grafico del tablero — PI0320251.

BD emulada + oraculo en pandas como motor (sin red, sin IA). Valores esperados A MANO: salen del modulo `csv` de
Python sobre `brujula-demo/datos-expo/ventas.csv` (731 filas, ver la cabecera de cada prueba) y sobre
`test-data/ferreteria/ventas.csv` (40 filas), nunca del motor ni del servicio probado.

Valores de la demo (ventas.csv, 731 filas, total 44.527.400, 51 productos, 18 clientes + 211 filas sin cliente):
- 2026-07-27: 19 ventas, 1.004.000; 15 productos (Tuberia PVC 400.500, Pintura vinilo galon 156.600, Cemento 68.000);
  por cliente: Remodelaciones Acosta 465.000, Constructora Andes 362.300, Mostrador 66.000, (sin dato) 42.200 ...;
  por forma de pago: efectivo 574.200, credito 362.300, tarjeta 67.500
- 2026-09: 141 ventas, 6.687.300; 39 productos (los 20 primeros suman 5.843.000, el resto 844.300); 28 dias con ventas
- Cemento gris Argos 50kg: 22 ventas, 2.802.400; por mes 304.100 / 810.000 / 305.000 / 336.000 / 505.800 / 541.500
- por forma de pago: credito 18.022.900 (119), transferencia 13.233.500, efectivo 9.375.300, tarjeta 3.895.700
- por producto: 9 primeros suman 31.244.600 y los otros 42 productos 13.282.800
- sin cliente: 211 ventas, 5.869.200; Constructora Andes SAS 116 ventas, 19.819.100
"""

import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
from app.services import dashboard_builder_service as builder
from app.services import dashboard_drill_service as drill_service
from app.services import dashboard_filters as dfilters
from app.services.dashboard_drill_service import DrillError
from app.services.dashboard_render_service import render_dashboard
from tests.dash_support import FERRETERIA, ORG_A, ORG_B, catalog_of, env, gemini, load_ferreteria, read_csv, settings_stub  # noqa: F401

DEMO = Path(r"C:\ucompensar\brujula-demo\datos-expo\ventas.csv")
needs_demo = pytest.mark.skipif(not DEMO.exists(), reason="datos de la demo (brujula-demo/datos-expo) no disponibles")
TYPES = {"fecha": "date", "cantidad": "integer", "precio_unitario": "number", "total": "number"}
ROLES = {c: c for c in ("fecha", "producto", "cantidad", "precio_unitario", "total", "cliente", "metodo_pago")}
USER = "11111111-1111-1111-1111-111111111111"
TODAY = date(2026, 10, 19)


def demo_rows() -> list[dict]:
    with open(DEMO, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def csv_sum(rows, key, **where) -> dict:
    """{valor de `key`: suma de total} sobre las filas que cumplen `where` (calculado con csv, sin el motor)."""
    out: dict = defaultdict(int)
    for r in rows:
        if all(str(r[k]).startswith(v) if k == "fecha" else r[k] == v for k, v in where.items()):
            out[r[key] or None] += int(r["total"])
    return dict(out)


def load_demo(db, *, roles: bool = True):
    columns, rows = read_csv(DEMO, TYPES)
    return db.add_table("ventas", columns, rows, display_name="Ventas", column_types=TYPES,
                        sheet_kind="ventas" if roles else None, roles=ROLES if roles else None,
                        labels={"total": "Vr.Total", "fecha": "Fec"} if roles else None)


W = {
    "kpi": {"table": "ventas", "chart_type": "kpi", "y": "sum(total)"},
    "dia": {"table": "ventas", "chart_type": "line", "x": "day(fecha)", "y": "sum(total)"},
    "mes": {"table": "ventas", "chart_type": "line", "x": "month(fecha)", "y": "sum(total)"},
    "producto": {"table": "ventas", "chart_type": "bar", "x": "producto", "y": "sum(total)", "top": 5},
    "cliente": {"table": "ventas", "chart_type": "bar", "x": "cliente", "y": "sum(total)", "top": 20},
    "pago": {"table": "ventas", "chart_type": "pie", "x": "metodo_pago", "y": "sum(total)"},
    "torta_producto": {"table": "ventas", "chart_type": "pie", "x": "producto", "y": "sum(total)"},
}


async def make_board(env, names, title="Tablero de prueba", org=ORG_A):
    pool, catalog = await catalog_of(env, org)
    created, omitted = await builder.build_dashboard(pool, catalog, title, [W[n] for n in names])
    assert not omitted
    db = env.dbs.db(org)
    did = created["id"]
    widgets = {}
    for w in db.widgets:
        if str(w["dashboard_id"]) == did:
            x = w["data_source_query"].get("x") or "kpi"
            widgets[(w["widget_type"], x)] = str(w["id"])
    return did, widgets


def wid(widgets, kind, x):
    return widgets[(kind, x)]


@pytest.fixture(autouse=True)
def fixed_today():
    with patch("app.services.dashboard_filters.today_co", return_value=TODAY):
        yield


@pytest.fixture
def demo_board(env):
    load_demo(env.dbs.db(ORG_A))
    return env


# ---------------------------------------------------------------------------
# Tocar un dia / un mes (eje X de fecha con bucket)
# ---------------------------------------------------------------------------

@needs_demo
class TestDetalleDeUnDia:
    async def test_el_detalle_de_un_dia_es_por_producto_con_total_y_porcentajes(self, demo_board):
        did, w = await make_board(demo_board, ["dia"])
        out = await drill_service.drill(ORG_A, did, wid(w, "line_chart", "day(fecha)"), {"value": "2026-07-27"})

        assert out["title"] == "Ventas del 27 de julio de 2026"
        assert out["total"] == 1_004_000 and out["records"] == 19
        assert out["by"] == {"by": "producto", "label": "Producto", "kind": "category"}
        assert out["groups"] == 15 and out["shown"] == 15 and out["truncated"] is False and out["message"] is None
        assert out["measure"] == {"label": "Ventas", "fn": "sum", "unit": "money"}
        assert out["x"] == {"label": "Día", "bucket": "day"}
        rows = out["rows"]
        assert [(r["name"], r["value"]) for r in rows[:3]] == [
            ("Tubería PVC presión 1/2 x 6m", 400_500), ("Pintura vinilo blanco galón", 156_600),
            ("Cemento gris Argos 50kg", 68_000)]
        assert rows[0]["share"] == pytest.approx(400_500 / 1_004_000, abs=1e-4)
        assert sum(r["value"] for r in rows) == 1_004_000
        assert sum(r["share"] for r in rows) == pytest.approx(1.0, abs=2e-3)
        assert [r["value"] for r in rows] == sorted((r["value"] for r in rows), reverse=True)
        assert out["widget"]["id"] == wid(w, "line_chart", "day(fecha)")
        assert out["question"].startswith("Cuéntame más sobre «Ventas del 27 de julio de 2026»")

    async def test_ver_por_cliente_incluye_el_grupo_sin_dato(self, demo_board):
        did, w = await make_board(demo_board, ["dia"])
        out = await drill_service.drill(ORG_A, did, wid(w, "line_chart", "day(fecha)"),
                                        {"value": "2026-07-27", "by": "cliente"})
        assert out["by"]["label"] == "Cliente"
        assert [(r["name"], r["value"]) for r in out["rows"]] == [
            ("Remodelaciones Acosta e Hijos", 465_000), ("Constructora Andes SAS", 362_300),
            ("Mostrador", 66_000), ("(sin dato)", 42_200), ("Nelly Patricia Roa", 31_500),
            ("Luz Marina Cifuentes", 23_800), ("Conjunto Residencial Los Almendros", 13_200)]
        assert out["total"] == 1_004_000

    async def test_ver_por_forma_de_pago(self, demo_board):
        did, w = await make_board(demo_board, ["dia"])
        out = await drill_service.drill(ORG_A, did, wid(w, "line_chart", "day(fecha)"),
                                        {"value": "2026-07-27", "by": "metodo_pago"})
        assert out["by"]["label"] == "Forma de pago"
        assert [(r["name"], r["value"]) for r in out["rows"]] == [("efectivo", 574_200), ("credito", 362_300), ("tarjeta", 67_500)]

    async def test_las_dimensiones_alternativas_son_las_categoricas_utiles_y_no_la_fecha_del_eje(self, demo_board):
        did, w = await make_board(demo_board, ["dia"])
        out = await drill_service.drill(ORG_A, did, wid(w, "line_chart", "day(fecha)"), {"value": "2026-07-27"})
        assert [(d["by"], d["label"]) for d in out["dimensions"]] == [
            ("producto", "Producto"), ("cliente", "Cliente"), ("metodo_pago", "Forma de pago")]

    async def test_un_dia_sin_ventas_es_vacio_amable_no_un_error(self, demo_board):
        did, w = await make_board(demo_board, ["dia"])
        out = await drill_service.drill(ORG_A, did, wid(w, "line_chart", "day(fecha)"), {"value": "2026-12-25"})
        assert out["empty"] is True and out["rows"] == [] and out["records"] == 0 and out["total"] == 0

    async def test_el_titulo_de_la_semana(self, demo_board):
        did, w = await make_board(demo_board, ["dia"])
        # un widget semanal
        pool, catalog = await catalog_of(demo_board)
        created, _ = await builder.build_dashboard(pool, catalog, "Semanas", [
            {"table": "ventas", "chart_type": "line", "x": "week(fecha)", "y": "sum(total)"}])
        wk = next(str(x["id"]) for x in demo_board.dbs.db(ORG_A).widgets if str(x["dashboard_id"]) == created["id"])
        out = await drill_service.drill(ORG_A, created["id"], wk, {"value": "2026-07-27"})
        assert out["title"] == "Ventas de la semana del 27 de julio de 2026"
        assert out["total"] == 1_427_200 and out["records"] == 40          # 27-jul .. 2-ago


@needs_demo
class TestDetalleDeUnMes:
    async def test_un_mes_es_el_periodo_completo_y_avisa_el_truncamiento(self, demo_board):
        did, w = await make_board(demo_board, ["mes"])
        out = await drill_service.drill(ORG_A, did, wid(w, "line_chart", "month(fecha)"), {"value": "2026-09"})
        assert out["title"] == "Ventas de septiembre de 2026"
        assert out["total"] == 6_687_300 and out["records"] == 141
        assert out["by"]["by"] == "producto"
        assert out["groups"] == 39 and out["shown"] == 20 and out["truncated"] is True
        assert out["message"] == "Mostrando 20 de 39"
        assert sum(r["value"] for r in out["rows"]) == 5_843_000
        assert out["rest"] == {"groups": 19, "value": 844_300}
        assert out["rows"][0]["name"] == "Cable THW 12 AWG (metro)" and out["rows"][0]["value"] == 1_082_900
        assert out["rows"][0]["share"] == pytest.approx(1_082_900 / 6_687_300, abs=1e-4)

    async def test_el_mes_se_puede_ver_por_dia_en_orden_cronologico(self, demo_board):
        did, w = await make_board(demo_board, ["mes"])
        out = await drill_service.drill(ORG_A, did, wid(w, "line_chart", "month(fecha)"),
                                        {"value": "2026-09", "by": "day(fecha)"})
        expected = csv_sum(demo_rows(), "fecha", fecha="2026-09")
        assert out["by"] == {"by": "day(fecha)", "label": "Día", "kind": "period"}
        assert out["order"] == "period" and out["groups"] == 28 == len(expected)
        assert [(r["name"], r["value"]) for r in out["rows"]] == sorted(expected.items())
        assert out["truncated"] is False

    async def test_el_eje_de_mes_ofrece_el_dia_como_dimension_mas_fina(self, demo_board):
        did, w = await make_board(demo_board, ["mes"])
        out = await drill_service.drill(ORG_A, did, wid(w, "line_chart", "month(fecha)"), {"value": "2026-07"})
        assert [d["by"] for d in out["dimensions"]] == ["producto", "cliente", "metodo_pago", "day(fecha)"]
        assert out["total"] == 7_926_900 and out["records"] == 145

    async def test_un_ano_se_ve_por_mes(self, demo_board):
        pool, catalog = await catalog_of(demo_board)
        created, _ = await builder.build_dashboard(pool, catalog, "Anios", [
            {"table": "ventas", "chart_type": "bar", "x": "year(fecha)", "y": "sum(total)"}])
        wk = next(str(x["id"]) for x in demo_board.dbs.db(ORG_A).widgets if str(x["dashboard_id"]) == created["id"])
        out = await drill_service.drill(ORG_A, created["id"], wk, {"value": "2026", "by": "month(fecha)"})
        assert out["title"] == "Ventas de 2026" and out["total"] == 44_527_400 and out["records"] == 731
        assert [r["value"] for r in out["rows"]] == [8_555_300, 7_321_600, 7_926_900, 8_294_200, 6_687_300, 5_742_100]


# ---------------------------------------------------------------------------
# Tocar una categoria / una porcion
# ---------------------------------------------------------------------------

@needs_demo
class TestDetalleDeUnaCategoria:
    async def test_un_producto_se_ve_por_cliente_y_por_mes(self, demo_board):
        did, w = await make_board(demo_board, ["producto"])
        widget = wid(w, "bar_chart", "producto")
        out = await drill_service.drill(ORG_A, did, widget, {"value": "Cemento gris Argos 50kg"})
        assert out["title"] == "Ventas de Cemento gris Argos 50kg"
        assert out["total"] == 2_802_400 and out["records"] == 22
        assert out["by"]["by"] == "cliente"                 # categoria distinta del eje, mejor por rol
        assert [(r["name"], r["value"]) for r in out["rows"][:3]] == [
            ("Constructora Andes SAS", 2_083_200), ("Remodelaciones Acosta e Hijos", 170_000), ("Mostrador", 138_000)]
        assert [d["by"] for d in out["dimensions"]] == ["cliente", "metodo_pago", "month(fecha)"]
        assert all(d["by"] != "producto" for d in out["dimensions"])
        by_month = await drill_service.drill(ORG_A, did, widget, {"value": "Cemento gris Argos 50kg", "by": "month(fecha)"})
        assert [(r["name"], r["value"]) for r in by_month["rows"]] == [
            ("2026-05", 304_100), ("2026-06", 810_000), ("2026-07", 305_000), ("2026-08", 336_000),
            ("2026-09", 505_800), ("2026-10", 541_500)]

    async def test_el_valor_se_compara_sin_importar_mayusculas_ni_espacios(self, demo_board):
        did, w = await make_board(demo_board, ["producto"])
        out = await drill_service.drill(ORG_A, did, wid(w, "bar_chart", "producto"), {"value": "  CEMENTO GRIS argos 50KG "})
        assert out["total"] == 2_802_400

    async def test_una_forma_de_pago_de_la_torta(self, demo_board):
        did, w = await make_board(demo_board, ["pago"])
        out = await drill_service.drill(ORG_A, did, wid(w, "pie_chart", "metodo_pago"), {"value": "credito"})
        assert out["title"] == "Ventas (pagadas con credito)"
        assert out["total"] == 18_022_900 and out["records"] == 119
        assert out["by"]["by"] == "producto"

    async def test_el_grupo_sin_dato_de_un_grafico_se_abre_con_value_null(self, demo_board):
        did, w = await make_board(demo_board, ["cliente"])
        widget = wid(w, "bar_chart", "cliente")
        chart = next(c for c in (await render_dashboard(ORG_A, did))["charts"] if c["id"] == widget)
        sin = next(p for p in chart["data"] if p.get("empty"))
        assert sin["name"] == "(sin dato)" and sin["value"] == 5_869_200
        out = await drill_service.drill(ORG_A, did, widget, {"value": None})
        assert out["title"] == "Ventas sin cliente" and out["total"] == 5_869_200 and out["records"] == 211

    async def test_los_nombres_largos_del_grafico_traen_su_clave_exacta_para_abrir_el_detalle(self, demo_board):
        did, w = await make_board(demo_board, ["torta_producto"])
        widget = wid(w, "pie_chart", "producto")
        chart = next(c for c in (await render_dashboard(ORG_A, did))["charts"] if c["id"] == widget)
        long_ones = [p for p in chart["data"] if "key" in p]
        assert long_ones == [] or all(len(p["key"]) > 30 or p["key"] != p["name"] for p in long_ones)
        # un nombre de 36 caracteres: el grafico lo recorta a 30 y entrega la clave exacta
        pool, catalog = await catalog_of(demo_board)
        created, _ = await builder.build_dashboard(pool, catalog, "Todos", [
            {"table": "ventas", "chart_type": "bar", "x": "producto", "y": "sum(total)", "top": 20}])
        render = await render_dashboard(ORG_A, created["id"])
        bar = render["charts"][0]
        grif = next(p for p in bar["data"] if p["name"].startswith("Grifería lavamanos"))
        assert grif["key"] == "Grifería lavamanos monocontrol cromo" and len(grif["name"]) <= 31
        out = await drill_service.drill(ORG_A, created["id"], bar["id"], {"value": grif["key"]})
        assert out["total"] == grif["value"] == 6_472_000

    async def test_la_porcion_otros_lista_las_categorias_que_no_entraron(self, demo_board):
        did, w = await make_board(demo_board, ["torta_producto"])
        widget = wid(w, "pie_chart", "producto")
        chart = next(c for c in (await render_dashboard(ORG_A, did))["charts"] if c["id"] == widget)
        otros = chart["data"][-1]
        assert otros["name"] == "Otros (42)" and otros["other"] is True and otros["value"] == 13_282_800
        out = await drill_service.drill(ORG_A, did, widget, {"other": True})
        assert out["total"] == 13_282_800 and out["groups"] == 42 and out["shown"] == 42 and out["truncated"] is False
        assert out["title"] == "Ventas de los 42 productos restantes"
        assert sum(r["value"] for r in out["rows"]) == 13_282_800
        assert out["rows"][0]["value"] <= 1_036_500          # el 10.o producto, por debajo de los 9 visibles

    async def test_otros_solo_existe_en_las_tortas(self, demo_board):
        did, w = await make_board(demo_board, ["producto"])
        with pytest.raises(DrillError, match="pastel"):
            await drill_service.drill(ORG_A, did, wid(w, "bar_chart", "producto"), {"other": True})


# ---------------------------------------------------------------------------
# Filtros globales activos en el detalle
# ---------------------------------------------------------------------------

@needs_demo
class TestDetalleRespetaLosFiltros:
    async def test_el_periodo_cambia_el_total_del_detalle(self, demo_board):
        did, w = await make_board(demo_board, ["producto"])
        widget = wid(w, "bar_chart", "producto")
        out = await drill_service.drill(ORG_A, did, widget, {
            "value": "Cemento gris Argos 50kg", "filters": {"period": {"from": "2026-07-01", "to": "2026-07-31"}}})
        assert out["total"] == 305_000 and out["records"] == 4
        assert out["filters"]["period"]["from"] == "2026-07-01"

    async def test_el_periodo_y_una_categoria_se_combinan(self, demo_board):
        did, w = await make_board(demo_board, ["producto"])
        out = await drill_service.drill(ORG_A, did, wid(w, "bar_chart", "producto"), {
            "value": "Cemento gris Argos 50kg",
            "filters": {"period": {"from": "2026-07-01", "to": "2026-07-31"},
                        "where": [{"key": "cliente", "values": ["Constructora Andes SAS"]}]}})
        assert out["total"] == 168_000 and out["records"] == 1

    async def test_una_categoria_con_varios_valores(self, demo_board):
        did, w = await make_board(demo_board, ["mes"])
        out = await drill_service.drill(ORG_A, did, wid(w, "line_chart", "month(fecha)"), {
            "value": "2026-09", "filters": {"where": [{"key": "metodo_pago", "values": ["credito", "efectivo"]}]}})
        assert out["total"] == 4_598_600 and out["records"] == 79

    async def test_un_atajo_de_periodo_se_resuelve_con_la_fecha_de_hoy(self, demo_board):
        did, w = await make_board(demo_board, ["pago"])
        out = await drill_service.drill(ORG_A, did, wid(w, "pie_chart", "metodo_pago"), {
            "value": "credito", "filters": {"period": {"preset": "last_month"}}})
        # hoy = 2026-10-19 -> mes anterior = septiembre de 2026
        assert out["total"] == 2_564_100 and out["records"] == 19
        assert out["filters"]["period"] == {"preset": "last_month", "label": "Mes anterior",
                                           "from": "2026-09-01", "to": "2026-09-30"}


# ---------------------------------------------------------------------------
# Seguridad: valores y columnas hostiles, otra organizacion
# ---------------------------------------------------------------------------

@needs_demo
class TestSeguridad:
    @pytest.fixture
    async def board(self, demo_board):
        did, w = await make_board(demo_board, ["dia", "producto", "kpi", "torta_producto"])
        return did, w

    @pytest.mark.parametrize("value", [
        "'; DROP TABLE org_data_rows; --", "x' OR '1'='1", "\" OR 1=1 --", "%", "_", "\\", "0x41", "NULL",
        "Cemento%' UNION SELECT data FROM org_data_rows --", "<script>alert(1)</script>", "💥" * 40,
    ])
    async def test_un_valor_malicioso_es_un_dato_mas_no_se_ejecuta(self, board, demo_board, value):
        did, w = board
        out = await drill_service.drill(ORG_A, did, wid(w, "bar_chart", "producto"), {"value": value})
        assert out["records"] == 0 and out["rows"] == [] and out["empty"] is True
        assert len(demo_board.dbs.db(ORG_A).rows) == 731                  # nada se borro ni se leyo de mas

    @pytest.mark.parametrize("value", ["2026-13-01", "2026-02-30", "'; DROP", "2026-7-27", "", "x" * 300, "9999-01-01", "1800-01-01", 20260727, True, ["2026-07-27"], {"a": 1}])
    async def test_un_periodo_invalido_es_un_error_amable(self, board, value):
        did, w = board
        with pytest.raises(DrillError):
            await drill_service.drill(ORG_A, did, wid(w, "line_chart", "day(fecha)"), {"value": value})

    @pytest.mark.parametrize("by", [
        "no_existe", "'; DROP TABLE x; --", "month(precio_unitario)", "sum(total)", "fecha", "total", "cantidad",
        "producto", "day(fecha); --", "DAY(FECHA", "../etc/passwd", "ventas.cliente",
    ])
    async def test_by_fuera_de_la_lista_blanca_se_rechaza(self, board, by):
        did, w = board
        with pytest.raises(DrillError, match="No se puede ver el detalle"):
            await drill_service.drill(ORG_A, did, wid(w, "bar_chart", "producto"), {"value": "Cemento gris Argos 50kg", "by": by})

    async def test_los_filtros_con_columnas_inexistentes_o_fechas_invalidas_se_rechazan(self, board):
        did, w = board
        widget = wid(w, "bar_chart", "producto")
        bad = [
            {"where": [{"key": "no_existe", "values": ["x"]}]},
            {"where": [{"key": "total", "values": ["1"]}]},                       # numerica: no es una categoria
            {"where": [{"key": "cliente", "values": []}]},
            {"where": [{"key": "cliente", "values": [{"a": 1}]}]},
            {"where": [{"key": "cliente", "values": ["x" * 300]}]},
            {"where": [{"key": c, "values": ["x"]} for c in ("cliente", "metodo_pago", "producto", "fecha")]},
            {"period": {"from": "2026-13-45"}}, {"period": {"from": "ayer"}}, {"period": {"to": "2026-02-30"}},
            {"period": {"from": "2026-09-30", "to": "2026-09-01"}},
            {"period": {"preset": "siempre"}}, {"period": {"preset": "last_30", "from": "2026-09-01"}},
            {"period": {"from": "1800-01-01"}}, {"period": "hoy"}, {"otro": 1}, "texto", [1],
        ]
        for filters in bad:
            with pytest.raises((DrillError, dfilters.FilterError)):
                await drill_service.drill(ORG_A, did, widget, {"value": "Cemento gris Argos 50kg", "filters": filters})

    async def test_los_graficos_de_otro_tablero_o_inexistentes_dan_404(self, board):
        did, w = board
        for widget in ("00000000-0000-4000-8000-000000000000", "no-es-un-uuid", "1; DROP TABLE widgets", ""):
            with pytest.raises(HTTPException) as exc:
                await drill_service.drill(ORG_A, did, widget, {"value": "x"})
            assert exc.value.status_code == 404

    async def test_una_cifra_no_tiene_detalle(self, board):
        did, w = board
        with pytest.raises(DrillError, match="cifras"):
            await drill_service.drill(ORG_A, did, wid(w, "kpi_card", "kpi"), {"value": "x"})

    async def test_otra_organizacion_no_ve_el_tablero_ni_sus_datos(self, board, demo_board):
        did, w = board
        demo_board.dbs.db(ORG_B).add_table("ventas", ["producto", "total"], [{"producto": "Secreto", "total": 1}],
                                           column_types={"total": "number"})
        with pytest.raises(HTTPException) as exc:
            await drill_service.drill(ORG_B, did, wid(w, "bar_chart", "producto"), {"value": "Cemento gris Argos 50kg"})
        assert exc.value.status_code == 404

    async def test_sin_valor_y_sin_other_es_un_error(self, board):
        did, w = board
        with pytest.raises(DrillError, match="Falta el valor"):
            await drill_service.drill(ORG_A, did, wid(w, "bar_chart", "producto"), {})

    async def test_un_fallo_de_la_bd_no_filtra_texto_de_celdas(self, board, caplog):
        did, w = board

        async def boom(pool, plans):
            raise RuntimeError("detalle con dato privado: Constructora Andes")

        with patch("app.services.data_query_engine.run_plans", boom):
            with pytest.raises(DrillError) as exc:
                await drill_service.drill(ORG_A, did, wid(w, "bar_chart", "producto"), {"value": "x"})
        assert exc.value.status_code == 500 and "Andes" not in str(exc.value) and "Andes" not in caplog.text

    async def test_el_statement_timeout_es_un_504_amable(self, board):
        did, w = board

        class Canceled(Exception):
            sqlstate = "57014"

        async def slow(pool, plans):
            raise Canceled()

        with patch("app.services.data_query_engine.run_plans", slow):
            with pytest.raises(DrillError) as exc:
                await drill_service.drill(ORG_A, did, wid(w, "bar_chart", "producto"), {"value": "x"})
        assert exc.value.status_code == 504

    async def test_el_detalle_no_modifica_el_tablero_ni_su_huella(self, board, demo_board):
        did, w = board
        db = demo_board.dbs.db(ORG_A)
        before = json.dumps([x["data_source_query"] for x in db.widgets], sort_keys=True)
        await drill_service.drill(ORG_A, did, wid(w, "bar_chart", "producto"), {
            "value": "Cemento gris Argos 50kg", "filters": {"period": {"preset": "last_30"}}})
        await render_dashboard(ORG_A, did, {"period": {"preset": "last_30"}})
        assert json.dumps([x["data_source_query"] for x in db.widgets], sort_keys=True) == before


# ---------------------------------------------------------------------------
# Sin roles (heuristica por nombres), sin otra dimension, ferreteria
# ---------------------------------------------------------------------------

@needs_demo
class TestSinRoles:
    async def test_sin_roles_se_elige_el_detalle_por_nombre_y_los_titulos_son_legibles(self, env):
        load_demo(env.dbs.db(ORG_A), roles=False)
        did, w = await make_board(env, ["mes"])
        out = await drill_service.drill(ORG_A, did, wid(w, "line_chart", "month(fecha)"), {"value": "2026-09"})
        assert out["by"]["by"] == "producto" and out["total"] == 6_687_300
        assert out["title"] == "Total de septiembre de 2026"
        render = await render_dashboard(ORG_A, did)
        assert render["charts"][0]["title"] == "Total por mes"


class TestSemanaCompleta:
    async def test_la_semana_va_de_lunes_a_domingo_ambos_incluidos(self, env):
        """lunes 27-jul 10, domingo 2-ago 5, lunes 3-ago 7: la semana del 27 vale 15 (con el domingo) y la del 3, 7."""
        env.dbs.db(ORG_A).add_table("ventas", ["fecha", "producto", "total"], [
            {"fecha": "2026-07-27", "producto": "A", "total": 10}, {"fecha": "2026-08-02", "producto": "B", "total": 5},
            {"fecha": "2026-08-03", "producto": "A", "total": 7}], column_types={"fecha": "date", "total": "number"})
        did, w = await make_board_custom(env, [{"table": "ventas", "chart_type": "line", "x": "week(fecha)", "y": "sum(total)"}])
        widget = next(iter(w.values()))
        first = await drill_service.drill(ORG_A, did, widget, {"value": "2026-07-27"})
        assert (first["total"], first["records"]) == (15, 2) and [r["name"] for r in first["rows"]] == ["A", "B"]
        second = await drill_service.drill(ORG_A, did, widget, {"value": "2026-08-03"})
        assert (second["total"], second["records"]) == (7, 1)


class TestUnaSolaColumna:
    async def test_sin_otra_dimension_el_detalle_dice_que_no_hay_desglose(self, env):
        env.dbs.db(ORG_A).add_table("ventas", ["producto", "total"],
                                    [{"producto": "A", "total": 10}, {"producto": "B", "total": 5}, {"producto": "A", "total": 1}],
                                    column_types={"total": "number"})
        did, w = await make_board_custom(env, [{"table": "ventas", "chart_type": "bar", "x": "producto", "y": "sum(total)"}])
        out = await drill_service.drill(ORG_A, did, next(iter(w.values())), {"value": "A"})
        assert out["total"] == 11 and out["records"] == 2
        assert out["by"] is None and out["rows"] == [] and out["dimensions"] == []


async def make_board_custom(env, widgets, org=ORG_A):
    pool, catalog = await catalog_of(env, org)
    created, omitted = await builder.build_dashboard(pool, catalog, "Custom", widgets)
    assert not omitted
    db = env.dbs.db(org)
    return created["id"], {str(x["id"]): str(x["id"]) for x in db.widgets if str(x["dashboard_id"]) == created["id"]}


class TestFerreteria:
    """test-data/ferreteria/ventas.csv (40 filas): total 10.234.700; agosto 2025: 12 ventas, 3.174.500."""

    async def test_el_detalle_de_agosto_por_producto_cliente_y_forma_de_pago(self, env):
        db = env.dbs.db(ORG_A)
        columns, rows = read_csv(FERRETERIA / "ventas.csv", {"fecha": "date", "cantidad": "integer", "precio_unitario": "number", "total": "number"})
        db.add_table("ventas", columns, rows, display_name="Ventas",
                     column_types={"fecha": "date", "cantidad": "integer", "precio_unitario": "number", "total": "number"})
        did, w = await make_board_custom(env, [{"table": "ventas", "chart_type": "line", "x": "month(fecha)", "y": "sum(total)"}])
        widget = next(iter(w.values()))
        by_product = await drill_service.drill(ORG_A, did, widget, {"value": "2025-08"})
        assert by_product["total"] == 3_174_500 and by_product["records"] == 12 and by_product["groups"] == 12
        assert [(r["name"], r["value"]) for r in by_product["rows"][:4]] == [
            ("Cemento Argos 50kg", 577_500), ("Pintura vinilo blanco 5gal", 560_000),
            ("Pulidora Angular Makita 4 1/2", 550_000), ("Cable THW 12 AWG (metro)", 420_000)]
        assert by_product["title"] == "Total de agosto de 2025"
        by_pay = await drill_service.drill(ORG_A, did, widget, {"value": "2025-08", "by": "metodo_pago"})
        assert [(r["name"], r["value"]) for r in by_pay["rows"]] == [
            ("transferencia", 1_789_500), ("tarjeta", 1_024_000), ("efectivo", 361_000)]
        by_client = await drill_service.drill(ORG_A, did, widget, {"value": "2025-08", "by": "cliente"})
        assert [(r["name"], r["value"]) for r in by_client["rows"][:3]] == [
            ("Constructora Bolivar", 717_500), ("Taller Metalico SAS", 642_000), ("Pintores Asociados", 560_000)]
        assert by_client["groups"] == 10 and sum(r["value"] for r in by_client["rows"]) == 3_174_500


# ---------------------------------------------------------------------------
# HTTP: contrato, 404/422, limite de peticiones
# ---------------------------------------------------------------------------

@pytest.fixture
def login(app):
    def _login(org_id: str = ORG_A, role: str = "owner"):
        user = CurrentUser(user_id=USER, org_id=org_id, email="u@example.com", role=role)
        app.dependency_overrides[get_current_user] = lambda: user

    yield _login
    app.dependency_overrides.pop(get_current_user, None)


@needs_demo
class TestHttp:
    @pytest.fixture
    async def api(self, client: TestClient, login, demo_board):
        login()
        did, w = await make_board(demo_board, ["dia", "producto", "kpi"])
        return client, did, w

    async def test_contrato_del_drill(self, api):
        client, did, w = api
        r = client.post(f"/api/v1/dashboards/{did}/widgets/{wid(w, 'line_chart', 'day(fecha)')}/drill",
                        json={"value": "2026-07-27", "by": "cliente", "limit": 3})
        assert r.status_code == 200
        body = r.json()
        assert set(body) >= {"title", "widget", "x", "measure", "total", "records", "additive", "by", "dimensions",
                             "rows", "groups", "shown", "truncated", "message", "order", "notes", "empty", "question"}
        assert body["shown"] == 3 and body["truncated"] is True and body["message"] == "Mostrando 3 de 7"
        assert body["rest"] == {"groups": 4, "value": 1_004_000 - 465_000 - 362_300 - 66_000}
        assert body["rows"][0] == {"name": "Remodelaciones Acosta e Hijos", "value": 465000, "share": 0.4631}

    async def test_errores_http(self, api, login):
        client, did, w = api
        widget = wid(w, "bar_chart", "producto")
        url = f"/api/v1/dashboards/{did}/widgets/{widget}/drill"
        assert client.post(url, json={"value": "x", "by": "no_existe"}).status_code == 422
        assert client.post(url, json={"value": "x", "limit": 0}).status_code == 422
        assert client.post(url, json={"value": "x", "limit": 500}).status_code == 422
        assert client.post(url, json={"value": "x", "otra_cosa": 1}).status_code == 422          # extra=forbid
        assert client.post(url, json={"value": {"a": 1}}).status_code == 422
        assert client.post(url, json={"value": "x", "filters": {"period": {"from": "mañana"}}}).status_code == 422
        assert client.post(url, json={}).status_code == 422
        assert client.post(f"/api/v1/dashboards/{did}/widgets/{wid(w, 'kpi_card', 'kpi')}/drill", json={"value": "x"}).status_code == 422
        assert client.post(f"/api/v1/dashboards/{did}/widgets/00000000-0000-4000-8000-000000000000/drill", json={"value": "x"}).status_code == 404
        assert client.post(f"/api/v1/dashboards/00000000-0000-4000-8000-000000000000/widgets/{widget}/drill", json={"value": "x"}).status_code == 404
        login(ORG_B)
        assert client.post(url, json={"value": "x"}).status_code == 404

    async def test_sin_sesion_es_401(self, client, app):
        app.dependency_overrides.pop(get_current_user, None)
        r = client.post("/api/v1/dashboards/00000000-0000-4000-8000-000000000000/widgets/00000000-0000-4000-8000-000000000001/drill",
                        json={"value": "x"})
        assert r.status_code in (401, 403)

    async def test_el_limite_de_peticiones_responde_429_con_mensaje_en_lenguaje_llano(self, api):
        from app.auth import limiter

        client, did, w = api
        url = f"/api/v1/dashboards/{did}/widgets/{wid(w, 'bar_chart', 'producto')}/drill"
        limiter.reset()
        try:
            responses = [client.post(url, json={"value": "Cemento gris Argos 50kg"}) for _ in range(95)]
        finally:
            limiter.reset()
        codes = [r.status_code for r in responses]
        assert codes[:90] == [200] * 90 and set(codes[90:]) == {429}
        body = responses[-1].json()["detail"]
        assert body["code"] == "rate_limit_user" and "tableros muy seguido" in body["message"]
        assert int(responses[-1].headers["Retry-After"]) >= 1
