"""Tests de agent_tools_service (chat con IA) — PI0320251.

Cubre:
- query_data: que datos devuelve, relevancia por pregunta, aislamiento por org
- analyze_table / create_chart: tools que el chat NO usa hoy, pero siguen en el modulo
- process_with_gemini: contexto con datos reales, historial, extraccion de charts
- Fallas de Gemini: excepcion del cliente (cuota, API, timeout, red, credenciales),
  respuesta vacia o bloqueada -> respuesta amable, sin texto crudo ni API key

NUNCA se llama a Gemini real: `google.genai.Client` se reemplaza por un mock en
TODOS los tests de este modulo (fixture autouse `gemini`). La BD se emula con
tests/fake_org_db.py y la BD principal (organizations) con FakeMainPool.

Lo que NO se puede probar sin infraestructura real: la latencia/timeout real de
Gemini (solo se simula la excepcion) y el comportamiento de asyncpg/Postgres
(solo se emula).
"""

import asyncio
import json
import logging
import re
import time
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.services.agent_tools_service import (
    _classify_gemini_failure,
    _clean_cell,
    _fmt_number,
    analyze_table,
    create_chart,
    process_with_gemini,
    query_data,
)
from tests.fake_gemini import make_fake_genai, text_response
from tests.fake_org_db import FakeMainPool, FakeOrgDBs

ORG_A = "550e8400-e29b-41d4-a716-446655440000"
ORG_B = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"

SECRET_KEY = "AIzaSy-TEST-SECRET-KEY-123"
MODEL = "gemini-test-model"
SERVICE_LOGGER = "app.services.agent_tools_service"


# ---------------------------------------------------------------------------
# Infraestructura de test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def gemini():
    """Reemplaza el cliente google.genai COMPLETO. Ningun test toca la red."""
    fake = make_fake_genai()
    with patch("google.genai.Client", return_value=fake.client) as ctor:
        yield SimpleNamespace(
            client=fake.client, chat=fake.chat, ctor=ctor, create=fake.create, send=fake.send, aclose=fake.aclose
        )


@pytest.fixture(autouse=True)
def _settings():
    """Clave y modelo conocidos para poder verificar que la clave no se filtra."""
    stub = SimpleNamespace(GOOGLE_API_KEY=SECRET_KEY, GEMINI_MODEL=MODEL, GEMINI_TIMEOUT_SECONDS=25.0)
    with patch("app.services.agent_tools_service.get_settings", return_value=stub):
        yield stub


@pytest.fixture
def env():
    """BDs en memoria instaladas como get_org_pool / get_main_pool del servicio."""
    dbs = FakeOrgDBs()
    main = FakeMainPool()
    main.orgs[ORG_A] = {"name": "Ferreteria Alfa", "sector": "comercio", "city": "Bogota"}
    main.orgs[ORG_B] = {"name": "Restaurante Beta", "sector": "comercio", "city": "Cali"}
    with patch("app.services.agent_tools_service.get_org_pool", dbs.get_org_pool), patch(
        "app.services.agent_tools_service.get_main_pool", main.get_main_pool
    ):
        yield SimpleNamespace(dbs=dbs, main=main)


def seed_ventas(env, org_id: str = ORG_A, rows: list[dict] | None = None):
    rows = rows if rows is not None else [
        {"producto": "Martillo", "total": 100},
        {"producto": "Taladro", "total": 200},
        {"producto": "Sierra", "total": 300},
    ]
    return env.dbs.db(org_id).add_table(
        "ventas",
        ["producto", "total"],
        rows,
        display_name="Ventas",
        column_types={"total": "number"},
    )


def system_prompt(gemini) -> str:
    return gemini.create.call_args.kwargs["config"].system_instruction


# ---------------------------------------------------------------------------
# query_data
# ---------------------------------------------------------------------------

