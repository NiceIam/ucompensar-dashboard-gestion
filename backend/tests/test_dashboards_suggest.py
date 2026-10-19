"""Tableros sugeridos (regla determinista + una llamada pequena a Gemini) — PI0320251.

Todo con BD emulada y Gemini simulado (`generate_content` es un AsyncMock): ninguna prueba toca la red.
Valores esperados A MANO (modulo csv sobre test-data/ferreteria): ventas 40 filas, total 10.234.700;
productos 30 filas. Lo que NO se puede probar aqui: la calidad de las propuestas del modelo real.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import dashboard_rules as rules
from app.services import dashboard_suggest_service as svc
from app.services.dashboard_render_service import render_dashboard
from tests.dash_support import ORG_A, catalog_of, env, gemini, load_ferreteria, settings_stub  # noqa: F401
from tests.fake_gemini import text_response, usage

GOOD_JSON = json.dumps({"dashboards": [
    {"title": "Ventas del año", "widgets": [
        {"table": "ventas", "chart_type": "kpi", "y": "sum(total)"},
        {"table": "ventas", "chart_type": "line", "x": "month(fecha)", "y": "sum(total)"},
        {"table": "ventas", "chart_type": "bar", "x": "producto", "y": "sum(total)", "top": 10},
    ]},
    {"title": "Cómo pagan", "widgets": [
        {"table": "ventas", "chart_type": "pie", "x": "metodo_pago", "y": "sum(total)"},
        {"table": "ventas", "chart_type": "kpi", "y": "count"},
    ]},
]})


def model_returns(gemini, text, prompt=900, output=300):
    gemini.generate.side_effect = None
    gemini.generate.return_value = text_response(text, usage(prompt, output, 12))
    gemini.generate = gemini.client.aio.models.generate_content = AsyncMock(
        return_value=text_response(text, usage(prompt, output, 12))
    )
    return gemini.generate


@pytest.fixture
def seeded(env):
    db = env.dbs.db(ORG_A)
    load_ferreteria(db)
    return db


def shapes(db, board_id):
    return sorted(
        (w["widget_type"], w["data_source_query"].get("x"), w["data_source_query"]["y"])
        for w in db.widgets if str(w["dashboard_id"]) == board_id
    )


class TestRegla:
    async def test_sin_clave_crea_tableros_con_la_regla_sin_llamar_al_modelo(self, env, seeded, gemini):
        env.settings.GOOGLE_API_KEY = ""
        out = await svc.suggest(ORG_A)
        assert out["status"] == "created" and out["source"] == "rules"
        gemini.ctor.assert_not_called()
        names = [b["name"] for b in out["dashboards"]]
        assert names == ["Resumen de Ventas", "Resumen de Productos"]       # fecha+medida primero
        ventas = out["dashboards"][0]
        assert shapes(seeded, ventas["id"]) == sorted([
            ("kpi_card", None, "sum(total)"), ("kpi_card", None, "count"),
            ("line_chart", "month(fecha)", "sum(total)"),
            ("bar_chart", "producto", "sum(total)"),
            ("pie_chart", "metodo_pago", "count"),
        ])

    async def test_un_precio_unitario_se_promedia_no_se_suma(self, env, seeded):
        env.settings.GOOGLE_API_KEY = ""
        out = await svc.suggest(ORG_A)
        productos = out["dashboards"][1]
        kinds = {(t, y) for t, _x, y in shapes(seeded, productos["id"])}
        assert ("kpi_card", "avg(precio_venta)") in kinds and ("kpi_card", "count") in kinds
        assert not any(y.startswith("sum(precio") for _t, y in kinds)

    async def test_lo_creado_se_abre_con_valores_correctos(self, env, seeded):
        env.settings.GOOGLE_API_KEY = ""
        out = await svc.suggest(ORG_A)
        data = await render_dashboard(ORG_A, out["dashboards"][0]["id"])
        kpis = {k["label"]: k["value"] for k in data["kpis"]}
        assert kpis == {"Suma de total": 10_234_700, "Registros de Ventas": 40}
        pie = next(c for c in data["charts"] if c["type"] == "pie")
        assert pie["title"] == "Cantidad por metodo_pago"
        assert {p["name"]: p["value"] for p in pie["data"]} == {"efectivo": 16, "transferencia": 14, "tarjeta": 10}
        assert not any(c.get("error") for c in data["charts"])

    async def test_hoja_solo_de_texto_igual_produce_un_tablero_con_contenido(self, env):
        env.settings.GOOGLE_API_KEY = ""
        env.dbs.db(ORG_A).add_table("contactos", ["nombre", "ciudad"], [
            {"nombre": f"n{i}", "ciudad": ["Bogota", "Cali"][i % 2]} for i in range(10)])
        out = await svc.suggest(ORG_A)
        assert out["status"] == "created"
        data = await render_dashboard(ORG_A, out["dashboards"][0]["id"])
        assert data["kpis"][0]["value"] == 10 and data["charts"][0]["data"]

    async def test_sin_datos_no_crea_nada(self, env):
        env.dbs.db(ORG_A).add_table("vacia", ["a"], [])
        assert (await svc.suggest(ORG_A))["status"] == "no_data"
        assert env.dbs.db(ORG_A).dashboards == {}

    def test_la_granularidad_sigue_el_rango_de_fechas(self):
        from app.services.data_query_engine import Column
        assert rules._bucket(Column("f", "f", ("2026-01-01", "2026-02-15"))) == "day"
        assert rules._bucket(Column("f", "f", ("2026-01-01", "2026-12-31"))) == "month"
        assert rules._bucket(Column("f", "f", ("2010-01-01", "2026-12-31"))) == "year"
        assert rules._bucket(Column("f", "f", None)) == "month"

    async def test_la_medida_prefiere_total_sobre_precio_unitario_y_nunca_un_id(self, env):
        db = env.dbs.db(ORG_A)
        db.add_table("pedidos", ["codigo", "precio_unitario", "total", "stock", "fecha"],
                     [{"codigo": 1, "precio_unitario": 5, "total": 10, "stock": 2, "fecha": "2026-01-02"}] * 3,
                     column_types={"codigo": "integer", "precio_unitario": "number", "total": "number",
                                   "stock": "integer", "fecha": "date"})
        _pool, catalog = await catalog_of(env)
        plans = rules.plan_dashboards(catalog)
        assert plans[0].widgets[0] == {"table": "pedidos", "chart_type": "kpi", "y": "sum(total)"}


class TestModelo:
    async def test_una_sola_llamada_con_catalogo_compacto_sin_datos_y_registra_tokens(self, env, seeded, gemini, caplog):
        import logging
        gen = model_returns(gemini, GOOD_JSON)
        with caplog.at_level(logging.INFO, logger="app.services.dashboard_suggest_service"):
            out = await svc.suggest(ORG_A)
        assert gen.await_count == 1
        assert out["status"] == "created" and out["source"] == "ai"
        assert [b["name"] for b in out["dashboards"]] == ["Ventas del año", "Cómo pagan"]
        kwargs = gen.await_args.kwargs
        contents, config = kwargs["contents"], kwargs["config"]
        assert "ventas[40]" in contents and "total:n" in contents
        for private in ("Cemento", "Carlos Pinzon", "385000"):
            assert private not in contents and private not in config.system_instruction       # SIN datos
        assert config.max_output_tokens == 900 and config.response_mime_type == "application/json"
        assert config.thinking_config.thinking_level.name == "LOW"
        assert out["tokens"] == {"prompt": 900, "output": 300, "thoughts": 12, "total": 1212}
        assert "Sugerencia IA: resultado=ok tokens prompt=900 salida=300 razonamiento=12 total=1212" in caplog.text
        # entrada estimada con caracteres/4: instrucciones + catalogo, muy por debajo de 4.000 tokens
        assert (len(contents) + len(config.system_instruction)) / 4 < 700

    async def test_las_propuestas_del_modelo_se_validan_contra_el_catalogo(self, env, seeded, gemini):
        bad = json.dumps({"dashboards": [{"title": "Malo", "widgets": [
            {"table": "ventas", "chart_type": "bar", "x": "regional", "y": "sum(total)"},
            {"table": "nada", "chart_type": "kpi", "y": "count"}]},
            {"title": "Bueno", "widgets": [{"table": "ventas", "chart_type": "kpi", "y": "count"}]}]})
        model_returns(gemini, bad)
        out = await svc.suggest(ORG_A)
        assert [b["name"] for b in out["dashboards"]] == ["Bueno"] and out["source"] == "ai"
        assert out["notes"] and "regional" in out["notes"][0]

    @pytest.mark.parametrize("text", [
        "esto no es json", "", "[]", '{"dashboards": "x"}', '{"dashboards":[{"title":"x","widgets":"no"}]}',
        '{"dashboards":[{"title":"x","widgets":[{"table":"ventas","chart_type":"bar","x":"nada","y":"count"}]}]}',
    ])
    async def test_respuesta_invalida_cae_a_la_regla_sin_reintentar(self, env, seeded, gemini, text):
        gen = model_returns(gemini, text)
        out = await svc.suggest(ORG_A)
        assert gen.await_count == 1                               # nunca un segundo llamado
        assert out["status"] == "created" and out["source"] == "rules"
        assert [b["name"] for b in out["dashboards"]] == ["Resumen de Ventas", "Resumen de Productos"]

    async def test_json_con_cercas_markdown_se_acepta(self, env, seeded, gemini):
        model_returns(gemini, "```json\n" + GOOD_JSON + "\n```")
        assert (await svc.suggest(ORG_A))["source"] == "ai"

    @pytest.mark.parametrize("error", [RuntimeError("boom"), TimeoutError()])
    async def test_si_el_modelo_falla_se_usa_la_regla(self, env, seeded, gemini, error):
        gen = model_returns(gemini, GOOD_JSON)
        gen.side_effect = error
        out = await svc.suggest(ORG_A)
        assert out["source"] == "rules" and out["status"] == "created"

    async def test_un_fallo_no_se_reintenta_y_no_vuelve_a_gastar(self, env, seeded, gemini, settings_stub):
        gen = model_returns(gemini, "no json")
        await svc.suggest(ORG_A)
        for board in list(seeded.dashboards):
            seeded.dashboards[board]["deleted_at"] = seeded.dashboards[board]["created_at"]
        await svc.suggest(ORG_A)
        assert gen.await_count == 1

    async def test_el_mismo_catalogo_no_llama_otra_vez_ni_duplica(self, env, seeded, gemini):
        gen = model_returns(gemini, GOOD_JSON)
        first = await svc.suggest(ORG_A)
        second = await svc.suggest(ORG_A)
        assert gen.await_count == 1 and second["status"] == "exists"
        assert {b["id"] for b in second["dashboards"]} == {b["id"] for b in first["dashboards"]}
        assert len(seeded.dashboards) == 2

    async def test_borrados_y_pedidos_de_nuevo_vuelven_de_la_cache_sin_llamar(self, env, seeded, gemini):
        gen = model_returns(gemini, GOOD_JSON)
        await svc.suggest(ORG_A)
        for d in seeded.dashboards.values():
            d["deleted_at"] = d["created_at"]
        again = await svc.suggest(ORG_A)
        assert gen.await_count == 1 and again["status"] == "created" and again["source"] == "ai"

    async def test_catalogo_nuevo_si_vuelve_a_preguntar_pero_mas_filas_no(self, env, seeded, gemini):
        gen = model_returns(gemini, GOOD_JSON)
        await svc.suggest(ORG_A)
        ventas = seeded.table_by_name("ventas")["id"]
        seeded.add_table("devoluciones", ["producto", "motivo"], [{"producto": "x", "motivo": "y"}])
        for d in seeded.dashboards.values():
            d["deleted_at"] = d["created_at"]
        await svc.suggest(ORG_A)
        assert gen.await_count == 2                                # hoja nueva -> firma nueva
        sig = svc.catalog_signature
        pool, catalog = await catalog_of(env)
        before = sig(catalog)
        seeded.rows.append({"id": __import__("uuid").uuid4(), "table_id": ventas, "data": {"total": 1}})
        seeded.tables[ventas]["row_count"] += 1
        _pool, catalog2 = await catalog_of(env)
        assert sig(catalog2) == before                             # mas filas: misma firma

    async def test_tope_diario_por_organizacion_con_firmas_distintas(self, env, seeded, gemini, settings_stub):
        settings_stub.DASHBOARD_SUGGEST_DAILY_CALLS = 1
        gen = model_returns(gemini, GOOD_JSON)
        await svc.suggest(ORG_A)
        seeded.add_table("otra", ["a", "b"], [{"a": "x", "b": 1}], column_types={"b": "number"})
        for d in seeded.dashboards.values():
            d["deleted_at"] = d["created_at"]
        out = await svc.suggest(ORG_A)
        assert gen.await_count == 1 and out["source"] == "rules"

    async def test_tope_duro_por_proceso(self, env, seeded, gemini):
        import time
        svc._call_times[:] = [time.monotonic()] * svc._HARD_CALLS_PER_HOUR
        gen = model_returns(gemini, GOOD_JSON)
        out = await svc.suggest(ORG_A)
        assert gen.await_count == 0 and out["source"] == "rules"

    async def test_interruptor_apagado_y_clave_vacia_no_llaman(self, env, seeded, gemini, settings_stub):
        gen = model_returns(gemini, GOOD_JSON)
        settings_stub.DASHBOARD_SUGGEST_USE_LLM = False
        await svc.suggest(ORG_A)
        assert gen.await_count == 0
        svc.reset_caches()
        for d in seeded.dashboards.values():
            d["deleted_at"] = d["created_at"]
        settings_stub.DASHBOARD_SUGGEST_USE_LLM, settings_stub.GOOGLE_API_KEY = True, "  "
        await svc.suggest(ORG_A)
        assert gen.await_count == 0

    async def test_dos_pedidos_simultaneos_de_la_misma_org_hacen_una_sola_llamada(self, env, seeded, gemini):
        import asyncio
        gen = model_returns(gemini, GOOD_JSON)
        a, b = await asyncio.gather(svc.suggest(ORG_A), svc.suggest(ORG_A))
        assert gen.await_count == 1 and len(seeded.dashboards) == 2
        assert sorted([a["status"], b["status"]]) == ["created", "exists"]

    async def test_la_clave_nunca_aparece_en_los_logs(self, env, seeded, gemini, caplog):
        gen = model_returns(gemini, GOOD_JSON)
        gen.side_effect = RuntimeError("clave AIzaSy-TEST-SECRET-KEY-123 invalida")
        await svc.suggest(ORG_A)
        assert "AIzaSy-TEST-SECRET-KEY-123" not in caplog.text


class TestAutomatico:
    async def test_solo_si_no_hay_tableros(self, env, seeded, gemini):
        gen = model_returns(gemini, GOOD_JSON)
        seeded.add_dashboard("ya tengo uno")
        out = await svc.suggest(ORG_A, auto=True)
        assert out["status"] == "has_dashboards" and gen.await_count == 0

    async def test_no_resucita_un_tablero_que_la_persona_borro(self, env, seeded, gemini):
        gen = model_returns(gemini, GOOD_JSON)
        first = await svc.suggest(ORG_A, auto=True)
        assert first["status"] == "created"
        for d in seeded.dashboards.values():
            d["deleted_at"] = d["created_at"]
        again = await svc.suggest(ORG_A, auto=True)
        assert again["status"] == "already_suggested" and gen.await_count == 1

    async def test_el_gancho_de_carga_nunca_lanza_aunque_todo_falle(self, env, seeded, gemini, settings_stub):
        settings_stub.DASHBOARD_AUTO_SUGGEST = True
        seeded.fail_when = lambda sql, args: True
        await svc.auto_suggest_after_upload(ORG_A)               # no lanza

    async def test_el_gancho_respeta_el_interruptor(self, env, seeded, gemini, settings_stub):
        settings_stub.DASHBOARD_AUTO_SUGGEST = False
        await svc.auto_suggest_after_upload(ORG_A)
        assert seeded.dashboards == {}
        settings_stub.DASHBOARD_AUTO_SUGGEST = True
        settings_stub.GOOGLE_API_KEY = ""
        await svc.auto_suggest_after_upload(ORG_A)
        assert len(seeded.dashboards) == 2

    async def test_una_org_nunca_queda_con_los_tableros_vacios(self, env, seeded):
        env.settings.GOOGLE_API_KEY = ""
        out = await svc.suggest(ORG_A, auto=True)
        for board in out["dashboards"]:
            data = await render_dashboard(ORG_A, board["id"])
            assert data["kpis"] or any(c["data"] for c in data["charts"])
            assert not any(c.get("error") for c in data["charts"])
