"""Calculo del tablero al abrirlo (render_dashboard, `POST /dashboards/{id}/execute`) — PI0320251.

Valores esperados A MANO (modulo csv de Python sobre test-data/ferreteria, sin el motor):
- ventas (40 filas): total 10.234.700; transferencia 4.941.700, tarjeta 3.109.000, efectivo 2.184.000;
  2025-07 3.315.500, 2025-08 3.174.500, 2025-09 2.994.700, 2025-10 750.000; cantidad total 460;
  top productos: Cemento Argos 50kg 2.194.500, Pintura vinilo blanco 5gal 1.344.000, Varilla corrugada 1/2 x 6m
  1.320.000 (orden por valor), Taladro Percutor Bosch 13mm 778.000, Cable THW 12 AWG (metro) 630.000
- productos (30 filas): precio_venta promedio 73.006,67; stock total 2.985; 13 categorias
- tabla sintetica de 731 filas: total = (i % 9 + 1) * 1000 -> suma 3.648.000 (las primeras 500 sumarian 2.490.000)
"""

import asyncio
import json
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services.dashboard_render_service import render_dashboard
from app.services.dashboard_service import list_dashboards
from tests.dash_support import ORG_A, catalog_of, env, gemini, load_ferreteria, settings_stub, read_csv  # noqa: F401
from app.services import dashboard_builder_service as builder
from app.services import chart_specs as cs

DEMO = Path(r"C:\ucompensar\brujula-demo\datos-expo\ventas.csv")


def spec(**kw):
    return cs.parse_spec(kw.pop("_catalog"), kw)


async def make(env, widgets, title="T", org=ORG_A):
    pool, catalog = await catalog_of(env, org)
    created, omitted = await builder.build_dashboard(pool, catalog, title, widgets)
    return created["id"], omitted


VENTAS = [
    {"table": "ventas", "chart_type": "kpi", "y": "sum(total)"},
    {"table": "ventas", "chart_type": "line", "x": "month(fecha)", "y": "sum(total)"},
    {"table": "ventas", "chart_type": "bar", "x": "producto", "y": "sum(total)", "top": 5},
    {"table": "ventas", "chart_type": "pie", "x": "metodo_pago", "y": "sum(total)"},
]


