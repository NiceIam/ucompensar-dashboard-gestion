#!/usr/bin/env python
"""Validacion de TABLEROS CREADOS POR LA IA contra Gemini REAL, con TOPES DE GASTO impuestos por codigo.

Reutiliza la guardia de gasto de `chat_smoke_real_gemini.py` (mismo contador, mismo bloqueo de red, mismo Postgres
desechable) y la extiende a `generate_content` (la sugerencia de tableros no usa chat). Ejecutar SIEMPRE desde
`backend/` con el venv del proyecto. Vive fuera de `tests/` y su nombre no empieza por `test_`: pytest no lo recoge.

Topes (todos abortan la corrida, limpian y salen con codigo != 0)
- Tope DURO de llamadas a Gemini en TODA la corrida (--max-calls, default 20; > 20 exige --i-know-this-spends-money;
  el maximo absoluto es 40). La llamada N+1 se rechaza ANTES de enviarse.
- Solo el host generativelanguage.googleapis.com; maximo 1 peticion HTTP por llamada logica (un reintento oculto del
  SDK aborta antes de enviarse); el SDK queda con attempts=1.
- PARADA INMEDIATA ante el primer error HTTP 4xx (incluido 400 "API key not valid" y 429): se registra sin la clave
  y se detiene todo. Cualquier otra excepcion tambien aborta.
- La clave se lee SOLO via app.config.get_settings() (entorno o .env; el script no abre ningun .env) y nunca se
  imprime: toda salida pasa por un redactor.
- Postgres desechable propio (127.0.0.1, puerto libre); nunca Neon ni el servicio instalado. Se detiene y se borra
  siempre; al final se verifica que no queden procesos.

Que valida (una org con ventas 40 filas + productos 30 filas de test-data/ferreteria y clientes sintetico)
  5  sugerencia automatica (1 llamada con generate_content, org sin tableros)
  1  "creame un tablero de ventas por mes y por producto"       -> debe llamar create_dashboard
  2  "quiero ver como van mis clientes"                          -> intencion sin la palabra tablero
  3  "quiero un tablero"                                         -> peticion ambigua (¿pregunta o inventa?)
  4  "cuanto vendi en total"                                     -> GATING: la herramienta NO debe declararse
  6  repetir el pedido 1                                         -> idempotencia (mismo tablero)
Orden de ejecucion fijo: 5, 1, 2, 3, 4, 6 (la sugerencia automatica solo corre si no hay tableros).
Llamadas esperadas: 1 + 2-3 + 2-3 + 1-2 + 2 + 2-3 = ~12-14.

Codigos de salida: 0 ok | 2 error HTTP 4xx | 3 tope de llamadas/HTTP | 4 otro error o timeout | 5 configuracion/
argumentos/clave | 6 infraestructura (Postgres) | 7 red no permitida o fallo de limpieza.

Ejemplos (desde backend/, con el venv del proyecto):
  # en seco (sin red ni clave; SDK real sobre un transporte falso con --dry-run-http):
  python scripts/dashboards_smoke_real_gemini.py --dry-run --dry-run-http --workdir <dir> --out <dir>/dash_smoke.json
  # topes en seco: --dry-run-mode overbudget | error429 | error400 | error503 | unexpected | timeout
  # real (gasta hasta --max-calls llamadas de la API key compartida; GOOGLE_API_KEY y APP_SECRET_KEY por entorno
  # o en backend/.env; el script no lee .env por su cuenta):
  python scripts/dashboards_smoke_real_gemini.py --workdir <dir> --out <dir>/dash_smoke_real.json --max-calls 20
  # solo un escenario:  --scenarios 1,4
  # costo proyectado por pedido: --price-in <USD por 1M tokens de entrada> --price-out <USD por 1M de salida>
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import csv
import datetime
import json
import random
import sys
import tempfile
import time
from collections import deque
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import chat_smoke_real_gemini as base  # noqa: E402  (hace os.chdir(backend) y deja `tests` importable)
from chat_smoke_real_gemini import (  # noqa: E402
    CallGuard, DisposablePostgres, NetworkBlocked, Patches, RunAborted, say,
    EXIT_BLOCKED, EXIT_CONFIG, EXIT_ERROR, EXIT_INFRA, EXIT_OK,
)

HARD_MAX_CALLS = 20
ABSOLUTE_MAX_CALLS = 40
ORG_ID = base.ORG_ID
FERRETERIA = Path(__file__).resolve().parents[2] / "test-data" / "ferreteria"
RUN_ORDER = [5, 1, 2, 3, 4, 6]
SCENARIOS = {
    1: "creame un tablero de ventas por mes y por producto",
    2: "quiero ver como van mis clientes",
    3: "quiero un tablero",
    4: "cuanto vendi en total",
    5: "(sugerencia automatica al terminar la carga)",
    6: "creame un tablero de ventas por mes y por producto",
}
VENTAS_TYPES = {"fecha": "date", "cantidad": "integer", "precio_unitario": "number", "total": "number"}
PRODUCTOS_TYPES = {"precio_compra": "number", "precio_venta": "number", "stock": "integer"}
CLIENTES_COLUMNS = {"nombre": "text", "ciudad": "text", "tipo": "text", "fecha_registro": "date", "compras": "integer"}


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------

def _cast(value: str, kind: str):
    if value == "":
        return None
    if kind == "integer":
        return int(value)
    if kind == "number":
        number = float(value)
        return int(number) if number == int(number) else number
    return value


def read_csv(path: Path, types: dict) -> tuple[dict, list[dict]]:
    with open(path, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = {c: types.get(c, "text") for c in (reader.fieldnames or [])}
        rows = [{c: _cast(r[c], types.get(c, "text")) for c in columns} for r in reader]
    return columns, rows


def build_seed() -> tuple[dict, dict]:
    """({tabla: (columnas, filas)}, esperado). Los esperados salen del modulo csv, sin el motor."""
    ventas = read_csv(FERRETERIA / "ventas.csv", VENTAS_TYPES)
    productos = read_csv(FERRETERIA / "productos.csv", PRODUCTOS_TYPES)
    rnd = random.Random(20261016)
    ciudades = ["Bogota", "Medellin", "Cali", "Barranquilla", "Bucaramanga"]
    tipos = ["minorista", "constructora", "contratista"]
    clientes = [
        {"nombre": f"Cliente {i:03d}", "ciudad": rnd.choice(ciudades), "tipo": rnd.choice(tipos),
         "fecha_registro": f"2025-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}", "compras": rnd.randint(1, 30)}
        for i in range(60)
    ]
    by_month: dict[str, int] = {}
    by_product: dict[str, int] = {}
    for row in ventas[1]:
        by_month[row["fecha"][:7]] = by_month.get(row["fecha"][:7], 0) + row["total"]
        by_product[row["producto"]] = by_product.get(row["producto"], 0) + row["total"]
    expected = {
        "ventas_rows": len(ventas[1]), "ventas_total": sum(r["total"] for r in ventas[1]),
        "sum_by_month": dict(sorted(by_month.items())),
        "top_product": max(by_product.items(), key=lambda kv: kv[1]),
        "clientes_rows": len(clientes),
    }
    return {"ventas": ventas, "productos": productos, "clientes": (CLIENTES_COLUMNS, clientes)}, expected


async def create_org_database(port: int, tables: dict):
    import asyncpg
    from app import database

    admin = await asyncpg.connect(host="127.0.0.1", port=port, user=base.PG_USER, database="postgres")
    try:
        await admin.execute('CREATE DATABASE "dash_smoke_org"')
    finally:
        await admin.close()
    pool = await asyncpg.create_pool(host="127.0.0.1", port=port, user=base.PG_USER, database="dash_smoke_org",
                                     min_size=1, max_size=8)
    async with pool.acquire() as conn:
        await conn.execute(database.ORG_BASE_SCHEMA_SQL)
        for name, (columns, rows) in tables.items():
            table_id = await conn.fetchval(
                "INSERT INTO org_data_tables (table_name, display_name, columns_definition, row_count) "
                "VALUES ($1, $2, $3::jsonb, $4) RETURNING id",
                name, name.title(), json.dumps([{"name": c, "type": t} for c, t in columns.items()]), len(rows),
            )
            await conn.executemany(
                "INSERT INTO org_data_rows (table_id, data) VALUES ($1, $2::jsonb)",
                [(table_id, json.dumps(r, ensure_ascii=False)) for r in rows],
            )
    from app.services.schema_agent_service import backfill_date_ranges
    await backfill_date_ranges(ORG_ID, dry_run=False, pool=pool)     # rango de fechas por columna, como una carga real
    return pool


# ---------------------------------------------------------------------------
# Guardia extendida: generate_content (sugerencias)
# ---------------------------------------------------------------------------

def install_models_guard(guard: CallGuard, patches: Patches) -> None:
    from google.genai import models

    original = models.AsyncModels.generate_content

    async def guarded_generate_content(self, *, model, contents, config=None):
        return await guard.call(lambda: original(self, model=model, contents=contents, config=config))

    patches.setattr(models.AsyncModels, "generate_content", guarded_generate_content)


# ---------------------------------------------------------------------------
# Cliente falso del dry-run
# ---------------------------------------------------------------------------

GOOD_SUGGEST = {"dashboards": [
    {"title": "Ventas del periodo", "widgets": [
        {"table": "ventas", "chart_type": "kpi", "y": "sum(total)"},
        {"table": "ventas", "chart_type": "line", "x": "month(fecha)", "y": "sum(total)"},
        {"table": "ventas", "chart_type": "bar", "x": "producto", "y": "sum(total)", "top": 5},
        {"table": "ventas", "chart_type": "pie", "x": "metodo_pago", "y": "sum(total)"}]},
    {"title": "Clientes", "widgets": [
        {"table": "clientes", "chart_type": "kpi", "y": "count"},
        {"table": "clientes", "chart_type": "bar", "x": "ciudad", "y": "count"},
        {"table": "clientes", "chart_type": "pie", "x": "tipo", "y": "count"}]},
]}
VENTAS_BOARD = [
    {"table": "ventas", "chart_type": "kpi", "y": "sum(total)"},
    {"table": "ventas", "chart_type": "line", "x": "month(fecha)", "y": "sum(total)"},
    {"table": "ventas", "chart_type": "bar", "x": "producto", "y": "sum(total)", "top": 10},
    {"table": "ventas", "chart_type": "pie", "x": "metodo_pago", "y": "sum(total)"},
]
CLIENTES_BOARD = [
    {"table": "clientes", "chart_type": "kpi", "y": "count"},
    {"table": "clientes", "chart_type": "bar", "x": "ciudad", "y": "count"},
    {"table": "clientes", "chart_type": "line", "x": "month(fecha_registro)", "y": "count"},
]


class DryScript:
    MODES = ("normal", "overbudget", "error429", "error400", "error503", "unexpected", "timeout")

    def __init__(self, mode: str, fail_at: int):
        self.mode, self.fail_at = mode, fail_at
        self.inner_calls = 0
        self.queue: deque = deque()
        self.requests: list[dict] = []

    def load(self, sc_id: int) -> None:
        from tests import fake_gemini as fg

        u = fg.usage
        if self.mode == "overbudget":
            self.queue = deque([lambda m: fg.text_response("x", u(500, 10, 0))] * 4)
            return
        steps = {
            5: [lambda m: fg.text_response(json.dumps(GOOD_SUGGEST), u(1100, 330, 25))],
            1: [lambda m: fg.call_response(("create_dashboard", {"title": "Ventas por mes y por producto", "widgets": VENTAS_BOARD}, "c1"), usage_metadata=u(1900, 190, 30)),
                lambda m: fg.text_response("Listo, creé tu tablero.", u(2000, 25, 0))],
            2: [lambda m: fg.call_response(("create_dashboard", {"title": "Cómo van mis clientes", "widgets": CLIENTES_BOARD}, "c1"), usage_metadata=u(1900, 150, 30)),
                lambda m: fg.text_response("Listo, ahí está.", u(2000, 25, 0))],
            3: [lambda m: fg.text_response("¿De qué hoja quieres el tablero y qué quieres medir?", u(1800, 20, 10))],
            4: [lambda m: fg.call_response(("query_table", {"table": "ventas", "aggregates": ["sum(total)"]}, "c1"), usage_metadata=u(1300, 30, 0)),
                lambda m: fg.text_response("Vendiste en total 10.234.700.", u(1400, 20, 0))],
            6: [lambda m: fg.call_response(("create_dashboard", {"title": "Ventas por mes y por producto", "widgets": VENTAS_BOARD}, "c1"), usage_metadata=u(1900, 190, 30)),
                lambda m: fg.text_response("Ese tablero ya existía.", u(2000, 25, 0))],
        }[sc_id]
        self.queue = deque(steps)

    async def http_handler(self, request):
        import httpx

        self.inner_calls += 1
        body = json.loads(request.content or b"{}")
        gen = body.get("generationConfig") or {}
        self.requests.append({
            "path": request.url.path.rsplit("/", 1)[-1], "host": request.url.host,
            "tools": sum(len(t.get("functionDeclarations") or []) for t in body.get("tools") or []),
            "thinkingConfig": gen.get("thinkingConfig"), "maxOutputTokens": gen.get("maxOutputTokens"),
            "responseMimeType": gen.get("responseMimeType"),
            "systemInstruction_chars": len(json.dumps(body.get("systemInstruction") or {}, ensure_ascii=False)),
            "has_api_key_header": "x-goog-api-key" in request.headers,
        })
        codes = {"error429": (429, "RESOURCE_EXHAUSTED"), "error400": (400, "INVALID_ARGUMENT"),
                 "error503": (503, "UNAVAILABLE")}
        if self.mode in codes and self.inner_calls == self.fail_at:
            code, status = codes[self.mode]
            return httpx.Response(code, json={"error": {"code": code, "message": "error simulado", "status": status}})
        if self.mode == "unexpected" and self.inner_calls == self.fail_at:
            raise RuntimeError("fallo inesperado simulado en el transporte")
        if self.mode == "timeout" and self.inner_calls == self.fail_at:
            await asyncio.sleep(60)
        if not self.queue:
            raise RuntimeError("guion del dry-run agotado")
        response = self.queue.popleft()(None)
        return httpx.Response(200, json=response.model_dump(mode="json", by_alias=True, exclude_none=True))

    async def inner(self, *args, **kwargs):
        from google.genai import errors as genai_errors

        self.inner_calls += 1
        if self.mode == "timeout" and self.inner_calls == self.fail_at:
            await asyncio.sleep(60)
        if self.mode not in ("normal", "overbudget", "timeout") and self.inner_calls == self.fail_at:
            if self.mode == "error429":
                raise genai_errors.ClientError(429, {"error": {"code": 429, "message": "cuota simulada", "status": "RESOURCE_EXHAUSTED"}})
            if self.mode == "error400":
                raise genai_errors.ClientError(400, {"error": {"code": 400, "message": "API key not valid (simulado)", "status": "INVALID_ARGUMENT"}})
            if self.mode == "error503":
                raise genai_errors.ServerError(503, {"error": {"code": 503, "message": "no disponible simulado", "status": "UNAVAILABLE"}})
            raise RuntimeError("fallo inesperado simulado")
        if not self.queue:
            raise RuntimeError("guion del dry-run agotado")
        return self.queue.popleft()(None)


# ---------------------------------------------------------------------------
# Escenarios
# ---------------------------------------------------------------------------

def _board_check(rendered: dict, expected: dict) -> dict:
    """Comprueba un tablero ya calculado con el motor contra los esperados A MANO (sin Gemini)."""
    errors = [c["error"] for c in rendered["charts"] if c.get("error")] + [k["error"] for k in rendered["kpis"] if k.get("error")]
    kpi_values = {k["label"]: k["value"] for k in rendered["kpis"] if not k.get("error")}
    month_chart = next((c for c in rendered["charts"] if c["type"] == "line"), None)
    return {
        "widgets_rendered": len(rendered["charts"]) + len(rendered["kpis"]),
        "widget_errors": errors,
        "has_total_kpi_ok": expected["ventas_total"] in kpi_values.values(),
        "month_series_ok": bool(month_chart) and {p["name"]: p["value"] for p in month_chart["data"]} == expected["sum_by_month"],
        "empty_charts": [c["title"] for c in rendered["charts"] if not c.get("error") and not c["data"]],
    }


async def run_scenario(runner, sc_id: int, dry: DryScript | None) -> dict:
    from app.services import agent_tools_service as ats
    from app.services import dashboard_suggest_service as suggest_service
    from app.services.dashboard_render_service import render_dashboard

    guard = runner.guard
    guard.scenario = sc_id
    calls_before, http_before = guard.calls, guard.http_calls
    if dry:
        dry.load(sc_id)
    say(f"\n=== Escenario {sc_id}: {SCENARIOS[sc_id]!r} ===")
    started = time.monotonic()
    entry: dict = {"id": sc_id, "prompt": SCENARIOS[sc_id]}
    declared: list[bool] = []
    original_declarations = ats._tool_declarations

    def recording_declarations(with_dashboard=False):
        declared.append(bool(with_dashboard))
        return original_declarations(with_dashboard)

    scenario_settings = runner.settings.model_copy(update={"CHAT_MAX_TOOL_ROUNDS": 3})
    timeout = float(scenario_settings.GEMINI_TIMEOUT_SECONDS) + 15.0
    result: dict = {}
    try:
        with patch.object(ats, "get_settings", return_value=scenario_settings), \
                patch.object(ats, "_tool_declarations", recording_declarations):
            if sc_id == 5:
                result = await asyncio.wait_for(suggest_service.suggest(ORG_ID, auto=True), timeout=timeout)
            else:
                result = await asyncio.wait_for(ats.process_with_gemini(ORG_ID, SCENARIOS[sc_id], []), timeout=timeout)
    finally:
        entry["latency_ms"] = int((time.monotonic() - started) * 1000)
        entry["calls_used"] = guard.calls - calls_before
        entry["http_requests"] = guard.http_calls - http_before
        entry["gemini_calls"] = [r for r in guard.records if r["scenario"] == sc_id]
        entry["tools_called"] = [{"call": i + 1, **fc} for i, r in enumerate(entry["gemini_calls"]) for fc in r["function_calls"]]

    usage = result.get("usage") or {}
    boards = result.get("dashboards") or []
    if sc_id == 5:
        usage = {"prompt_tokens": (result.get("tokens") or {}).get("prompt", 0),
                 "output_tokens": (result.get("tokens") or {}).get("output", 0),
                 "thoughts_tokens": (result.get("tokens") or {}).get("thoughts", 0),
                 "total_tokens": (result.get("tokens") or {}).get("total", 0), "model_calls": entry["calls_used"]}
    entry["usage"] = {k: usage.get(k, 0) for k in ("model_calls", "prompt_tokens", "output_tokens", "thoughts_tokens", "total_tokens")}
    entry["text"] = (result.get("text") or "")[:600]
    entry["fallback_reason"] = result.get("fallback_reason")
    entry["dashboards_created"] = [{"name": b.get("name"), "widgets": b.get("widgets"), "existing": b.get("existing")} for b in boards]
    entry["dashboard_tool_declared"] = any(declared)
    entry["status"] = result.get("status")
    entry["source"] = result.get("source")

    checks = []
    for board in boards:
        if board.get("id"):
            rendered = await render_dashboard(ORG_ID, board["id"])
            checks.append({"name": board["name"], **_board_check(rendered, runner.expected)})
    entry["rendered_checks"] = checks
    expected_flags = {}
    if sc_id == 1:
        expected_flags = {"creo_un_tablero": len(boards) == 1 and not boards[0].get("existing"),
                          "llamo_create_dashboard": any(t["name"] == "create_dashboard" for t in entry["tools_called"]),
                          "sin_errores_en_widgets": all(not c["widget_errors"] and not c["empty_charts"] for c in checks) and bool(checks),
                          "total_correcto": any(c["has_total_kpi_ok"] for c in checks),
                          "serie_mensual_correcta": any(c["month_series_ok"] for c in checks),
                          "entrada_<=4000": entry["usage"]["prompt_tokens"] <= 4000,
                          "salida_<=600": entry["usage"]["output_tokens"] <= 600}
    elif sc_id == 2:
        expected_flags = {"declaro_la_herramienta": entry["dashboard_tool_declared"],
                          "creo_un_tablero": len(boards) == 1, "sin_errores_en_widgets": all(not c["widget_errors"] and not c["empty_charts"] for c in checks) and bool(checks)}
    elif sc_id == 3:
        expected_flags = {"pregunto_en_vez_de_inventar": not boards and (entry["text"].strip().endswith("?") or "?" in entry["text"]),
                          "creo_algo": bool(boards)}
    elif sc_id == 4:
        expected_flags = {"NO_declaro_la_herramienta": not entry["dashboard_tool_declared"],
                          "no_llamo_create_dashboard": not any(t["name"] == "create_dashboard" for t in entry["tools_called"]),
                          "no_creo_tableros": not boards}
    elif sc_id == 5:
        expected_flags = {"creo_tableros": result.get("status") == "created", "fuente_ia": result.get("source") == "ai",
                          "una_sola_llamada": entry["calls_used"] == 1,
                          "sin_errores_en_widgets": all(not c["widget_errors"] and not c["empty_charts"] for c in checks) and bool(checks)}
        entry["dashboards_created"] = [{"name": b.get("name"), "widgets": b.get("widgets")} for b in result.get("dashboards") or []]
    elif sc_id == 6:
        expected_flags = {"mismo_tablero_ya_existia": bool(boards) and all(b.get("existing") for b in boards)}
    entry["expected_flags"] = expected_flags
    return entry


class Runner:
    def __init__(self, args, settings, guard: CallGuard, expected: dict):
        self.args, self.settings, self.guard, self.expected = args, settings, guard, expected
        self.results: list[dict] = []
        self.aborted: dict | None = None

    def totals(self) -> dict:
        tot = {"gemini_calls": self.guard.calls, "http_requests": self.guard.http_calls,
               "prompt_tokens": 0, "output_tokens": 0, "thoughts_tokens": 0, "cached_tokens": 0, "total_tokens": 0}
        for rec in self.guard.records:
            for key in ("prompt_tokens", "output_tokens", "thoughts_tokens", "cached_tokens", "total_tokens"):
                tot[key] += (rec.get("usage") or {}).get(key, 0)
        return tot

    def cost(self) -> dict | None:
        if self.args.price_in is None or self.args.price_out is None:
            return None
        t = self.totals()
        usd = (t["prompt_tokens"] * self.args.price_in + (t["output_tokens"] + t["thoughts_tokens"]) * self.args.price_out) / 1e6
        creations = [r for r in self.results if r["id"] in (1, 2)]
        per_request = None
        if creations:
            u = [(r["usage"]["prompt_tokens"] * self.args.price_in + (r["usage"]["output_tokens"] + r["usage"]["thoughts_tokens"]) * self.args.price_out) / 1e6 for r in creations]
            per_request = sum(u) / len(u)
        return {"total_usd": round(usd, 6), "avg_usd_per_dashboard_request": None if per_request is None else round(per_request, 6)}

    def write(self, out: Path, extra: dict | None = None) -> None:
        dry = getattr(self, "dry", None)
        payload = {
            "meta": {"mode": "dry-run" if self.args.dry_run else "REAL", "model": self.settings.GEMINI_MODEL,
                     "max_calls": self.guard.max_calls, "api_key_present": bool(self.settings.GOOGLE_API_KEY),
                     "sdk_retries": "desactivados (attempts=1)",
                     "started_at": datetime.datetime.now().isoformat(timespec="seconds")},
            "seed_expected": self.expected, "scenarios": self.results, "totals": self.totals(), "cost": self.cost(),
            "aborted": self.aborted,
            **({"mock_http_requests": dry.requests} if dry is not None and dry.requests else {}), **(extra or {}),
        }
        with contextlib.suppress(Exception):
            out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(base.redact(json.dumps(payload, ensure_ascii=False, indent=2, default=str)), encoding="utf-8")


def print_scenario(entry: dict) -> None:
    u = entry["usage"]
    say(f"  llamadas={entry['calls_used']} http={entry['http_requests']} latencia={entry['latency_ms']} ms fallback={entry['fallback_reason']}")
    say("  herramientas: " + (", ".join(f"{t['name']}({json.dumps(t['args'], ensure_ascii=False)[:140]})" for t in entry["tools_called"]) or "(ninguna)"))
    say(f"  tokens: entrada={u['prompt_tokens']} salida={u['output_tokens']} razonamiento={u['thoughts_tokens']} total={u['total_tokens']}")
    say(f"  tablero declarado={entry['dashboard_tool_declared']} creados={json.dumps(entry['dashboards_created'], ensure_ascii=False)}")
    say(f"  banderas: {json.dumps(entry['expected_flags'], ensure_ascii=False)}")
    if entry["text"]:
        say("  texto: " + entry["text"].replace("\n", "\n         "))


async def run_all(args, settings, pg_port: int, out: Path):
    from tests.fake_org_db import FakeMainPool
    from app.services import agent_tools_service as ats
    from app.services import dashboard_builder_service as builder
    from app.services import dashboard_render_service as render
    from app.services import dashboard_service as dsv
    from app.services import dashboard_suggest_service as suggest_service

    tables, expected = build_seed()
    guard = CallGuard(args.max_calls)
    runner = Runner(args, settings, guard, expected)
    pool = await create_org_database(pg_port, tables)
    patches = Patches()
    dry: DryScript | None = None
    exit_code = EXIT_OK
    suggest_service.reset_caches()
    try:
        main_pool = FakeMainPool()
        main_pool.orgs[ORG_ID] = {"name": "Ferreteria Demo", "sector": "comercio", "city": "Bogota"}

        async def get_pool(_org_id):
            return pool

        base.install_http_guard(guard, patches)
        install_models_guard(guard, patches)
        if args.dry_run:
            dry = DryScript(args.dry_run_mode, args.dry_run_fail_at)
            runner.dry = dry  # type: ignore[attr-defined]
        if args.dry_run and args.dry_run_http:
            import httpx

            # AsyncChat.send_message llama internamente a AsyncModels.generate_content: con la guardia en ESE punto se
            # cuentan igual los mensajes del chat y las sugerencias, y cada llamada se cuenta UNA sola vez.
            base.install_client_factory(patches, expect_key=base.DRY_RUN_KEY, transport=httpx.MockTransport(dry.http_handler))
        elif args.dry_run:
            from google import genai
            from unittest.mock import AsyncMock
            from tests import fake_gemini as fg

            fake = fg.make_fake_genai()

            async def guarded_send(message, config=None):
                return await guard.call(lambda: dry.inner(message, config))

            async def guarded_generate(*a, **k):
                return await guard.call(lambda: dry.inner(*a, **k))

            fake.send.side_effect = guarded_send
            fake.client.aio.models.generate_content = AsyncMock(side_effect=guarded_generate)

            def fake_client_factory(*a, **k):
                if k.get("api_key") != base.DRY_RUN_KEY:
                    raise NetworkBlocked("DRY-RUN: el cliente falso recibio una clave que no es la de prueba")
                return fake.client

            patches.setattr(genai, "Client", fake_client_factory)
        else:
            base.install_client_factory(patches)

        scoped = [
            patch.object(ats, "get_org_pool", get_pool), patch.object(ats, "get_main_pool", main_pool.get_main_pool),
            patch.object(dsv, "get_org_pool", get_pool), patch.object(render, "get_org_pool", get_pool),
            patch.object(suggest_service, "get_org_pool", get_pool),
            patch.object(suggest_service, "get_settings", return_value=settings),
            patch.object(builder, "get_settings", return_value=settings),
            patch.object(render, "get_settings", return_value=settings),
        ]
        for p in scoped:
            p.start()
        try:
            for sc_id in [i for i in RUN_ORDER if i in args.scenarios_list]:
                try:
                    entry = await run_scenario(runner, sc_id, dry)
                except RunAborted as exc:
                    runner.aborted = {"scenario": sc_id, "kind": exc.kind, "exit_code": exc.exit_code, "detail": exc.detail}
                    exit_code = exc.exit_code
                    say(f"\n!!! ABORTADO en el escenario {sc_id} ({exc.kind}): {exc.detail}")
                    break
                except asyncio.TimeoutError:
                    runner.aborted = {"scenario": sc_id, "kind": "timeout", "exit_code": EXIT_ERROR, "detail": "el watchdog del escenario expiro"}
                    exit_code = EXIT_ERROR
                    say(f"\n!!! ABORTADO: timeout total del escenario {sc_id}")
                    break
                except Exception as exc:
                    runner.aborted = {"scenario": sc_id, "kind": "unexpected", "exit_code": EXIT_ERROR,
                                      "detail": base.redact(f"{type(exc).__name__}: {exc}")[:300]}
                    exit_code = EXIT_ERROR
                    say(f"\n!!! ABORTADO por excepcion inesperada: {runner.aborted['detail']}")
                    break
                runner.results.append(entry)
                print_scenario(entry)
                runner.write(out)
                if entry["fallback_reason"] in ("auth", "quota", "unavailable", "timeout", "unknown"):
                    runner.aborted = {"scenario": sc_id, "kind": "fallback", "exit_code": EXIT_ERROR,
                                      "detail": f"la app cayo al fallback ({entry['fallback_reason']}); no se continua"}
                    exit_code = EXIT_ERROR
                    say(f"\n!!! ABORTADO: fallback_reason={entry['fallback_reason']}")
                    break
        finally:
            for p in reversed(scoped):
                p.stop()
    finally:
        patches.close()
        with contextlib.suppress(Exception):
            await pool.close()
    runner.dry = dry  # type: ignore[attr-defined]
    return exit_code, runner


def parse_args(argv=None):
    class _Parser(argparse.ArgumentParser):
        def error(self, message):
            self.print_usage(sys.stderr)
            self.exit(EXIT_CONFIG, f"{self.prog}: error: {message}\n")

    p = _Parser(description="Validacion de tableros creados por la IA con Gemini real y topes de gasto por codigo.")
    p.add_argument("--dry-run", action="store_true", help="cliente falso, sin red ni clave")
    p.add_argument("--dry-run-mode", choices=DryScript.MODES, default="normal")
    p.add_argument("--dry-run-http", action="store_true", help="solo con --dry-run: SDK REAL sobre un transporte httpx falso")
    p.add_argument("--dry-run-fail-at", type=int, default=3)
    p.add_argument("--pg-bin")
    p.add_argument("--workdir")
    p.add_argument("--out")
    p.add_argument("--max-calls", type=int, default=HARD_MAX_CALLS)
    p.add_argument("--i-know-this-spends-money", action="store_true", help=f"permite --max-calls > {HARD_MAX_CALLS} (maximo {ABSOLUTE_MAX_CALLS})")
    p.add_argument("--scenarios", default="5,1,2,3,4,6")
    p.add_argument("--price-in", type=float, default=None, help="USD por 1M de tokens de entrada (para el costo proyectado)")
    p.add_argument("--price-out", type=float, default=None, help="USD por 1M de tokens de salida (incluye razonamiento)")
    args = p.parse_args(argv)
    if args.max_calls < 1 or args.max_calls > ABSOLUTE_MAX_CALLS:
        p.error(f"--max-calls entre 1 y {ABSOLUTE_MAX_CALLS}")
    if args.max_calls > HARD_MAX_CALLS and not args.i_know_this_spends_money:
        p.error(f"--max-calls > {HARD_MAX_CALLS} exige --i-know-this-spends-money")
    if (args.dry_run_mode != "normal" or args.dry_run_http) and not args.dry_run:
        p.error("--dry-run-mode y --dry-run-http solo con --dry-run")
    try:
        args.scenarios_list = sorted({int(x) for x in args.scenarios.split(",") if x.strip()})
    except ValueError:
        p.error("--scenarios: lista de enteros separada por comas")
    if not args.scenarios_list or any(i not in SCENARIOS for i in args.scenarios_list):
        p.error("--scenarios: ids validos 1..6")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    base.setup_logging()
    import logging
    logging.getLogger("app.services.dashboard_suggest_service").setLevel(logging.INFO)
    base._install_signal_handlers()
    say(f"Validacion de tableros | modo={'DRY-RUN' if args.dry_run else 'REAL'} | tope de llamadas={args.max_calls} | escenarios={args.scenarios_list}")
    try:
        settings = base.load_settings(args)
    except RunAborted as exc:
        say(f"ERROR de configuracion: {exc.detail}")
        return EXIT_CONFIG
    if not (settings.GOOGLE_API_KEY or "").strip():
        say("ERROR: GOOGLE_API_KEY esta vacia en Settings (entorno/.env). No se levanto nada.")
        return EXIT_CONFIG
    base._SECRETS.append(settings.GOOGLE_API_KEY)
    say(f"Config: modelo={settings.GEMINI_MODEL} timeout={settings.GEMINI_TIMEOUT_SECONDS}s api_key_presente=si")
    settings = settings.model_copy(update={"DASHBOARD_AUTO_SUGGEST": True, "CHAT_DASHBOARD_TOOL_ENABLED": True,
                                           "DASHBOARD_SUGGEST_USE_LLM": True})

    net_patches = Patches()
    selftests: list = []
    if args.dry_run:
        if args.dry_run_mode == "normal":
            selftests = base.run_selftests()
            selftests += _models_selftests()
            for name, ok, detail in selftests:
                say(f"  [selftest] {'OK ' if ok else 'FALLO'} {name}" + ("" if ok else f" -> {detail}"))
            if not all(ok for _, ok, _ in selftests):
                say("ERROR: fallaron autochequeos de los topes; no se continua.")
                return EXIT_BLOCKED
        base.install_network_guard(net_patches)
        say("DRY-RUN: red no-loopback bloqueada por codigo; ninguna llamada a Gemini es posible.")

    workdir = Path(args.workdir) if args.workdir else Path(tempfile.gettempdir())
    workdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(args.out) if args.out else workdir / f"dash_smoke_{stamp}{'_dry' if args.dry_run else ''}.json"
    cluster: DisposablePostgres | None = None
    exit_code = EXIT_INFRA
    runner: Runner | None = None
    try:
        try:
            cluster = DisposablePostgres(base.find_pg_bin(args.pg_bin), workdir)
            port = cluster.start()
            say(f"Postgres desechable en 127.0.0.1:{port} ({cluster.root})")
            exit_code, runner = asyncio.run(run_all(args, settings, port, out))
        except KeyboardInterrupt:
            say("Interrumpido por el usuario.")
            exit_code = EXIT_ERROR
        except RunAborted as exc:
            say(f"ABORTADO: {exc.detail}")
            exit_code = exc.exit_code
        except Exception as exc:
            say(f"ERROR: {type(exc).__name__}: {base.redact(exc)[:300]}")
            exit_code = EXIT_INFRA if isinstance(exc, (FileNotFoundError, RuntimeError, OSError)) else EXIT_ERROR
    finally:
        net_patches.close()
        report = cluster.cleanup() if cluster else {}
        if cluster:
            clean = bool(report.get("postgres_pid_dead") and report.get("dir_removed") and report.get("port_free"))
            say(f"\nLimpieza: postgres detenido={report.get('postgres_pid_dead')} directorio borrado={report.get('dir_removed')} "
                f"puerto {report.get('port')} libre={report.get('port_free')}")
            if not clean and exit_code == EXIT_OK:
                exit_code = EXIT_BLOCKED
    if runner is not None:
        with contextlib.suppress(Exception):
            runner.write(out, {"cleanup": report, "selftests": [{"name": n, "ok": ok, "detail": d} for n, ok, d in selftests]})
        dry = getattr(runner, "dry", None)
        if dry is not None and dry.requests:
            say("[dry-run-http] lo que el SDK REAL habria enviado:")
            for i, r in enumerate(dry.requests, 1):
                say(f"  #{i} {r['path']} tools={r['tools']} thinking={r['thinkingConfig']} maxOut={r['maxOutputTokens']} "
                    f"json={r['responseMimeType']} sys_chars={r['systemInstruction_chars']} api_key_en_header={r['has_api_key_header']}")
        say(f"JSON: {out}")
        t = runner.totals()
        say(f"TOTAL: llamadas a Gemini {t['gemini_calls']}/{runner.guard.max_calls} | http {t['http_requests']} | tokens "
            f"entrada={t['prompt_tokens']} salida={t['output_tokens']} razonamiento={t['thoughts_tokens']} total={t['total_tokens']}")
        if runner.cost():
            say(f"Costo: {runner.cost()}")
    say(f"Codigo de salida: {exit_code}")
    return exit_code


def _models_selftests() -> list[tuple[str, bool, str]]:
    """El contador tambien cubre generate_content (SDK real, transporte falso, cero red)."""
    import httpx
    from google import genai
    from google.genai import types as genai_types

    async def probe(statuses: list[int], max_calls: int, sends: int):
        guard = CallGuard(max_calls)
        guard.quiet = True
        patches = Patches()
        seen: list = []
        outcome = []
        try:
            base.install_http_guard(guard, patches)
            install_models_guard(guard, patches)
            http_client = httpx.AsyncClient(transport=base._mock_gemini_transport(statuses, seen))
            options = genai_types.HttpOptions(httpx_async_client=http_client, retry_options=genai_types.HttpRetryOptions(attempts=1))
            client = genai.Client(api_key=base.DRY_RUN_KEY, http_options=options)
            for i in range(sends):
                try:
                    await client.aio.models.generate_content(model="gemini-test", contents=f"hola {i}")
                    outcome.append("ok")
                except RunAborted as exc:
                    outcome.append(exc.kind)
                    break
            await http_client.aclose()
        finally:
            patches.close()
        return {"outcome": outcome, "logical": guard.calls, "transport": len(seen)}

    a = asyncio.run(probe([200], 10, 1))
    b = asyncio.run(probe([200, 400, 200], 10, 3))
    c = asyncio.run(probe([200], 2, 5))
    return [
        ("generate_content: 1 llamada => 1 logica y 1 HTTP", a["logical"] == 1 and a["transport"] == 1, str(a)),
        ("generate_content: 400 => aborta con http_4xx y no envia mas", b["outcome"] == ["ok", "http_4xx"] and b["transport"] == 2, str(b)),
        ("generate_content: tope 2 => la 3.a se rechaza sin enviar", c["outcome"] == ["ok", "ok", "budget"] and c["transport"] == 2, str(c)),
    ]


if __name__ == "__main__":
    sys.exit(main())