class TestQueryData:
    async def test_devuelve_filas_columnas_y_metadatos_de_la_tabla(self, env):
        seed_ventas(env)

        out = await query_data(ORG_A, "ventas")

        assert list(out) == ["Ventas"]
        info = out["Ventas"]
        assert info["table_name"] == "ventas"
        assert info["row_count"] == 3
        assert info["columns"] == ["producto", "total"]
        assert info["data"] == [
            {"producto": "Martillo", "total": 100},
            {"producto": "Taladro", "total": 200},
            {"producto": "Sierra", "total": 300},
        ]

    @pytest.mark.parametrize("jsonb_as_text", [True, False])
    async def test_acepta_jsonb_como_texto_o_como_dict(self, env, jsonb_as_text):
        """asyncpg entrega jsonb como str; el codigo debe tolerar ambos."""
        seed_ventas(env)
        env.dbs.db(ORG_A).jsonb_as_text = jsonb_as_text

        out = await query_data(ORG_A, "ventas")

        assert out["Ventas"]["data"][0] == {"producto": "Martillo", "total": 100}

    async def test_descarta_filas_que_no_son_objetos(self, env):
        """Una fila jsonb que no es un objeto (lista, texto) no debe romper ni colarse."""
        seed_ventas(env, rows=[{"producto": "Martillo", "total": 1}, ["lista"], "texto suelto"])

        out = await query_data(ORG_A, "ventas")

        assert out["Ventas"]["data"] == [{"producto": "Martillo", "total": 1}]
        assert out["Ventas"]["row_count"] == 1

    async def test_org_sin_tablas_devuelve_vacio(self, env):
        assert await query_data(ORG_A, "cuanto vendi?") == {}

    async def test_tabla_vacia_se_omite(self, env):
        env.dbs.db(ORG_A).add_table("ventas", ["producto"], [], display_name="Ventas")

        assert await query_data(ORG_A, "ventas") == {}

    async def test_row_count_none_se_trata_como_vacia(self, env):
        tid = seed_ventas(env)
        env.dbs.db(ORG_A).tables[tid]["row_count"] = None

        assert await query_data(ORG_A, "ventas") == {}

    async def test_pocas_tablas_con_datos_se_buscan_todas_aunque_la_pregunta_no_las_nombre(self, env):
        seed_ventas(env)
        env.dbs.db(ORG_A).add_table("clientes", ["nombre"], [{"nombre": "Ana"}], display_name="Clientes")

        out = await query_data(ORG_A, "hola, como estas?")

        assert set(out) == {"Ventas", "Clientes"}

    async def test_pregunta_sin_datos_en_la_org_devuelve_vacio_sin_error(self, env):
        env.dbs.db(ORG_A)  # BD existe pero sin tablas

        assert await query_data(ORG_A, "dame el total de ventas de marzo") == {}

    @staticmethod
    def _seed_seis_tablas(env, extra_columns: dict[str, list[str]] | None = None):
        """6 tablas con datos -> se activa el filtro por relevancia (>4)."""
        db = env.dbs.db(ORG_A)
        extra_columns = extra_columns or {}
        for name in ["ventas", "clientes", "productos", "gastos", "empleados", "sucursales"]:
            cols = extra_columns.get(name, ["valor"])
            db.add_table(name, cols, [{c: "x" for c in cols}], display_name=name.title())

    @pytest.mark.parametrize(
        "pregunta, esperadas",
        [
            ("cuanto suman las ventas", {"Ventas"}),              # por table_name
            ("VENTAS Y CLIENTES", {"Ventas", "Clientes"}),        # insensible a mayusculas
            ("dame el valor promedio", {"Ventas", "Clientes", "Productos", "Gastos", "Empleados", "Sucursales"}),  # por columna
        ],
    )
    async def test_con_mas_de_4_tablas_solo_las_que_se_nombran(self, env, pregunta, esperadas):
        self._seed_seis_tablas(env)

        out = await query_data(ORG_A, pregunta)

        assert set(out) == esperadas

    async def test_con_mas_de_4_tablas_y_ninguna_nombrada_no_devuelve_datos(self, env):
        """Documenta el comportamiento actual (ver tambien el xfail de lenguaje natural)."""
        self._seed_seis_tablas(env)

        assert await query_data(ORG_A, "hola") == {}

    @pytest.mark.xfail(
        strict=True,
        reason="BUG agent_tools_service.py:49-52 -- la relevancia es `kw in pregunta` por subcadena literal: "
        "con >4 tablas, 'cuanto vendimos este mes' no recibe la tabla ventas (el chat responde sin datos).",
    )
    async def test_pregunta_en_lenguaje_natural_recibe_la_tabla_relacionada(self, env):
        self._seed_seis_tablas(env)

        out = await query_data(ORG_A, "cuanto vendimos este mes?")

        assert "Ventas" in out

    @pytest.mark.xfail(
        strict=True,
        reason="BUG agent_tools_service.py:49-52 -- un nombre de columna corto ('id') coincide como subcadena "
        "de cualquier palabra ('decidio') y mete tablas irrelevantes al contexto.",
    )
    async def test_columna_corta_no_activa_tabla_irrelevante_por_subcadena(self, env):
        self._seed_seis_tablas(env, extra_columns={"gastos": ["id"]})

        out = await query_data(ORG_A, "Quien decidio el presupuesto?")

        assert out == {}

    async def test_aislamiento_por_org_solo_lee_la_bd_de_la_org_pedida(self, env):
        seed_ventas(env, ORG_A)
        env.dbs.db(ORG_B).add_table(
            "ventas", ["producto"], [{"producto": "SECRETO_DE_B"}], display_name="Ventas"
        )

        out_a = await query_data(ORG_A, "ventas")
        out_b = await query_data(ORG_B, "ventas")

        assert "SECRETO_DE_B" not in json.dumps(out_a)
        assert [r["producto"] for r in out_b["Ventas"]["data"]] == ["SECRETO_DE_B"]
        assert env.dbs.requested_org_ids == [ORG_A, ORG_B]

    async def test_row_count_truncado_no_baja_del_total_real_ni_del_conteo_cargado(self, env):
        tid = seed_ventas(env, rows=[{"producto": f"p{i}", "total": i} for i in range(1005)])
        env.dbs.db(ORG_A).tables[tid]["row_count"] = 500   # contador desactualizado

        out = await query_data(ORG_A, "ventas")

        assert out["Ventas"]["row_count"] == 1000

    async def test_limita_a_1000_filas_por_tabla(self, env):
        seed_ventas(env, rows=[{"producto": f"p{i}", "total": i} for i in range(1005)])

        out = await query_data(ORG_A, "ventas")

        assert len(out["Ventas"]["data"]) == 1000

    async def test_row_count_refleja_el_total_real_aunque_se_trunque_la_muestra(self, env):
        seed_ventas(env, rows=[{"producto": f"p{i}", "total": i} for i in range(1005)])

        out = await query_data(ORG_A, "ventas")

        assert out["Ventas"]["row_count"] == 1005