class TestValoresExactos:
    async def test_un_tablero_creado_se_calcula_con_los_valores_correctos_y_la_unidad(self, env):
        db = env.dbs.db(ORG_A)
        load_ferreteria(db)
        did, _ = await make(env, VENTAS)

        out = await render_dashboard(ORG_A, did)

        assert out["legacy"] is False
        (kpi,) = out["kpis"]
        assert (kpi["label"], kpi["value"], kpi["unit"], kpi["icon"], kpi["column"]) == (
            "Suma de total", 10_234_700, "money", "DollarSign", "total")
        line, bar, pie = out["charts"]
        assert line["type"] == "line" and line["unit"] == "money"
        assert [(p["name"], p["value"]) for p in line["data"]] == [
            ("2025-07", 3_315_500), ("2025-08", 3_174_500), ("2025-09", 2_994_700), ("2025-10", 750_000)]
        assert [(p["name"], p["value"]) for p in bar["data"]] == [
            ("Cemento Argos 50kg", 2_194_500), ("Pintura vinilo blanco 5gal", 1_344_000),
            ("Varilla corrugada 1/2 x 6m", 1_320_000), ("Taladro Percutor Bosch 13mm", 778_000),
            ("Cable THW 12 AWG (metro)", 630_000)]
        assert {p["name"]: p["value"] for p in pie["data"]} == {
            "transferencia": 4_941_700, "tarjeta": 3_109_000, "efectivo": 2_184_000}
        assert all(c["x"] == "name" and c["y"] == "value" and not c.get("error") for c in out["charts"])

    async def test_la_unidad_de_cada_cifra(self, env):
        load_ferreteria(env.dbs.db(ORG_A))
        did, _ = await make(env, [
            {"table": "ventas", "chart_type": "kpi", "y": "count"},
            {"table": "ventas", "chart_type": "kpi", "y": "sum(cantidad)"},
            {"table": "productos", "chart_type": "kpi", "y": "avg(precio_venta)"},
            {"table": "productos", "chart_type": "kpi", "y": "sum(stock)"},
            {"table": "ventas", "chart_type": "kpi", "y": "count_distinct(cliente)"},
        ])
        out = await render_dashboard(ORG_A, did)
        got = {(k["label"], k["unit"], k["value"]) for k in out["kpis"]}
        assert got == {
            ("Registros de Ventas", "count", 40),
            ("Suma de cantidad", "number", 460),
            ("Promedio de precio_venta", "money", 73006.67),
            ("Suma de stock", "number", 2985),
            ("Distintos de cliente", "count", 22),
        }

    async def test_el_tablero_NO_es_una_foto_si_llegan_mas_datos_cambia(self, env):
        db = env.dbs.db(ORG_A)
        ventas, _ = load_ferreteria(db)
        did, _ = await make(env, [VENTAS[0]])
        assert (await render_dashboard(ORG_A, did))["kpis"][0]["value"] == 10_234_700
        db.rows.append({"id": __import__("uuid").uuid4(), "table_id": ventas,
                        "data": {"fecha": "2025-11-01", "producto": "Nuevo", "total": 300, "metodo_pago": "efectivo"}})
        assert (await render_dashboard(ORG_A, did))["kpis"][0]["value"] == 10_235_000

    async def test_tabla_de_731_filas_se_suma_completa_sin_el_limite_de_500(self, env):
        db = env.dbs.db(ORG_A)
        rows = [{"categoria": f"c{i % 9}", "total": (i % 9 + 1) * 1000} for i in range(731)]
        db.add_table("ventas", ["categoria", "total"], rows, column_types={"total": "number"})
        did, _ = await make(env, [
            {"table": "ventas", "chart_type": "kpi", "y": "sum(total)"},
            {"table": "ventas", "chart_type": "bar", "x": "categoria", "y": "sum(total)"},
            {"table": "ventas", "chart_type": "kpi", "y": "count"},
        ])
        out = await render_dashboard(ORG_A, did)
        values = {k["label"]: k["value"] for k in out["kpis"]}
        assert values["Suma de total"] == 3_648_000 and values["Registros de Ventas"] == 731
        assert sum(sum(r["total"] for r in rows[:500]) for _ in [0]) == 2_490_000      # lo que daba el LIMIT 500
        # categorias 0 y 1 aparecen 82 veces; el resto 81
        expected = {f"c{k}": (k + 1) * 1000 * (82 if k < 2 else 81) for k in range(9)}
        assert {p["name"]: p["value"] for p in out["charts"][0]["data"]} == expected

    @pytest.mark.skipif(not DEMO.exists(), reason="datos de la demo (brujula-demo/datos-expo) no disponibles")
    async def test_ventas_de_la_demo_731_filas_totales_exactos(self, env):
        """ventas.csv de la demo: 731 filas, total 44.527.400 (las primeras 500 sumaban 31.781.800), credito 18.022.900."""
        columns, rows = read_csv(DEMO, {"fecha": "date", "cantidad": "integer", "precio_unitario": "number", "total": "number"})
        env.dbs.db(ORG_A).add_table("ventas", columns, rows, display_name="Ventas",
                                    column_types={"fecha": "date", "cantidad": "integer", "precio_unitario": "number", "total": "number"})
        did, _ = await make(env, [
            {"table": "ventas", "chart_type": "kpi", "y": "sum(total)"},
            {"table": "ventas", "chart_type": "pie", "x": "metodo_pago", "y": "sum(total)"},
            {"table": "ventas", "chart_type": "line", "x": "month(fecha)", "y": "sum(total)"},
        ])
        out = await render_dashboard(ORG_A, did)
        assert out["kpis"][0]["value"] == 44_527_400
        line, pie_chart = out["charts"][1], out["charts"][0]     # cifras arriba; luego graficos en el orden pedido
        pie = {p["name"]: p["value"] for p in pie_chart["data"]}
        assert pie == {"credito": 18_022_900, "transferencia": 13_233_500, "efectivo": 9_375_300, "tarjeta": 3_895_700}
        assert [p["value"] for p in line["data"]] == [
            8_555_300, 7_321_600, 7_926_900, 8_294_200, 6_687_300, 5_742_100]


