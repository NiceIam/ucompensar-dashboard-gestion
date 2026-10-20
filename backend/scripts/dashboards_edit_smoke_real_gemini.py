#!/usr/bin/env python
"""Validacion de la EDICION DE TABLEROS por la IA contra Gemini REAL, con TOPES DE GASTO impuestos por codigo.

Modelado sobre `dashboards_smoke_real_gemini.py` (misma guardia de `chat_smoke_real_gemini.py`: contador duro de
llamadas, solo el host de Gemini, sin reintentos del SDK, parada en el primer 4xx, clave solo via get_settings() y
nunca impresa, Postgres desechable propio en 127.0.0.1). Ejecutar SIEMPRE desde `backend/` con el venv del proyecto.
Vive fuera de `tests/` y su nombre no empieza por `test_`: pytest no lo recoge.

Cada escenario pasa por `chat_service.send_message` (cuota, historial real de la BD, bloques del servidor), como
en produccion. Orden fijo 1..8; el 6 (deshacer por REST) NO llama a Gemini.

  1 "creame un tablero de ventas por mes y por producto"             tablero base (create_dashboard)
  2 "agregale un grafico de ventas por metodo de pago"               edit_dashboard: add_widget
  3 "cambia el grafico de barras por una torta"                      edit_dashboard: replace_widget (o pregunta)
  4 "quitale el segundo grafico"                                     edit_dashboard: remove_widget
  5 "renombralo a Resumen de ventas 2025"                            edit_dashboard: rename
  6 deshacer por REST (POST /dashboards/{id}/undo-edit) x2           0 llamadas a Gemini
  7 "agregale un grafico de clientes por ciudad al tablero de ventas"  nombre AMBIGUO (2 tableros con "ventas")
  8 "edita el tablero de inventario"                                 tablero INEXISTENTE
Llamadas esperadas a Gemini: 2+2+2+2+2+0+2+1..2 = 13-14 (maximo ~16). Tope duro por defecto 16; hasta 25 solo con
--i-know-this-spends-money (maximo absoluto 25). La llamada N+1 se rechaza ANTES de enviarse.

Codigos de salida: 0 ok | 2 error HTTP 4xx | 3 tope de llamadas/HTTP | 4 otro error o timeout | 5 configuracion/
argumentos/clave | 6 infraestructura (Postgres) | 7 red no permitida o fallo de limpieza.

Ejemplos (desde backend/, con el venv del proyecto):
  # en seco (sin red ni clave; SDK real sobre un transporte falso con --dry-run-http):
  python scripts/dashboards_edit_smoke_real_gemini.py --dry-run --dry-run-http --workdir <dir> --out <dir>/edit_smoke.json
  # topes en seco: --dry-run-mode overbudget | error429 | error400 | error503 | unexpected | timeout
  # real (gasta hasta --max-calls llamadas de la API key compartida; GOOGLE_API_KEY y APP_SECRET_KEY por entorno
  # o en backend/.env; el script no lee .env por su cuenta):
  python scripts/dashboards_edit_smoke_real_gemini.py --workdir <dir> --out <dir>/edit_smoke_real.json --max-calls 16
  # solo algunos escenarios (los que dependen del tablero base lo siembran sin Gemini si el 1 no corre):  --scenarios 1,2,3
  # costo proyectado por edicion: --price-in <USD por 1M tokens de entrada> --price-out <USD por 1M de salida>
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import datetime
import json
import re
import sys
import tempfile
import time
import unicodedata
from collections import deque
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import chat_smoke_real_gemini as base  # noqa: E402  (hace os.chdir(backend) y deja `tests` importable)
import dashboards_smoke_real_gemini as dsm  # noqa: E402
from chat_smoke_real_gemini import (  # noqa: E402
    CallGuard, DisposablePostgres, NetworkBlocked, Patches, RunAborted, say,
    EXIT_BLOCKED, EXIT_CONFIG, EXIT_ERROR, EXIT_INFRA, EXIT_OK,
)

HARD_MAX_CALLS = 16
ABSOLUTE_MAX_CALLS = 25
ORG_ID = base.ORG_ID
USER_ID = "11111111-1111-4111-8111-111111111111"
RUN_ORDER = [1, 2, 3, 4, 5, 6, 7, 8]
BASE_NAME = "Ventas por mes y por producto"
RENAMED = "Resumen de ventas 2025"
SCENARIOS = {
    1: "creame un tablero de ventas por mes y por producto",
    2: "agregale un grafico de ventas por metodo de pago",
    3: "cambia el grafico de barras por una torta",
    4: "quitale el segundo grafico",
    5: f"renombralo a {RENAMED}",
    6: "(deshacer por REST: renombre y quitado)",
    7: "agregale un grafico de clientes por ciudad al tablero de ventas",
    8: "edita el tablero de inventario",
}
EXPECTED = {
    1: "create_dashboard; 1 tablero nuevo con >=3 graficos; edit_dashboard NO declarada",
    2: "edit_dashboard declarada (create_dashboard no); add_widget; +1 grafico; datos por metodo_pago correctos; <=3.500 tokens de entrada y <=500 de salida",
    3: "replace_widget barras->torta (mismo n.o de graficos) O pregunta si hay 2 barras; no crea tableros",
    4: "remove_widget de UN grafico (-1); el tablero no queda vacio",
    5: f"rename: el tablero se llama {RENAMED!r}; mismos graficos",
    6: "undo-edit del renombre -> 200 y vuelve el nombre; undo-edit del quitado -> 200 y vuelve el grafico; reusar la version -> 404",
    7: "el servidor responde 'varios tableros parecidos'; el modelo PREGUNTA cual; ningun tablero cambia",
    8: "ningun cambio ni tablero nuevo; el modelo dice que no existe (o pregunta que cambiar)",
}
BASE_WIDGETS = dsm.VENTAS_BOARD[:3]          # cifra total, ventas por mes y barras por producto (sin la torta)
W_METODO_VALUES = {"transferencia": 4_941_700, "tarjeta": 3_109_000, "efectivo": 2_184_000}   # csv sobre ventas.csv
BLOCK_EDIT = re.compile(r"```dashboard_edit\s*\n(.*?)\n```", re.DOTALL)
BLOCK_BOARD = re.compile(r"```dashboard\s*\n(.*?)\n```", re.DOTALL)


def _fold(text) -> str:
    return unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower().strip()


# ---------------------------------------------------------------------------
# Cliente falso del dry-run (guion por escenario; refleja lo que deberia hacer un modelo correcto)
# ---------------------------------------------------------------------------

PIE_METODO = {"table": "ventas", "chart_type": "pie", "x": "metodo_pago", "y": "sum(total)"}
PIE_PRODUCTO = {"table": "ventas", "chart_type": "pie", "x": "producto", "y": "sum(total)", "top": 5}
BAR_CIUDAD = {"table": "clientes", "chart_type": "bar", "x": "ciudad", "y": "count"}


def _edit(dashboard, *ops, cid="c1"):
    return ("edit_dashboard", {"dashboard": dashboard, "operations": list(ops)}, cid)


class DryScript(dsm.DryScript):
    def load(self, sc_id: int) -> None:
        from tests import fake_gemini as fg

        u = fg.usage
        if self.mode == "overbudget":
            self.queue = deque([lambda m: fg.text_response("x", u(500, 10, 0))] * 4)
            return
        steps = {
            1: [lambda m: fg.call_response(("create_dashboard", {"title": BASE_NAME, "widgets": BASE_WIDGETS}, "c1"), usage_metadata=u(1900, 190, 30)),
                lambda m: fg.text_response("Listo, creé tu tablero.", u(2000, 25, 0))],
            2: [lambda m: fg.call_response(_edit(BASE_NAME, {"op": "add_widget", "spec": PIE_METODO}), usage_metadata=u(1500, 90, 20)),
                lambda m: fg.text_response("Listo, agregué la torta.", u(1550, 15, 0))],
            3: [lambda m: fg.call_response(_edit(BASE_NAME, {"op": "replace_widget", "target": "barras", "spec": PIE_PRODUCTO}), usage_metadata=u(1500, 90, 20)),
                lambda m: fg.text_response("Cambié las barras por una torta.", u(1550, 15, 0))],
            4: [lambda m: fg.call_response(_edit(BASE_NAME, {"op": "remove_widget", "target": "2"}), usage_metadata=u(1500, 60, 20)),
                lambda m: fg.text_response("Quité el segundo gráfico.", u(1550, 15, 0))],
            5: [lambda m: fg.call_response(_edit(BASE_NAME, {"op": "rename", "title": RENAMED}), usage_metadata=u(1500, 50, 20)),
                lambda m: fg.text_response("Listo, ya se llama así.", u(1550, 15, 0))],
            6: [],
            7: [lambda m: fg.call_response(_edit("ventas", {"op": "add_widget", "spec": BAR_CIUDAD}), usage_metadata=u(1500, 90, 20)),
                lambda m: fg.text_response("Tienes dos tableros de ventas: «Resumen de ventas 2025» y «Ventas del año». ¿En cuál lo agrego?", u(1700, 40, 0))],
            8: [lambda m: fg.call_response(_edit("inventario", {"op": "add_widget", "spec": BAR_CIUDAD}), usage_metadata=u(1500, 90, 20)),
                lambda m: fg.text_response("No tienes un tablero de inventario. ¿Quieres que lo cree?", u(1700, 40, 0))],
        }[sc_id]
        self.queue = deque(steps)


# ---------------------------------------------------------------------------
# Estado del tablero en Postgres
# ---------------------------------------------------------------------------

async def boards_state(pool) -> list[dict]:
    async with pool.acquire() as conn:
        boards = await conn.fetch("SELECT id, name FROM dashboards WHERE deleted_at IS NULL ORDER BY created_at")
        out = []
        for b in boards:
            widgets = await conn.fetch(
                "SELECT id::text AS id, title, widget_type FROM widgets WHERE dashboard_id = $1 "
                "ORDER BY position_y, position_x, created_at", b["id"])
            out.append({"id": str(b["id"]), "name": b["name"], "widgets": [dict(w) for w in widgets]})
    return out


def find_board(state: list[dict], board_id: str | None):
    return next((b for b in state if b["id"] == board_id), None)


def _fingerprint(state: list[dict]) -> str:
    return json.dumps(state, sort_keys=True, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Escenarios
# ---------------------------------------------------------------------------

async def run_scenario(runner, sc_id: int, dry: DryScript | None) -> dict:
    from app.services import agent_tools_service as ats
    from app.services import chat_service
    from app.services import dashboard_builder_service as builder
    from app.services import data_query_engine as engine
    from app.services.dashboard_render_service import render_dashboard

    guard, ctx, pool = runner.guard, runner.ctx, runner.pool
    guard.scenario = sc_id
    calls_before, http_before = guard.calls, guard.http_calls
    if dry:
        dry.load(sc_id)
    say(f"\n=== Escenario {sc_id}: {SCENARIOS[sc_id]!r} ===")
    entry: dict = {"id": sc_id, "prompt": SCENARIOS[sc_id], "expected": EXPECTED[sc_id]}

    async def catalog():
        async with pool.acquire() as conn:
            return engine.build_catalog(await conn.fetch(
                "SELECT id, table_name, display_name, row_count, columns_definition FROM org_data_tables"))

    async def seed_base_board() -> None:
        created, _ = await builder.build_dashboard(pool, await catalog(), BASE_NAME, BASE_WIDGETS)
        ctx["board_id"] = created["id"]
        entry["base_board_seeded_by_script"] = True
        say("  (tablero base sembrado por el script, sin Gemini)")

    state_before = await boards_state(pool)
    if sc_id != 1 and ctx.get("board_id") is None:
        await seed_base_board()
        state_before = await boards_state(pool)
    if sc_id == 7 and not any(b["name"] != ctx.get("name") and "ventas" in _fold(b["name"]) and b["id"] != ctx.get("board_id")
                              for b in state_before):
        await builder.build_dashboard(pool, await catalog(), "Ventas del año", [dsm.VENTAS_BOARD[0], dsm.VENTAS_BOARD[3]])
        state_before = await boards_state(pool)
        entry["second_board_seeded_by_script"] = True

    started = time.monotonic()
    if sc_id == 6:
        entry.update(await rest_undo(runner))
        entry["latency_ms"] = int((time.monotonic() - started) * 1000)
        entry["calls_used"] = entry["http_requests"] = 0
        entry["tools_called"], entry["declared"], entry["usage"] = [], [], {"prompt_tokens": 0, "output_tokens": 0, "thoughts_tokens": 0, "total_tokens": 0, "model_calls": 0}
        entry["text"], entry["fallback_reason"] = "", None
        return entry

    declared: list[tuple] = []
    original_declarations = ats._tool_declarations

    def recording_declarations(with_dashboard=False, with_edit=False):
        declared.append((bool(with_dashboard), bool(with_edit)))
        return original_declarations(with_dashboard, with_edit)

    scenario_settings = runner.settings.model_copy(update={"CHAT_MAX_TOOL_ROUNDS": 3})
    timeout = float(scenario_settings.GEMINI_TIMEOUT_SECONDS) + 15.0
    assistant_content = ""
    try:
        with patch.object(ats, "get_settings", return_value=scenario_settings), \
                patch.object(chat_service, "get_settings", return_value=scenario_settings), \
                patch.object(ats, "_tool_declarations", recording_declarations):
            _user, assistant = await asyncio.wait_for(
                chat_service.send_message(ORG_ID, USER_ID, SCENARIOS[sc_id]), timeout=timeout)
            assistant_content = assistant.content
    finally:
        entry["latency_ms"] = int((time.monotonic() - started) * 1000)
        entry["calls_used"] = guard.calls - calls_before
        entry["http_requests"] = guard.http_calls - http_before
        entry["gemini_calls"] = [r for r in guard.records if r["scenario"] == sc_id]
        entry["tools_called"] = [{"call": i + 1, **fc} for i, r in enumerate(entry["gemini_calls"]) for fc in r["function_calls"]]

    usage = {k: sum((r.get("usage") or {}).get(k, 0) for r in entry["gemini_calls"])
             for k in ("prompt_tokens", "output_tokens", "thoughts_tokens", "total_tokens")}
    usage["model_calls"] = entry["calls_used"]
    first = (entry["gemini_calls"][0].get("usage") or {}) if entry["gemini_calls"] else {}
    usage["first_call_prompt_tokens"] = first.get("prompt_tokens", 0)
    entry["usage"] = usage
    edits = [json.loads(m) for m in BLOCK_EDIT.findall(assistant_content)]
    boards_made = [json.loads(m) for m in BLOCK_BOARD.findall(assistant_content)]
    text = BLOCK_EDIT.sub("", BLOCK_BOARD.sub("", assistant_content)).strip()
    entry["text"] = text[:600]
    entry["fallback_reason"] = "fallback" if text.startswith("No pude consultar al asistente") else None
    entry["declared"] = declared
    entry["dashboard_edits"] = edits
    entry["dashboards_created"] = [{"name": b.get("name"), "widgets": b.get("widgets"), "existing": b.get("existing")} for b in boards_made]
    state_after = await boards_state(pool)
    entry["state_after"] = [{"name": b["name"], "widgets": [w["title"] + f" [{w['widget_type']}]" for w in b["widgets"]]} for b in state_after]
    called = [t["name"] for t in entry["tools_called"]]
    edit_declared = any(e for _, e in declared)
    create_declared = any(c for c, _ in declared)
    edit_args = json.dumps([t["args"] for t in entry["tools_called"] if t["name"] == "edit_dashboard"], ensure_ascii=False)
    board = find_board(state_after, ctx.get("board_id"))
    before = find_board(state_before, ctx.get("board_id"))
    n_before = len(before["widgets"]) if before else 0
    n_after = len(board["widgets"]) if board else 0
    unchanged = _fingerprint(state_before) == _fingerprint(state_after)
    ok_text = text.strip().endswith("?") or "?" in text
    flags: dict = {}
    if sc_id == 1:
        made = boards_made[0] if boards_made else {}
        ctx["board_id"] = made.get("id")
        ctx["name"] = made.get("name")
        flags = {"creo_un_tablero": len(boards_made) == 1 and not made.get("existing"), "llamo_create_dashboard": "create_dashboard" in called,
                 "edit_dashboard_NO_declarada": not edit_declared, "con_3_o_mas_graficos": (made.get("widgets") or 0) >= 3}
        if ctx["board_id"] is None:
            await seed_base_board()
            flags["tablero_base_sembrado_por_el_script"] = True
    elif sc_id == 2:
        edit = edits[0] if edits else {}
        ctx["versions"] = {**ctx.get("versions", {}), 2: edit.get("version")}
        new_chart = None
        if board and edit:
            rendered = await render_dashboard(ORG_ID, board["id"])
            new_chart = next((c for c in rendered["charts"] if "metodo_pago" in _fold(c["title"]) and not c.get("error")), None)
            entry["render_errors"] = [c["error"] for c in rendered["charts"] if c.get("error")] + [k["error"] for k in rendered["kpis"] if k.get("error")]
        flags = {"declaro_edit_dashboard": edit_declared, "create_dashboard_NO_declarada": not create_declared,
                 "llamo_edit_dashboard_con_add_widget": "edit_dashboard" in called and "add_widget" in edit_args,
                 "agrego_un_grafico": n_after == n_before + 1 and len(edit.get("added") or []) == 1,
                 "no_creo_tableros": not boards_made and len(state_after) == len(state_before),
                 "sin_errores_al_calcular": not entry.get("render_errors"),
                 "datos_por_metodo_pago_correctos": bool(new_chart) and (
                     {p["name"]: p["value"] for p in new_chart["data"]} == W_METODO_VALUES
                     or "count" in _fold(new_chart["title"]) or "cantidad" in _fold(new_chart["title"])),
                 "sin_ids_en_los_argumentos": not re.search(r'"(id|dashboard_id|color|position\w*)"', edit_args),
                 "entrada_total_<=3500": usage["prompt_tokens"] <= 3500, "salida_total_<=500": usage["output_tokens"] + usage["thoughts_tokens"] <= 500,
                 "a_lo_sumo_3_llamadas": entry["calls_used"] <= 3}
    elif sc_id == 3:
        edit = edits[0] if edits else {}
        ctx["versions"] = {**ctx.get("versions", {}), 3: edit.get("version")}
        flags = {"declaro_edit_dashboard": edit_declared,
                 "reemplazo_barras_por_torta_O_pregunto_por_ambiguedad": (
                     bool(edit.get("replaced")) and n_after == n_before
                     and any("pie" in w["widget_type"] for w in (board or {"widgets": []})["widgets"]))
                 or (not edits and unchanged and ok_text),
                 "no_creo_tableros": not boards_made and len(state_after) == len(state_before)}
    elif sc_id == 4:
        edit = edits[0] if edits else {}
        ctx["versions"] = {**ctx.get("versions", {}), 4: edit.get("version")}
        flags = {"declaro_edit_dashboard": edit_declared, "quito_un_grafico": len(edit.get("removed") or []) == 1 and n_after == n_before - 1,
                 "no_dejo_el_tablero_vacio": n_after >= 1, "no_agrego_nada": not edit.get("added")}
        ctx["widgets_before_s4"] = n_before
    elif sc_id == 5:
        edit = edits[0] if edits else {}
        ctx["versions"] = {**ctx.get("versions", {}), 5: edit.get("version")}
        ctx["name_before_s5"] = before["name"] if before else None
        flags = {"declaro_edit_dashboard": edit_declared, "renombro": bool(board) and _fold(board["name"]) == _fold(RENAMED),
                 "mismos_graficos": n_after == n_before, "bloque_con_renamed": bool(edit.get("renamed"))}
        ctx["name"] = board["name"] if board else ctx.get("name")
    elif sc_id == 7:
        flags = {"declaro_edit_dashboard": edit_declared, "ningun_tablero_cambio": unchanged and not edits,
                 "el_modelo_pregunto_cual": ok_text, "no_creo_tableros": not boards_made}
        entry["server_errors_seen"] = [t["name"] for t in entry["tools_called"]]
    elif sc_id == 8:
        flags = {"declaro_edit_dashboard": edit_declared, "ningun_cambio": unchanged and not edits and not boards_made,
                 "el_modelo_responde_sin_inventar": bool(text)}
    entry["expected_flags"] = flags
    return entry


async def asgi_request(app, method: str, path: str, body: dict | None = None) -> tuple[int, object]:
    """Llama a la app ASGI REAL en el mismo event loop SIN sockets ni httpx (la guardia de red de este script rechaza
    cualquier peticion httpx que no sea a Gemini). Devuelve (status, JSON)."""
    payload = json.dumps(body).encode() if body is not None else b""
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "path": path,
             "raw_path": path.encode(), "query_string": b"", "scheme": "http", "root_path": "",
             "headers": [(b"host", b"smoke"), (b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())],
             "client": ("127.0.0.1", 1), "server": ("smoke", 80)}
    sent = {"body": False}
    out: dict = {"status": None, "chunks": []}

    async def receive():
        if not sent["body"]:
            sent["body"] = True
            return {"type": "http.request", "body": payload, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            out["status"] = message["status"]
        elif message["type"] == "http.response.body":
            out["chunks"].append(message.get("body", b""))

    await app(scope, receive, send)
    raw = b"".join(out["chunks"])
    try:
        return out["status"], json.loads(raw) if raw else None
    except ValueError:
        return out["status"], raw[:200].decode("utf-8", "replace")


async def rest_undo(runner) -> dict:
    """Deshacer por la API REAL (ASGI en el mismo event loop; sin sockets): renombre (5) y quitado (4)."""
    from app.auth import CurrentUser, get_current_user
    from app.routers import dashboard_edits
    from main import create_app

    ctx, pool = runner.ctx, runner.pool
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id=USER_ID, org_id=ORG_ID, email="u@example.com", role="member")

    async def get_pool(_org):
        return pool

    out: dict = {"rest": []}
    board_id = ctx.get("board_id")
    versions = ctx.get("versions", {})
    with patch.object(dashboard_edits, "get_org_pool", get_pool):
        code, listed = await asgi_request(app, "GET", f"/api/v1/dashboards/{board_id}/versions")
        out["rest"].append({"GET versions": code, "n": len(listed) if code == 200 else None})
        steps = [("undo renombre (5)", versions.get(5)), ("undo quitado (4)", versions.get(4)), ("reusar version (4)", versions.get(4))]
        for label, version in steps:
            code, body = await asgi_request(app, "POST", f"/api/v1/dashboards/{board_id}/undo-edit", {"version": str(version)})
            out["rest"].append({label: code, "body": body})
    state = find_board(await boards_state(pool), board_id)
    r = out["rest"]
    codes = [list(x.values())[0] for x in r[1:]]
    flags = {"hubo_versiones_para_deshacer": all(versions.get(i) for i in (4, 5)),
             "undo_renombre_200": codes[:1] == [200], "undo_quitado_200": codes[1:2] == [200], "reusar_version_404": codes[2:3] == [404],
             "volvio_el_nombre_anterior": bool(state) and state["name"] == ctx.get("name_before_s5"),
             "volvio_el_grafico_quitado": bool(state) and len(state["widgets"]) == ctx.get("widgets_before_s4")}
    out["expected_flags"] = flags
    out["state_after"] = [{"name": state["name"], "widgets": [w["title"] for w in state["widgets"]]}] if state else []
    ctx["name"] = state["name"] if state else ctx.get("name")
    return out


class Runner:
    def __init__(self, args, settings, guard: CallGuard, expected: dict):
        self.args, self.settings, self.guard, self.expected = args, settings, guard, expected
        self.results: list[dict] = []
        self.aborted: dict | None = None
        self.ctx: dict = {}
        self.pool = None

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
        edits = [r for r in self.results if r["id"] in (2, 3, 4, 5)]
        usd = lambda u: (u["prompt_tokens"] * self.args.price_in + (u["output_tokens"] + u["thoughts_tokens"]) * self.args.price_out) / 1e6  # noqa: E731
        t = self.totals()
        return {"total_usd": round(usd(t), 6),
                "avg_usd_per_edit": round(sum(usd(r["usage"]) for r in edits) / len(edits), 6) if edits else None}

    def table(self) -> list[dict]:
        rows = []
        for r in self.results:
            flags = r.get("expected_flags") or {}
            rows.append({"id": r["id"], "prompt": r["prompt"], "esperado": r["expected"],
                         "obtenido": {"banderas_ok": [k for k, v in flags.items() if v], "banderas_FALLAN": [k for k, v in flags.items() if not v],
                                      "llamadas": r["calls_used"], "tokens_entrada": r["usage"]["prompt_tokens"],
                                      "tokens_salida": r["usage"]["output_tokens"], "texto": r["text"][:160]}})
        return rows

    def write(self, out: Path, extra: dict | None = None) -> None:
        dry = getattr(self, "dry", None)
        payload = {
            "meta": {"mode": "dry-run" if self.args.dry_run else "REAL", "model": self.settings.GEMINI_MODEL,
                     "max_calls": self.guard.max_calls, "api_key_present": bool(self.settings.GOOGLE_API_KEY),
                     "sdk_retries": "desactivados (attempts=1)", "started_at": datetime.datetime.now().isoformat(timespec="seconds")},
            "scenarios": self.results, "esperado_vs_obtenido": self.table(), "totals": self.totals(), "cost": self.cost(),
            "aborted": self.aborted,
            **({"mock_http_requests": dry.requests} if dry is not None and dry.requests else {}), **(extra or {}),
        }
        with contextlib.suppress(Exception):
            out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(base.redact(json.dumps(payload, ensure_ascii=False, indent=2, default=str)), encoding="utf-8")


def print_scenario(entry: dict) -> None:
    u = entry["usage"]
    say(f"  llamadas={entry['calls_used']} http={entry['http_requests']} latencia={entry['latency_ms']} ms fallback={entry['fallback_reason']}")
    say("  herramientas: " + (", ".join(f"{t['name']}({json.dumps(t['args'], ensure_ascii=False)[:160]})" for t in entry["tools_called"]) or "(ninguna)"))
    say(f"  tokens: entrada={u['prompt_tokens']} salida={u['output_tokens']} razonamiento={u['thoughts_tokens']} total={u['total_tokens']}")
    if entry.get("dashboard_edits"):
        say(f"  bloque dashboard_edit: {json.dumps(entry['dashboard_edits'], ensure_ascii=False)[:300]}")
    if entry.get("rest"):
        say(f"  REST: {json.dumps(entry['rest'], ensure_ascii=False)[:400]}")
    say(f"  banderas: {json.dumps(entry['expected_flags'], ensure_ascii=False)}")
    if entry["text"]:
        say("  texto: " + entry["text"].replace("\n", "\n         "))


def print_table(runner: Runner) -> None:
    say("\n=== ESPERADO vs OBTENIDO ===")
    for row in runner.table():
        bad = row["obtenido"]["banderas_FALLAN"]
        say(f"[{row['id']}] {'OK ' if not bad else 'REVISAR'} {row['prompt']}")
        say(f"     esperado: {row['esperado']}")
        say(f"     obtenido: llamadas={row['obtenido']['llamadas']} entrada={row['obtenido']['tokens_entrada']} salida={row['obtenido']['tokens_salida']}"
            + (f" | FALLAN: {', '.join(bad)}" if bad else ""))


async def run_all(args, settings, pg_port: int, out: Path):
    from tests.fake_org_db import FakeMainPool
    from app.services import agent_tools_service as ats
    from app.services import chat_service
    from app.services import dashboard_builder_service as builder
    from app.services import dashboard_edit_service as editor
    from app.services import dashboard_render_service as render
    from app.services import dashboard_service as dsv
    from app.services import dashboard_suggest_service as suggest_service

    tables, expected = dsm.build_seed()
    guard = CallGuard(args.max_calls)
    runner = Runner(args, settings, guard, expected)
    pool = await dsm.create_org_database(pg_port, tables)
    runner.pool = pool
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
        dsm.install_models_guard(guard, patches)
        if args.dry_run:
            dry = DryScript(args.dry_run_mode, args.dry_run_fail_at)
            runner.dry = dry  # type: ignore[attr-defined]
        if args.dry_run and args.dry_run_http:
            import httpx

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
            patch.object(chat_service, "get_org_pool", get_pool),
            patch.object(dsv, "get_org_pool", get_pool), patch.object(render, "get_org_pool", get_pool),
            patch.object(suggest_service, "get_org_pool", get_pool),
            patch.object(builder, "get_settings", return_value=settings), patch.object(editor, "get_settings", return_value=settings),
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
                if entry["fallback_reason"]:
                    runner.aborted = {"scenario": sc_id, "kind": "fallback", "exit_code": EXIT_ERROR,
                                      "detail": "la app cayo al fallback (Gemini fallo); no se continua"}
                    exit_code = EXIT_ERROR
                    say("\n!!! ABORTADO: la respuesta es el texto de fallback")
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

    p = _Parser(description="Validacion de la edicion de tableros por la IA con Gemini real y topes de gasto por codigo.")
    p.add_argument("--dry-run", action="store_true", help="cliente falso, sin red ni clave")
    p.add_argument("--dry-run-mode", choices=DryScript.MODES, default="normal")
    p.add_argument("--dry-run-http", action="store_true", help="solo con --dry-run: SDK REAL sobre un transporte httpx falso")
    p.add_argument("--dry-run-fail-at", type=int, default=3)
    p.add_argument("--pg-bin")
    p.add_argument("--workdir")
    p.add_argument("--out")
    p.add_argument("--max-calls", type=int, default=HARD_MAX_CALLS)
    p.add_argument("--i-know-this-spends-money", action="store_true", help=f"permite --max-calls > {HARD_MAX_CALLS} (maximo {ABSOLUTE_MAX_CALLS})")
    p.add_argument("--scenarios", default="1,2,3,4,5,6,7,8")
    p.add_argument("--price-in", type=float, default=None, help="USD por 1M de tokens de entrada")
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
        p.error("--scenarios: ids validos 1..8")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    base.setup_logging()
    base._install_signal_handlers()
    say(f"Validacion de edicion de tableros | modo={'DRY-RUN' if args.dry_run else 'REAL'} | tope de llamadas={args.max_calls} | escenarios={args.scenarios_list}")
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
    settings = settings.model_copy(update={"DASHBOARD_AUTO_SUGGEST": False, "CHAT_DASHBOARD_TOOL_ENABLED": True,
                                           "CHAT_DASHBOARD_EDIT_ENABLED": True, "CHAT_ORG_DAILY_MESSAGES": 300,
                                           "CHAT_USER_MAX_MESSAGES": 20})

    net_patches = Patches()
    selftests: list = []
    if args.dry_run:
        if args.dry_run_mode == "normal":
            selftests = base.run_selftests()
            selftests += dsm._models_selftests()
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
    out = Path(args.out) if args.out else workdir / f"edit_smoke_{stamp}{'_dry' if args.dry_run else ''}.json"
    cluster: DisposablePostgres | None = None
    exit_code = EXIT_INFRA
    runner: Runner | None = None
    report: dict = {}
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
        print_table(runner)
        dry = getattr(runner, "dry", None)
        if dry is not None and dry.requests:
            say("[dry-run-http] lo que el SDK REAL habria enviado:")
            for i, r in enumerate(dry.requests, 1):
                say(f"  #{i} {r['path']} tools={r['tools']} thinking={r['thinkingConfig']} maxOut={r['maxOutputTokens']} "
                    f"sys_chars={r['systemInstruction_chars']} api_key_en_header={r['has_api_key_header']}")
        say(f"JSON: {out}")
        t = runner.totals()
        say(f"TOTAL: llamadas a Gemini {t['gemini_calls']}/{runner.guard.max_calls} | http {t['http_requests']} | tokens "
            f"entrada={t['prompt_tokens']} salida={t['output_tokens']} razonamiento={t['thoughts_tokens']} total={t['total_tokens']}")
        if runner.cost():
            say(f"Costo: {runner.cost()}")
    say(f"Codigo de salida: {exit_code}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