# ---------------------------------------------------------------------------
# analyze_table / create_chart (no las usa el chat hoy)
# ---------------------------------------------------------------------------

class TestAnalyzeTable:
    async def test_estadisticas_numericas_y_top_values(self, env):
        seed_ventas(env, rows=[
            {"producto": "Martillo", "total": 100},
            {"producto": "Martillo", "total": 200},
            {"producto": "Sierra", "total": "300"},   # numero como texto: se convierte
        ])

        out = await analyze_table(ORG_A, "ventas")

        stats = out["Ventas"]
        assert stats["total_rows"] == 3
        assert stats["columns"]["total"] == {
            "non_null": 3, "unique": 3, "min": 100.0, "max": 300.0, "avg": 200.0, "sum": 600.0,
        }
        assert stats["columns"]["producto"]["top_values"][0] == {"value": "Martillo", "count": 2}

    async def test_sin_nombre_analiza_solo_tablas_con_datos(self, env):
        seed_ventas(env)
        env.dbs.db(ORG_A).add_table("vacia", ["x"], [], display_name="Vacia")

        assert set(await analyze_table(ORG_A)) == {"Ventas"}

    async def test_tabla_inexistente_devuelve_vacio(self, env):
        seed_ventas(env)

        assert await analyze_table(ORG_A, "no_existe") == {}

    async def test_aislamiento_por_org(self, env):
        seed_ventas(env, ORG_A)
        assert await analyze_table(ORG_B) == {}


class TestCreateChart:
    async def test_cuenta_por_categoria_ordenado_desc(self, env):
        seed_ventas(env, rows=[{"producto": "A"}, {"producto": "B"}, {"producto": "B"}])

        out = await create_chart(ORG_A, "ventas", "bar", "producto", "count")

        assert out["data"] == [{"name": "B", "value": 2}, {"name": "A", "value": 1}]
        assert out["title"] == "Ventas por producto"
        assert out["color"] == "#3b82f6"

    async def test_suma_valores_y_tolera_valores_no_numericos(self, env):
        seed_ventas(env, rows=[
            {"producto": "A", "total": 10}, {"producto": "A", "total": "basura"}, {"producto": "B", "total": 5},
        ])

        out = await create_chart(ORG_A, "ventas", "pie", "producto", "total", title="Mi grafico")

        assert out["data"] == [{"name": "A", "value": 10}, {"name": "B", "value": 5}]
        assert out["title"] == "Mi grafico"

    async def test_tabla_inexistente_y_tabla_vacia_devuelven_error(self, env):
        env.dbs.db(ORG_A).add_table("vacia", ["x"], [], display_name="Vacia")

        assert "no encontrada" in (await create_chart(ORG_A, "nada", "bar", "x", "count"))["error"]
        assert "no tiene datos" in (await create_chart(ORG_A, "vacia", "bar", "x", "count"))["error"]

    async def test_limita_a_15_categorias(self, env):
        seed_ventas(env, rows=[{"producto": f"p{i}"} for i in range(40)])

        out = await create_chart(ORG_A, "ventas", "bar", "producto", "count")

        assert len(out["data"]) == 15


# ---------------------------------------------------------------------------
# process_with_gemini — camino feliz y contexto
# ---------------------------------------------------------------------------