class TestErrorAislado:
    async def test_una_columna_renombrada_rompe_solo_ese_widget(self, env):
        db = env.dbs.db(ORG_A)
        ventas, _ = load_ferreteria(db)
        did, _ = await make(env, VENTAS)
        # renombran la columna metodo_pago -> forma_pago en el catalogo y en las filas
        import json as _json
        cols = _json.loads(db.tables[ventas]["columns_definition"])
        for c in cols:
            if c["name"] == "metodo_pago":
                c["name"] = "forma_pago"
        db.tables[ventas]["columns_definition"] = _json.dumps(cols)
        for r in db.rows:
            if r["table_id"] == ventas and "metodo_pago" in r["data"]:
                r["data"]["forma_pago"] = r["data"].pop("metodo_pago")

        out = await render_dashboard(ORG_A, did)

        assert out["kpis"][0]["value"] == 10_234_700
        line, bar, pie = out["charts"]
        assert not line.get("error") and not bar.get("error")
        assert pie["data"] == [] and "metodo_pago" in pie["error"] and "no existe" in pie["error"]
        assert pie["title"] == "Suma de total por metodo_pago"          # titulo guardado al crearlo

    async def test_tabla_borrada_da_error_por_widget_y_el_resto_sigue(self, env):
        db = env.dbs.db(ORG_A)
        load_ferreteria(db)
        did, _ = await make(env, [VENTAS[0], {"table": "productos", "chart_type": "kpi", "y": "count"}])
        prod = db.table_by_name("productos")["id"]
        db.tables.pop(prod)
        out = await render_dashboard(ORG_A, did)
        by_label = {k["label"]: k for k in out["kpis"]}
        assert by_label["Suma de total"]["value"] == 10_234_700
        errors = [k for k in out["kpis"] if k.get("error")]
        assert len(errors) == 1 and "productos" in errors[0]["error"] and errors[0]["value"] is None

    async def test_un_error_inesperado_del_motor_no_filtra_texto_de_celdas(self, env, caplog):
        load_ferreteria(env.dbs.db(ORG_A))
        did, _ = await make(env, VENTAS[:2])
        from unittest.mock import patch

        async def boom(pool, plans):
            raise RuntimeError("detalle con dato privado: Carlos Pinzon")

        with patch("app.services.data_query_engine.run_plans", boom):
            out = await render_dashboard(ORG_A, did)
        assert out["kpis"][0]["error"] == "no se pudo calcular este gráfico"
        assert out["charts"][0]["error"] == "no se pudo calcular este gráfico"
        assert "Carlos" not in json.dumps(out) and "Carlos" not in caplog.text

    async def test_statement_timeout_es_un_mensaje_de_lentitud_no_un_error_interno(self, env):
        load_ferreteria(env.dbs.db(ORG_A))
        did, _ = await make(env, VENTAS[:2])
        from unittest.mock import patch

        class Canceled(Exception):
            sqlstate = "57014"

        async def slow(pool, plans):
            raise Canceled()

        with patch("app.services.data_query_engine.run_plans", slow):
            out = await render_dashboard(ORG_A, did)
        assert out["charts"][0]["error"] == "este gráfico tardó demasiado en calcularse"

    async def test_el_tope_de_tiempo_global_corta_los_widgets_lentos_y_responde(self, env, settings_stub):
        load_ferreteria(env.dbs.db(ORG_A))
        did, _ = await make(env, VENTAS)
        settings_stub.DASHBOARD_RENDER_TIMEOUT_SECONDS = 1.0
        from unittest.mock import patch

        async def very_slow(pool, plans):
            await asyncio.sleep(30)

        started = time.monotonic()
        with patch("app.services.data_query_engine.run_plans", very_slow):
            out = await render_dashboard(ORG_A, did)
        assert time.monotonic() - started < 5
        assert len(out["kpis"]) + len(out["charts"]) == 4
        assert all(x["error"] for x in out["kpis"] + out["charts"])