class TestProcessWithGeminiContexto:
    async def test_arma_el_prompt_con_org_tablas_y_datos_reales(self, env, gemini):
        seed_ventas(env)

        result = await process_with_gemini(ORG_A, "cuanto vendi?")

        assert result == {"text": "Respuesta de prueba", "charts": [], "actions": []}
        prompt = system_prompt(gemini)
        assert 'empresa "Ferreteria Alfa"' in prompt
        assert "- Ventas (ventas): 3 filas. Columnas: producto, total" in prompt
        assert "Datos de Ventas (3 filas)" in prompt
        assert '"producto": "Martillo"' in prompt and '"total": 300' in prompt

    async def test_usa_modelo_y_clave_de_la_configuracion_y_envia_el_mensaje(self, env, gemini):
        seed_ventas(env)

        await process_with_gemini(ORG_A, "cuanto vendi?")

        gemini.ctor.assert_called_once()
        assert gemini.ctor.call_args.kwargs["api_key"] == SECRET_KEY
        assert gemini.create.call_args.kwargs["model"] == MODEL
        gemini.send.assert_called_once_with("cuanto vendi?")

    async def test_usa_la_api_async_del_sdk_y_cierra_el_cliente(self, env, gemini):
        await process_with_gemini(ORG_A, "hola")

        gemini.client.chats.create.assert_not_called()  # la API sincrona bloquearia el event loop
        gemini.aclose.assert_awaited_once()

    async def test_cierra_el_cliente_async_tambien_cuando_gemini_falla(self, env, gemini):
        gemini.send.side_effect = RuntimeError("boom")

        await process_with_gemini(ORG_A, "hola")

        gemini.aclose.assert_awaited_once()

    async def test_si_cerrar_el_cliente_falla_no_se_pierde_la_respuesta(self, env, gemini):
        gemini.aclose.side_effect = RuntimeError("no se pudo cerrar")

        result = await process_with_gemini(ORG_A, "hola")

        assert result["text"] == "Respuesta de prueba"
        assert "fallback_reason" not in result

    async def test_timeout_del_sdk_va_en_milisegundos_y_viene_de_la_configuracion(self, env, gemini, _settings):
        _settings.GEMINI_TIMEOUT_SECONDS = 12.5

        await process_with_gemini(ORG_A, "hola")

        assert gemini.ctor.call_args.kwargs["http_options"].timeout == 12500

    @pytest.mark.parametrize("configurado", [0, -3, None])
    async def test_timeout_invalido_usa_el_default_de_25_segundos(self, env, gemini, _settings, configurado):
        _settings.GEMINI_TIMEOUT_SECONDS = configurado

        await process_with_gemini(ORG_A, "hola")

        assert gemini.ctor.call_args.kwargs["http_options"].timeout == 25000

    def test_la_configuracion_real_trae_25s_por_defecto_y_se_sobreescribe_por_entorno(self, monkeypatch):
        from app.config import Settings

        monkeypatch.delenv("GEMINI_TIMEOUT_SECONDS", raising=False)
        assert Settings(_env_file=None).GEMINI_TIMEOUT_SECONDS == 25.0
        monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "7.5")
        assert Settings(_env_file=None).GEMINI_TIMEOUT_SECONDS == 7.5

    async def test_org_desconocida_usa_nombre_generico(self, env, gemini):
        del env.main.orgs[ORG_A]

        await process_with_gemini(ORG_A, "hola")

        assert 'empresa "tu empresa"' in system_prompt(gemini)

    async def test_org_id_que_no_es_uuid_no_rompe(self, env, gemini):
        env.main.orgs["org-legacy"] = {"name": "Legacy SA", "sector": "x", "city": "y"}

        await process_with_gemini("org-legacy", "hola")

        assert 'empresa "Legacy SA"' in system_prompt(gemini)

    async def test_aislamiento_por_org_el_prompt_no_incluye_datos_de_otra_org(self, env, gemini):
        seed_ventas(env, ORG_A)
        env.dbs.db(ORG_B).add_table(
            "ventas", ["producto"], [{"producto": "SECRETO_DE_B"}], display_name="Ventas"
        )

        await process_with_gemini(ORG_A, "ventas")

        assert "SECRETO_DE_B" not in system_prompt(gemini)
        assert "Restaurante Beta" not in system_prompt(gemini)
        assert env.dbs.requested_org_ids == [ORG_A, ORG_A]  # una vez por contexto, otra por query_data

    async def test_org_sin_tablas_igual_responde_y_el_prompt_no_trae_bloque_de_datos(self, env, gemini):
        result = await process_with_gemini(ORG_A, "que datos tengo?")

        assert result["text"] == "Respuesta de prueba"
        assert "Datos de " not in system_prompt(gemini)

    async def test_tabla_vacia_se_lista_pero_no_aporta_datos(self, env, gemini):
        env.dbs.db(ORG_A).add_table("ventas", ["producto"], [], display_name="Ventas")

        await process_with_gemini(ORG_A, "ventas")

        prompt = system_prompt(gemini)
        assert "- Ventas (ventas): 0 filas" in prompt
        assert "Datos de Ventas" not in prompt

    async def test_el_contexto_solo_incluye_10_filas_de_muestra(self, env, gemini):
        seed_ventas(env, rows=[{"producto": f"prod{i:02d}", "total": i} for i in range(25)])

        await process_with_gemini(ORG_A, "ventas")

        prompt = system_prompt(gemini)
        assert "prod09" in prompt
        assert "prod10" not in prompt

    async def test_el_prompt_avisa_que_los_datos_son_una_muestra(self, env, gemini):
        seed_ventas(env, rows=[{"producto": f"prod{i:02d}", "total": i} for i in range(25)])

        await process_with_gemini(ORG_A, "ventas")

        assert re.search(r"muestra|primeras 10|10 de 25", system_prompt(gemini).lower())

    async def test_tabla_truncada_se_etiqueta_como_muestra_con_el_total_real(self, env, gemini):
        seed_ventas(env, rows=[{"producto": f"p{i}", "total": i} for i in range(1005)])

        await process_with_gemini(ORG_A, "ventas")

        prompt = system_prompt(gemini)
        assert "Datos de Ventas (MUESTRA de las primeras 10 de 1005 filas)" in prompt
        assert "- Ventas (ventas): 1005 filas" in prompt

    async def test_tabla_completa_no_se_etiqueta_como_muestra(self, env, gemini):
        seed_ventas(env)

        await process_with_gemini(ORG_A, "ventas")

        prompt = system_prompt(gemini)
        assert "Datos de Ventas (3 filas)" in prompt
        assert "Datos de Ventas (MUESTRA" not in prompt

    async def test_el_prompt_pide_no_afirmar_totales_sobre_una_muestra(self, env, gemini):
        seed_ventas(env)

        await process_with_gemini(ORG_A, "ventas")

        prompt = system_prompt(gemini)
        assert "MUESTRA" in prompt and "aproximado" in prompt and "NO afirmes totales" in prompt

    async def test_historial_usa_ultimos_6_y_mapea_roles(self, env, gemini):
        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(10)
        ]

        await process_with_gemini(ORG_A, "hola", history)

        sent = gemini.create.call_args.kwargs["history"]
        assert [(c.role, c.parts[0].text) for c in sent] == [
            ("user", "m4"), ("model", "m5"), ("user", "m6"), ("model", "m7"), ("user", "m8"), ("model", "m9"),
        ]

    async def test_sin_historial_envia_lista_vacia(self, env, gemini):
        await process_with_gemini(ORG_A, "hola", None)

        assert gemini.create.call_args.kwargs["history"] == []

    async def test_extrae_charts_y_los_quita_del_texto(self, env, gemini):
        chart = {"type": "bar", "title": "Ventas", "data": [{"name": "a", "value": 1}], "x": "name", "y": "value"}
        gemini.send.return_value = text_response(
            f"Aqui va:\n```chart\n{json.dumps(chart)}\n```\nFin."
        )

        result = await process_with_gemini(ORG_A, "grafico")

        assert result["charts"] == [chart]
        assert "```chart" not in result["text"]
        assert "Aqui va:" in result["text"] and "Fin." in result["text"]

    async def test_chart_con_json_invalido_se_descarta_sin_fallar(self, env, gemini):
        gemini.send.return_value = text_response("Texto\n```chart\n{no es json}\n```")

        result = await process_with_gemini(ORG_A, "grafico")

        assert result["charts"] == []
        assert result["text"] == "Texto"

    async def test_respuesta_que_es_solo_un_chart_devuelve_texto_vacio_y_el_chart(self, env, gemini):
        gemini.send.return_value = text_response('```chart\n{"type":"pie","data":[]}\n```')

        result = await process_with_gemini(ORG_A, "grafico")

        assert result["text"] == ""
        assert result["charts"] == [{"type": "pie", "data": []}]

    async def test_la_llamada_a_gemini_no_bloquea_el_event_loop(self, env, gemini):
        window: dict[str, float] = {}

        async def slow_send(_msg):
            window["start"] = time.monotonic()
            await asyncio.sleep(0.3)
            window["end"] = time.monotonic()
            return text_response("ok")

        gemini.send.side_effect = slow_send
        ticks: list[float] = []

        async def ticker():
            while True:
                ticks.append(time.monotonic())
                await asyncio.sleep(0.01)

        task = asyncio.create_task(ticker())
        await asyncio.sleep(0.05)
        try:
            await process_with_gemini(ORG_A, "hola")
        finally:
            task.cancel()

        assert sum(window["start"] < t < window["end"] for t in ticks) >= 5

    async def test_tres_llamadas_concurrentes_de_0_3s_tardan_lo_de_una_no_la_suma(self, env, gemini):
        async def slow_send(_msg):
            await asyncio.sleep(0.3)
            return text_response("ok")

        gemini.send.side_effect = slow_send

        started = time.monotonic()
        results = await asyncio.gather(*(process_with_gemini(ORG_A, f"pregunta {i}") for i in range(3)))
        elapsed = time.monotonic() - started

        assert [r["text"] for r in results] == ["ok"] * 3
        assert elapsed < 0.6, f"las llamadas se serializaron: {elapsed:.2f}s (esperado ~0.3s, secuencial ~0.9s)"