class TestEspecificacionesHostiles:
    """El data_source_query lo puede escribir cualquier usuario autenticado por REST: nunca es de confianza."""

    def widget(self, dsq, wtype="bar_chart", title="g"):
        return (title, wtype, dsq, None)

    @pytest.mark.parametrize("dsq", [
        {"v": 2, "table": "ventas", "x": "producto", "y": "count"},
        {"v": 1, "table": "ventas", "x": "producto", "y": "count", "extra": "no permitido"},
        {"v": 1, "table": "ventas; DROP TABLE x", "x": "producto", "y": "count"},
        {"v": 1, "table": "ventas", "x": "producto", "y": "sum(total); DROP"},
        {"v": 1, "table": "ventas", "x": "producto", "y": "count", "filters": "nada"},
        {"v": 1, "table": "ventas", "x": ["lista"], "y": "count"},
        {"v": 1, "table": "ventas", "x": "producto", "y": "count", "filters": [["producto", "=", "x" * 10_000]]},
        {"v": 1, "table": "ventas", "x": "producto", "y": "count", "relleno": "x" * 10_000},
        {"v": 1, "table": {"a": 1}, "x": "producto", "y": "count"},
        "no es un objeto", ["lista"], 12345,
    ])
    async def test_cada_especificacion_hostil_es_un_error_del_widget_nunca_un_500(self, env, dsq):
        db = env.dbs.db(ORG_A)
        load_ferreteria(db)
        good = {"v": 1, "table": "ventas", "x": "metodo_pago", "y": "count"}
        did = db.add_dashboard("hostil", widgets=[self.widget(dsq), self.widget(good, "pie_chart")])
        out = await render_dashboard(ORG_A, str(did))
        assert out["legacy"] is False
        bad, ok = out["charts"]
        assert bad["error"] and bad["data"] == []
        assert not ok.get("error") and sum(p["value"] for p in ok["data"]) == 40

    async def test_500_widgets_se_recortan_y_no_tumban_el_tablero(self, env):
        db = env.dbs.db(ORG_A)
        load_ferreteria(db)
        spec_ = {"v": 1, "table": "ventas", "x": "metodo_pago", "y": "count"}
        did = db.add_dashboard("enorme", widgets=[self.widget(spec_, "pie_chart", f"g{i}") for i in range(500)])
        started = time.monotonic()
        out = await render_dashboard(ORG_A, str(did))
        assert len(out["charts"]) == 12 and time.monotonic() - started < 5

    async def test_un_widget_vacio_hecho_a_mano_se_ignora_y_si_son_todos_el_tablero_es_antiguo(self, env):
        db = env.dbs.db(ORG_A)
        load_ferreteria(db)
        did = db.add_dashboard("t", widgets=[("g", "bar_chart", None, None), ("h", "bar_chart", {}, None)])
        assert (await render_dashboard(ORG_A, str(did)))["legacy"] is True

    async def test_widget_con_tipo_no_compatible_es_un_error_de_ese_widget(self, env):
        db = env.dbs.db(ORG_A)
        load_ferreteria(db)
        good = {"v": 1, "table": "ventas", "x": "metodo_pago", "y": "count"}
        did = db.add_dashboard("t", widgets=[("g", "radar_chart", good, None), ("h", "pie_chart", good, None)])
        out = await render_dashboard(ORG_A, str(did))
        assert out["charts"][0]["error"] == "tipo de gráfico no compatible"
        assert not out["charts"][1].get("error")

    async def test_dsq_guardado_como_texto_jsonb_se_lee_igual(self, env):
        db = env.dbs.db(ORG_A)
        load_ferreteria(db)
        did, _ = await make(env, VENTAS[:1])
        assert db.jsonb_as_text is True          # la BD emulada entrega el jsonb como texto, igual que asyncpg
        assert (await render_dashboard(ORG_A, did))["kpis"][0]["value"] == 10_234_700

    async def test_tablero_borrado_o_inexistente_da_404(self, env):
        db = env.dbs.db(ORG_A)
        did = db.add_dashboard("viejo", deleted=True)
        for value in (str(did), "00000000-0000-4000-8000-000000000000"):
            with pytest.raises(HTTPException) as exc:
                await render_dashboard(ORG_A, value)
            assert exc.value.status_code == 404