# ---------------------------------------------------------------------------
# process_with_gemini — Gemini falla
# ---------------------------------------------------------------------------

RAW = "RAWMARKER"


def _api_error(cls, code, status, message):
    return cls(code, {"error": {"code": code, "message": f"{message} {RAW}", "status": status}})


# (causa esperada, fabrica de la excepcion). Cada test crea su propia instancia.
CLIENT_FAILURES = {
    "cuota 429": ("quota", lambda: _api_error(genai_errors.ClientError, 429, "RESOURCE_EXHAUSTED", "Quota exceeded for metric")),
    "servicio 503": ("unavailable", lambda: _api_error(genai_errors.ServerError, 503, "UNAVAILABLE", "The model is overloaded")),
    "interno 500": ("unavailable", lambda: _api_error(genai_errors.ServerError, 500, "INTERNAL", "Internal error")),
    "deadline 504": ("timeout", lambda: _api_error(genai_errors.ServerError, 504, "DEADLINE_EXCEEDED", "Deadline expired")),
    "timeout httpx": ("timeout", lambda: httpx.ReadTimeout(f"read timed out {RAW}")),
    "timeout builtin": ("timeout", lambda: TimeoutError(f"timed out {RAW}")),
    "conexion rechazada": ("unavailable", lambda: ConnectionError(f"connection refused {RAW}")),
    "conexion httpx": ("unavailable", lambda: httpx.ConnectError(f"all connection attempts failed {RAW}")),
    "permiso 403": ("auth", lambda: _api_error(genai_errors.ClientError, 403, "PERMISSION_DENIED", "Method doesn't allow unregistered callers")),
    "clave invalida 400": ("auth", lambda: _api_error(genai_errors.ClientError, 400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key.")),
    "sin api key": ("auth", lambda: ValueError(f"No API key was provided. Please pass a valid API key. {RAW}")),
    "inesperada": ("unknown", lambda: RuntimeError(f"fallo interno con key={SECRET_KEY} {RAW}")),
}

# Fragmento (en minusculas) que identifica la causa en el texto para el usuario.
CAUSE_TEXT = {
    "quota": "cuota",
    "unavailable": "no está disponible",
    "timeout": "tardó",
    "auth": "configurad",
    "blocked": "bloque",
    "empty": "no devolvió",
    "truncated": "se cortó",
    "unknown": "error inesperado",
}

class TestGeminiFalla:
    @pytest.mark.parametrize("name", list(CLIENT_FAILURES))
    async def test_nunca_lanza_y_devuelve_el_contrato_de_siempre(self, env, gemini, name):
        gemini.send.side_effect = CLIENT_FAILURES[name][1]()

        result = await process_with_gemini(ORG_A, "hola")

        assert set(result) >= {"text", "charts", "actions"}
        assert result["charts"] == [] and result["actions"] == []
        assert isinstance(result["text"], str) and result["text"]

    @pytest.mark.parametrize("name", list(CLIENT_FAILURES))
    async def test_usuario_ve_mensaje_amable_con_la_causa_clasificada(self, env, gemini, name):
        kind, factory = CLIENT_FAILURES[name]
        gemini.send.side_effect = factory()

        result = await process_with_gemini(ORG_A, "hola")

        assert CAUSE_TEXT[kind] in result["text"].lower()
        assert result["fallback_reason"] == kind

    @pytest.mark.parametrize("name", list(CLIENT_FAILURES))
    async def test_usuario_no_ve_texto_crudo_de_la_excepcion_ni_la_clave(self, env, gemini, name):
        gemini.send.side_effect = CLIENT_FAILURES[name][1]()

        text = (await process_with_gemini(ORG_A, "hola"))["text"]

        for leaked in (RAW, SECRET_KEY, "Error con Gemini", "RESOURCE_EXHAUSTED", "Traceback", "Exception"):
            assert leaked not in text

    @pytest.mark.parametrize("name", list(CLIENT_FAILURES))
    async def test_el_error_real_queda_en_logs_sin_la_clave(self, env, gemini, caplog, name):
        gemini.send.side_effect = CLIENT_FAILURES[name][1]()

        with caplog.at_level(logging.DEBUG, logger=SERVICE_LOGGER):
            await process_with_gemini(ORG_A, "hola")

        records = [r for r in caplog.records if r.name == SERVICE_LOGGER and r.levelno >= logging.WARNING]
        assert records, "la falla de Gemini debe quedar registrada"
        assert RAW in caplog.text, "el detalle real debe estar en logs para diagnosticar"
        assert SECRET_KEY not in caplog.text

    @pytest.mark.parametrize("donde", ["constructor", "chats.create"])
    async def test_falla_al_crear_cliente_o_chat_tambien_cae_en_fallback(self, env, gemini, donde):
        exc = RuntimeError(f"fallo de inicializacion {RAW}")
        if donde == "constructor":
            gemini.ctor.side_effect = exc
        else:
            gemini.create.side_effect = exc

        result = await process_with_gemini(ORG_A, "hola")

        assert RAW not in result["text"]
        assert result["fallback_reason"] == "unknown"

    async def test_fallback_incluye_resumen_local_calculado_de_datos_reales(self, env, gemini):
        seed_ventas(env)  # total: 100 + 200 + 300
        gemini.send.side_effect = CLIENT_FAILURES["cuota 429"][1]()

        text = (await process_with_gemini(ORG_A, "ventas"))["text"]

        assert "Ventas" in text
        assert "3" in text                       # filas
        assert "600" in text                     # suma de total
        assert "200" in text                     # promedio de total
        assert "Martillo" in text                # fila de muestra real

    async def test_fallback_sin_datos_lo_dice_y_orienta_a_cargar_archivos(self, env, gemini):
        gemini.send.side_effect = CLIENT_FAILURES["servicio 503"][1]()

        text = (await process_with_gemini(ORG_A, "cuanto vendi?"))["text"].lower()

        assert "no está disponible" in text
        assert "no hay datos" in text
        assert "archivo" in text

    async def test_fallback_no_filtra_datos_de_otra_org(self, env, gemini):
        seed_ventas(env, ORG_A)
        env.dbs.db(ORG_B).add_table(
            "ventas", ["producto"], [{"producto": "SECRETO_DE_B"}], display_name="Ventas"
        )
        gemini.send.side_effect = CLIENT_FAILURES["cuota 429"][1]()

        text = (await process_with_gemini(ORG_A, "ventas"))["text"]

        assert "SECRETO_DE_B" not in text
        assert "Martillo" in text

    async def test_fallback_no_vuelve_a_llamar_a_gemini(self, env, gemini):
        gemini.send.side_effect = CLIENT_FAILURES["cuota 429"][1]()

        await process_with_gemini(ORG_A, "hola")

        assert gemini.send.call_count == 1  # sin reintentos: la API key es compartida y sensible al costo

    # -- respuesta vacia o bloqueada ------------------------------------------

    @staticmethod
    def _prompt_bloqueado():
        return genai_types.GenerateContentResponse(
            prompt_feedback=genai_types.GenerateContentResponsePromptFeedback(
                block_reason=genai_types.BlockedReason.SAFETY
            )
        )

    @staticmethod
    def _candidato_bloqueado(reason):
        return genai_types.GenerateContentResponse(
            candidates=[genai_types.Candidate(finish_reason=reason)]
        )

    @pytest.mark.parametrize(
        "kind, factory",
        [
            ("empty", lambda: text_response(None)),
            ("empty", lambda: text_response("")),
            ("empty", lambda: text_response("   \n ")),
            ("blocked", lambda: TestGeminiFalla._prompt_bloqueado()),
            ("blocked", lambda: TestGeminiFalla._candidato_bloqueado(genai_types.FinishReason.SAFETY)),
            ("blocked", lambda: TestGeminiFalla._candidato_bloqueado(genai_types.FinishReason.PROHIBITED_CONTENT)),
            ("truncated", lambda: TestGeminiFalla._candidato_bloqueado(genai_types.FinishReason.MAX_TOKENS)),
        ],
        ids=[
            "sin-candidatos", "texto-vacio", "solo-espacios", "prompt-bloqueado",
            "finish-safety", "finish-prohibido", "finish-max-tokens",
        ],
    )
    async def test_respuesta_vacia_o_bloqueada_da_mensaje_amable_con_causa(self, env, gemini, kind, factory):
        seed_ventas(env)
        gemini.send.return_value = factory()

        result = await process_with_gemini(ORG_A, "ventas")

        assert CAUSE_TEXT[kind] in result["text"].lower()
        assert result["fallback_reason"] == kind
        assert "Ventas" in result["text"]  # sigue ofreciendo el resumen local

    async def test_respuesta_vacia_nunca_devuelve_texto_en_blanco(self, env, gemini):
        gemini.send.return_value = text_response("   ")

        text = (await process_with_gemini(ORG_A, "hola"))["text"]

        assert text.strip()

    async def test_respuesta_normal_no_activa_el_fallback(self, env, gemini):
        result = await process_with_gemini(ORG_A, "hola")

        assert "fallback_reason" not in result


# ---------------------------------------------------------------------------
# Timeout duro, clasificacion robusta y fallback acotado
# ---------------------------------------------------------------------------

class TestTimeout:
    async def test_llamada_colgada_cae_en_timeout_antes_de_que_pase_mucho_tiempo(self, env, gemini, _settings):
        _settings.GEMINI_TIMEOUT_SECONDS = 0.05

        async def hang(_msg):
            await asyncio.sleep(30)

        gemini.send.side_effect = hang

        started = time.monotonic()
        result = await process_with_gemini(ORG_A, "hola")

        assert time.monotonic() - started < 2
        assert result["fallback_reason"] == "timeout"
        assert "tardó" in result["text"]
        gemini.aclose.assert_awaited_once()


class TestClasificacion:
    def test_valueerror_de_api_key_faltante_es_auth(self):
        exc = ValueError("No API key was provided. Please pass a valid API key. Learn how to create...")
        assert _classify_gemini_failure(exc) == "auth"

    def test_valueerror_cualquiera_sigue_siendo_unknown(self):
        assert _classify_gemini_failure(ValueError("otra cosa")) == "unknown"

    def test_la_clasificacion_nunca_lanza(self):
        class Raro(genai_errors.APIError):
            @property
            def code(self):
                raise RuntimeError("roto")

            @code.setter
            def code(self, _v):
                pass

        exc = Raro.__new__(Raro)  # sin __init__: atributos faltantes
        assert _classify_gemini_failure(exc) == "unknown"

    async def test_si_el_clasificador_falla_el_usuario_igual_recibe_fallback_unknown(self, env, gemini):
        gemini.send.side_effect = RuntimeError("boom")

        with patch("app.services.agent_tools_service._classify", side_effect=RuntimeError("bug en clasificador")):
            result = await process_with_gemini(ORG_A, "hola")

        assert result["fallback_reason"] == "unknown"
        assert "error inesperado" in result["text"]

    async def test_excepcion_cuyo_str_lanza_no_rompe_el_manejador(self, env, gemini):
        class StrRoto(Exception):
            def __str__(self):
                raise RuntimeError("str roto")

        gemini.send.side_effect = StrRoto()

        result = await process_with_gemini(ORG_A, "hola")

        assert result["fallback_reason"] == "unknown"


class TestFormatoNumerico:
    @pytest.mark.parametrize(
        "value, expected",
        [
            (3.0, 3),
            (2.456, 2.46),
            (-7.0, -7),
            (float("inf"), "no calculable"),
            (float("-inf"), "no calculable"),
            (float("nan"), "no calculable"),
            (1e15, "1.000e+15"),
            (-2.5e300, "-2.500e+300"),
        ],
    )
    def test_fmt_number(self, value, expected):
        assert _fmt_number(value) == expected

    async def test_suma_que_desborda_a_infinito_no_provoca_500(self, env, gemini):
        seed_ventas(env, rows=[{"producto": "A", "total": 1.7e308}, {"producto": "B", "total": 1.7e308}])
        gemini.send.side_effect = CLIENT_FAILURES["cuota 429"][1]()

        result = await process_with_gemini(ORG_A, "ventas")

        assert result["fallback_reason"] == "quota"
        assert "no calculable" in result["text"]

    async def test_enteros_gigantes_no_se_imprimen_completos_ni_rompen(self, env, gemini):
        seed_ventas(env, rows=[{"producto": "A", "total": 10**400}, {"producto": "B", "total": 5}])
        gemini.send.side_effect = CLIENT_FAILURES["cuota 429"][1]()

        result = await process_with_gemini(ORG_A, "ventas")

        assert "total: suma 5," in result["text"]   # el 10**400 (no convertible a float) se ignora
        assert len(result["text"]) < 3000

    async def test_booleanos_no_cuentan_como_numeros(self, env, gemini):
        seed_ventas(env, rows=[{"producto": "A", "total": True}, {"producto": "B", "total": False},
                               {"producto": "C", "total": 5}])
        gemini.send.side_effect = CLIENT_FAILURES["cuota 429"][1]()

        text = (await process_with_gemini(ORG_A, "ventas"))["text"]

        assert "suma 5, promedio 5, mínimo 5, máximo 5" in text


class TestCeldasDelFallback:
    def test_clean_cell_recorta_y_normaliza(self):
        assert _clean_cell("a\nb\r\tc\x00d") == "a b c d"
        assert _clean_cell("x" * 500) == "x" * 80 + "…"
        assert _clean_cell(12) == "12"

    async def test_celda_de_1mb_no_infla_el_texto_persistido(self, env, gemini):
        seed_ventas(env, rows=[{"producto": "X" * 1_000_000, "total": 1}])
        gemini.send.side_effect = CLIENT_FAILURES["cuota 429"][1]()

        text = (await process_with_gemini(ORG_A, "ventas"))["text"]

        assert len(text) < 2000
        assert "X" * 81 not in text and "…" in text

    async def test_saltos_de_linea_en_celdas_no_pueden_inyectar_markdown(self, env, gemini):
        seed_ventas(env, rows=[{"producto": "ok\n\n# TITULO FALSO\n- item\u2028otro\x1b[31m", "total": 1}])
        gemini.send.side_effect = CLIENT_FAILURES["cuota 429"][1]()

        text = (await process_with_gemini(ORG_A, "ventas"))["text"]

        assert "TITULO FALSO" in text            # el contenido se conserva
        assert "\n# TITULO" not in text and "\n- item" not in text
        assert "\u2028" not in text and "\x1b" not in text