class TestTablerosAntiguos:
    async def test_un_tablero_sin_especificaciones_sigue_funcionando_con_el_motor_y_cifras_del_catalogo(self, env):
        db = env.dbs.db(ORG_A)
        load_ferreteria(db)
        did = db.add_dashboard("hecho a mano")             # sin widgets: como los creados por POST /dashboards
        out = await render_dashboard(ORG_A, str(did))
        assert out["legacy"] is True
        kpis = {k["label"]: (k["value"], k["unit"]) for k in out["kpis"]}
        assert kpis["Registros totales"] == (70, "count")
        assert kpis["Total Ventas"] == (40, "count") and kpis["Total Productos"] == (30, "count")
        assert out["charts"] and all(not c.get("error") for c in out["charts"])
        titles = {c["title"] for c in out["charts"]}
        assert "Suma de total por mes de fecha" in titles and "Suma de total por producto" in titles

    async def test_el_tablero_antiguo_ya_no_se_calcula_sobre_500_filas(self, env):
        db = env.dbs.db(ORG_A)
        rows = [{"categoria": f"c{i % 9}", "total": (i % 9 + 1) * 1000} for i in range(731)]
        db.add_table("ventas", ["categoria", "total"], rows, column_types={"total": "number"})
        did = db.add_dashboard("antiguo")
        out = await render_dashboard(ORG_A, str(did))
        bar = next(c for c in out["charts"] if c["type"] == "bar")
        assert sum(p["value"] for p in bar["data"]) == 3_648_000     # antes: 2.490.000 (solo 500 filas)


class TestListaParaTarjetas:
    async def test_la_lista_trae_cuantos_graficos_origen_vista_previa_y_titulos(self, env):
        db = env.dbs.db(ORG_A)
        load_ferreteria(db)
        await make(env, VENTAS, "Ventas")
        db.add_dashboard("a mano")
        items = {d.name: d for d in await list_dashboards(ORG_A)}
        board = items["Ventas"]
        assert board.widget_count == 4 and board.source == "assistant"
        assert board.preview == {"type": "line", "points": [3315500, 3174500, 2994700, 750000]}
        assert board.highlights == [
            "Suma de total por mes de fecha", "Suma de total por producto", "Suma de total por metodo_pago"]
        manual = items["a mano"]
        assert (manual.widget_count, manual.source, manual.preview, manual.highlights) == (0, None, None, [])

    async def test_una_vista_previa_hostil_escrita_por_rest_se_ignora(self, env):
        db = env.dbs.db(ORG_A)
        db.add_dashboard("x", widgets=[("g", "bar_chart", None, {"preview": {"type": "bar", "points": ["<b>x</b>", True, 5]}})])
        (item,) = await list_dashboards(ORG_A)
        assert item.preview == {"type": "bar", "points": [5]}
