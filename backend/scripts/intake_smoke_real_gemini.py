#!/usr/bin/env python
"""Validacion del agente de esquema de la CARGA INTELIGENTE contra Gemini REAL, con TOPES DE GASTO por codigo.

Ejecutar SIEMPRE desde `backend/` con el venv del proyecto. Vive fuera de `tests/` y su nombre no empieza por
`test_`: pytest no lo recoge (un test lo ejecuta solo en modo --dry-run).

Que hace
- Toma el set de hojas desordenadas de `tests/intake_corpus.py` (restaurante, tienda, taller, drogueria, ferreteria,
  cartera, bodega; encabezados en ingles, abreviaturas colombianas, columnas genericas e inyeccion en celdas) y le
  pasa cada una a `schema_ai_service.understand` (cache -> determinista -> UNA llamada a Gemini si es ambigua).
- Mide: acierto del tipo de hoja (`kind`) y de cada rol contra la verdad esperada, tokens reales por hoja
  (entrada / salida / razonamiento), llamadas gastadas, fallos, y proyecta los tokens por organizacion (8 hojas).
  Sin precios por defecto: pasar --price-in / --price-out (USD por millon de tokens) para ver el costo.
- No necesita Postgres: el agente de esquema solo lee encabezados y muestras. (La corrida de punta a punta con
  Postgres desechable esta en tests/test_intake_pg.py y NO usa Gemini.)

Topes por codigo (todos abortan la corrida, escriben el JSON parcial y salen con codigo != 0)
- Tope DURO de llamadas a Gemini en TODA la corrida (--max-calls, default 15; maximo absoluto 50; > 15 exige
  --i-know-this-spends-money). La llamada N+1 se rechaza ANTES de enviarse.
- Solo se permite el host generativelanguage.googleapis.com, a lo sumo 1 peticion HTTP por llamada logica (un
  reintento oculto del SDK aborta ANTES de enviarse). El cliente se crea con HttpRetryOptions(attempts=1).
- PARADA INMEDIATA ante el primer error HTTP 4xx (incluido 429): se registra (sin la clave) y no se reintenta.
- Cualquier otra excepcion de la llamada (5xx, timeout, red) tambien aborta.
- La clave se lee SOLO via app.config.get_settings() y nunca se imprime ni se guarda; todo pasa por un redactor.
  El script no lee ni imprime el contenido de ningun .env.

Codigos de salida: 0 ok | 2 HTTP 4xx | 3 tope de llamadas/HTTP | 4 otro error/timeout | 5 configuracion/clave | 7 red.

Ejemplos (desde backend/):
  # en seco, sin red ni clave (oraculo perfecto / con errores a proposito):
  <python> scripts/intake_smoke_real_gemini.py --dry-run --out <dir>/intake_dry.json
  <python> scripts/intake_smoke_real_gemini.py --dry-run --dry-run-mode noisy
  # topes en seco:  --dry-run-mode overbudget | error400 | error429 | error503 | timeout | malformed
  # idem, con el SDK REAL de google-genai sobre un transporte httpx falso (valida el cuerpo que se enviaria):
  <python> scripts/intake_smoke_real_gemini.py --dry-run --dry-run-http
  # REAL (gasta llamadas de la API key compartida: una por hoja ambigua del set, ~9):
  <python> scripts/intake_smoke_real_gemini.py --max-calls 15 --out <dir>/intake_real.json
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import datetime
import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

BACKEND_DIR = Path(__file__).resolve().parents[1]
os.chdir(BACKEND_DIR)                 # Settings lee ".env" relativo al cwd; tambien hace importable `tests`
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Se reutiliza la maquinaria de guardas del smoke del chat (mismos topes y mismo redactor).
_spec = importlib.util.spec_from_file_location("chat_smoke_guards", BACKEND_DIR / "scripts" / "chat_smoke_real_gemini.py")
smoke = importlib.util.module_from_spec(_spec)
sys.modules["chat_smoke_guards"] = smoke
_spec.loader.exec_module(smoke)

say, redact = smoke.say, smoke.redact
EXIT_OK, EXIT_CONFIG, EXIT_ERROR = smoke.EXIT_OK, smoke.EXIT_CONFIG, smoke.EXIT_ERROR
ABS_MAX_CALLS = 50
DEFAULT_MAX_CALLS = 15
ORG_ID = "00000000-0000-4000-8000-0000000000b2"
MODES = ("normal", "noisy", "overbudget", "error400", "error429", "error503", "timeout", "malformed")
SHEETS_PER_ORG = 8          # supuesto de la proyeccion: una organizacion sube ~8 hojas en total


# ---------------------------------------------------------------------------
# Verdad esperada y servidor falso (dry-run)
# ---------------------------------------------------------------------------

def load_corpus(ids: str | None):
    from tests import intake_corpus as corpus

    cases = list(corpus.CASES)
    if ids:
        wanted = [i.strip() for i in ids.split(",") if i.strip()]
        unknown = [i for i in wanted if i not in corpus.BY_ID]
        if unknown:
            raise smoke.RunAborted(f"--sheets: ids desconocidos {unknown}; validos: {sorted(corpus.BY_ID)}")
        cases = [corpus.BY_ID[i] for i in wanted]
    return cases


def oracle_answer(case, noisy: bool = False) -> dict:
    """Lo que un modelo PERFECTO contestaria (o con 2 errores a proposito si noisy)."""
    roles = list(case.roles)
    if noisy and len(roles) >= 2:
        roles[0], roles[-1] = "otro", ("producto" if case.kind == "ventas" else "otro")
    cols = []
    for i, role in enumerate(roles):
        item = {"i": i, "role": role, "confidence": 0.9}
        if role == "otro":
            item["desc"] = "dato adicional"
        cols.append(item)
    return {"kind": case.kind, "confidence": 0.9, "columns": cols}


def find_case(cases, payload_text: str):
    payload = json.loads(payload_text)
    heads = [c["h"] for c in payload["columnas"]]
    for case in cases:
        if [h[:60] for h in case.headers] == heads or list(case.headers) == heads:
            return case
    return None


class DryServer:
    def __init__(self, mode: str, cases, fail_at: int):
        self.mode, self.cases, self.fail_at = mode, cases, fail_at
        self.inner_calls = 0
        self.requests: list[dict] = []

    def _text(self, payload_text: str) -> str:
        if self.mode == "malformed":
            return "esto no es json {"
        case = find_case(self.cases, payload_text)
        return json.dumps(oracle_answer(case, noisy=self.mode == "noisy") if case else {"kind": "otro", "confidence": 0.5, "columns": []})

    @staticmethod
    def _usage(prompt_text: str, out_text: str) -> dict:
        p, o = max(1, len(prompt_text) // 4), max(1, len(out_text) // 4)
        return {"promptTokenCount": p, "candidatesTokenCount": o, "thoughtsTokenCount": 40, "totalTokenCount": p + o + 40}

    async def http_handler(self, request):
        import httpx

        self.inner_calls += 1
        body = json.loads(request.content or b"{}")
        gen = body.get("generationConfig") or {}
        contents = body.get("contents") or []
        payload_text = ""
        with contextlib.suppress(Exception):
            payload_text = contents[0]["parts"][0]["text"]
        schema = gen.get("responseSchema") or gen.get("responseJsonSchema") or {}
        self.requests.append({
            "path": request.url.path.rsplit("/", 1)[-1], "host": request.url.host,
            "tools": len(body.get("tools") or []), "thinkingConfig": gen.get("thinkingConfig"),
            "maxOutputTokens": gen.get("maxOutputTokens"), "temperature": gen.get("temperature"),
            "responseMimeType": gen.get("responseMimeType"), "has_schema": bool(schema),
            "schema_kind_enum": len(((schema.get("properties") or {}).get("kind") or {}).get("enum") or []),
            "contents": len(contents), "payload_chars": len(payload_text),
            "systemInstruction_chars": len(json.dumps(body.get("systemInstruction") or {}, ensure_ascii=False)),
            "has_api_key_header": "x-goog-api-key" in request.headers,
        })
        codes = {"error429": (429, "RESOURCE_EXHAUSTED"), "error400": (400, "INVALID_ARGUMENT"),
                 "error503": (503, "UNAVAILABLE")}
        if self.mode in codes and self.inner_calls == self.fail_at:
            code, status = codes[self.mode]
            return httpx.Response(code, json={"error": {"code": code, "message": "error simulado", "status": status}})
        if self.mode == "timeout" and self.inner_calls == self.fail_at:
            await asyncio.sleep(60)
        text = self._text(payload_text)
        return httpx.Response(200, json={
            "candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}],
            "usageMetadata": self._usage(payload_text + "x" * 1600, text)})

    def fake_client(self):
        """Cliente falso SIN SDK (dry-run sin --dry-run-http)."""
        from unittest.mock import AsyncMock, MagicMock

        from google.genai import errors as genai_errors
        from tests.fake_gemini import text_response, usage

        server = self

        async def generate_content(*, model, contents, config=None):
            server.inner_calls += 1
            if server.mode in ("error429", "error400", "error503") and server.inner_calls == server.fail_at:
                code = {"error429": 429, "error400": 400, "error503": 503}[server.mode]
                cls = genai_errors.ServerError if code >= 500 else genai_errors.ClientError
                raise cls(code, {"error": {"code": code, "message": "error simulado", "status": "SIMULATED"}})
            if server.mode == "timeout" and server.inner_calls == server.fail_at:
                await asyncio.sleep(60)
            text = server._text(contents)
            u = server._usage(contents + "x" * 1600, text)
            return text_response(text, usage(u["promptTokenCount"], u["candidatesTokenCount"], u["thoughtsTokenCount"]))

        client = MagicMock(name="genai.Client()")
        client.aio.models.generate_content = generate_content
        client.aio.aclose = AsyncMock()
        return client


# ---------------------------------------------------------------------------
# Corrida
# ---------------------------------------------------------------------------

class SettingsProxy:
    """Settings reales (la clave sale de get_settings()) con topes propios del script."""

    def __init__(self, inner, **override):
        self._inner, self._override = inner, override

    def __getattr__(self, name):
        if name in self._override:
            return self._override[name]
        return getattr(self._inner, name)


def estimate_tokens(payload: str) -> dict:
    from app.services import schema_ai_service as ai

    prompt = (len(ai.SYSTEM_PROMPT) + len(payload) + 1100) // 4     # +~1100 caracteres del esquema de salida
    return {"prompt": prompt}


async def run_cases(args, settings, guard, cases, dry: DryServer | None) -> dict:
    import pandas as pd

    from app.services import intake_service as intake
    from app.services import schema_ai_service as ai

    ai.clear_memory_cache()
    budget = ai.AiBudget(ORG_ID, max_per_request=ABS_MAX_CALLS)
    rows: list[dict] = []
    for n, case in enumerate(cases, 1):
        df = pd.DataFrame(list(case.rows), columns=list(case.headers))
        prep = intake.prepare_sheet(df)
        before = guard.calls
        started = time.monotonic()
        und = await ai.understand(ORG_ID, prep.profiles, sheet_name=case.sheet, file_name=case.file, budget=budget,
                                  org_tables=[])
        latency = int((time.monotonic() - started) * 1000)
        got_roles = [c.role for c in und.columns]
        hits = sum(1 for a, b in zip(got_roles, case.roles) if a == b)
        usage = und.usage or {}
        called = guard.calls - before
        payload = ai.build_payload(case.sheet, prep.profiles)
        row = {
            "id": case.id, "expected_kind": case.kind, "got_kind": und.kind, "kind_ok": und.kind == case.kind,
            "roles_ok": hits, "roles_total": len(case.roles), "got_roles": got_roles, "expected_roles": list(case.roles),
            "source": "cache" if und.from_cache else und.source, "model_called": bool(called), "confidence": und.kind_confidence,
            "needs_review": und.needs_review, "ai_error": und.ai_error,
            "tokens": {"prompt": usage.get("prompt_tokens", 0), "output": usage.get("output_tokens", 0),
                       "thoughts": usage.get("thoughts_tokens", 0), "total": usage.get("total_tokens", 0)},
            "estimate_chars_div_4": estimate_tokens(payload) | {"payload_chars": len(payload)},
            "latency_ms": latency, "note": case.note,
            "unexpected_call": case.expect_model is False and bool(called),
        }
        rows.append(row)
        say(f"  [{n:>2}/{len(cases)}] {case.id:26} kind {'OK ' if row['kind_ok'] else 'MAL'} "
            f"({case.kind} -> {und.kind}) roles {hits}/{len(case.roles)} fuente={row['source']:9} "
            f"tokens={row['tokens']['prompt']}+{row['tokens']['output']}+{row['tokens']['thoughts']}"
            + (f" error_ia={und.ai_error}" if und.ai_error else ""))
    return summarize(rows, guard, args, dry)


def summarize(rows: list[dict], guard, args, dry) -> dict:
    model_rows = [r for r in rows if r["model_called"]]
    det_rows = [r for r in rows if r["source"] == "heuristic" and not r["model_called"]]
    tot = lambda key: sum(r["tokens"][key] for r in model_rows)       # noqa: E731
    calls = len(model_rows)
    summary = {
        "sheets": len(rows), "gemini_calls": guard.calls, "http_requests": guard.http_calls,
        "kind_accuracy": round(sum(r["kind_ok"] for r in rows) / len(rows), 3) if rows else None,
        "roles_accuracy": round(sum(r["roles_ok"] for r in rows) / max(1, sum(r["roles_total"] for r in rows)), 3),
        "resolved_without_model": len(det_rows), "resolved_with_model": calls,
        "from_cache": sum(1 for r in rows if r["source"] == "cache"),
        "kind_accuracy_model_sheets": round(sum(r["kind_ok"] for r in model_rows) / calls, 3) if calls else None,
        "roles_accuracy_model_sheets": round(sum(r["roles_ok"] for r in model_rows) / max(1, sum(r["roles_total"] for r in model_rows)), 3) if calls else None,
        "kind_accuracy_deterministic_sheets": round(sum(r["kind_ok"] for r in det_rows) / len(det_rows), 3) if det_rows else None,
        "unexpected_calls": [r["id"] for r in rows if r["unexpected_call"]],
        "failures": [{"id": r["id"], "ai_error": r["ai_error"]} for r in rows if r["ai_error"]],
        "tokens_total": {"prompt": tot("prompt"), "output": tot("output"), "thoughts": tot("thoughts"), "total": tot("total")},
    }
    if calls:
        avg = {k: round(tot(k) / calls) for k in ("prompt", "output", "thoughts", "total")}
        # 8 hojas por organizacion: la fraccion ambigua observada en este set; las repetidas cuestan 0.
        frac_ambiguous = calls / len(rows)
        per_org = {k: round(SHEETS_PER_ORG * frac_ambiguous * avg[k]) for k in avg}
        summary["tokens_per_ambiguous_sheet_avg"] = avg
        summary["projection_per_org"] = {
            "sheets": SHEETS_PER_ORG, "assumed_ambiguous_fraction": round(frac_ambiguous, 3), "tokens": per_org,
            "worst_case_all_ambiguous": {k: SHEETS_PER_ORG * avg[k] for k in avg},
            "note": "el set de prueba esta cargado de casos dificiles a proposito: una organizacion real tiene menos hojas ambiguas",
        }
        if args.price_in is not None and args.price_out is not None:
            def usd(t):
                return round((t["prompt"] * args.price_in + (t["output"] + t["thoughts"]) * args.price_out) / 1e6, 6)

            summary["projection_per_org"]["usd_per_org"] = usd(per_org)
            summary["projection_per_org"]["usd_worst_case"] = usd({k: SHEETS_PER_ORG * avg[k] for k in avg})
            summary["prices_usd_per_million"] = {"in": args.price_in, "out": args.price_out}
    est = [r["estimate_chars_div_4"]["prompt"] for r in model_rows] or [r["estimate_chars_div_4"]["prompt"] for r in rows if r["source"] != "cache" and r["expected_kind"] != "x"]
    summary["estimated_prompt_tokens_chars_div_4"] = {"min": min(est), "max": max(est), "avg": round(sum(est) / len(est))} if est else None
    return summary


def write_report(path: Path, meta: dict, rows_summary: dict | None, guard, aborted: dict | None, dry) -> None:
    data = {"meta": meta, "summary": rows_summary, "aborted": aborted,
            "gemini_calls": [{k: v for k, v in r.items() if k != "function_calls"} for r in guard.records]}
    if dry is not None:
        data["dry_run_requests"] = dry.requests
    path.write_text(redact(json.dumps(data, ensure_ascii=False, indent=2, default=str)), encoding="utf-8")


def parse_args(argv=None):
    class _Parser(argparse.ArgumentParser):
        def error(self, message):
            self.print_usage(sys.stderr)
            self.exit(EXIT_CONFIG, f"{self.prog}: error: {message}\n")

    p = _Parser(description="Valida el agente de esquema contra Gemini real con topes de gasto por codigo.")
    p.add_argument("--dry-run", action="store_true", help="servidor falso, sin red ni clave")
    p.add_argument("--dry-run-mode", choices=MODES, default="normal")
    p.add_argument("--dry-run-http", action="store_true", help="solo con --dry-run: SDK REAL sobre un transporte httpx falso")
    p.add_argument("--dry-run-fail-at", type=int, default=3, help="n-esima llamada en la que falla el dry-run (default 3)")
    p.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS, help="tope duro de llamadas (default 15, maximo 50)")
    p.add_argument("--i-know-this-spends-money", action="store_true", help=f"permite --max-calls > {DEFAULT_MAX_CALLS}")
    p.add_argument("--sheets", help="ids de tests/intake_corpus.py separados por coma (default: todas)")
    p.add_argument("--out", help="JSON de salida (default: <temp>/intake_smoke_<fecha>[_dry].json)")
    p.add_argument("--price-in", type=float, help="USD por millon de tokens de ENTRADA (para proyectar el costo)")
    p.add_argument("--price-out", type=float, help="USD por millon de tokens de SALIDA (incluye razonamiento)")
    args = p.parse_args(argv)
    if args.max_calls < 1 or args.max_calls > ABS_MAX_CALLS:
        p.error(f"--max-calls debe estar entre 1 y {ABS_MAX_CALLS}")
    if args.max_calls > DEFAULT_MAX_CALLS and not args.i_know_this_spends_money:
        p.error(f"--max-calls > {DEFAULT_MAX_CALLS} exige --i-know-this-spends-money")
    if (args.dry_run_mode != "normal" or args.dry_run_http) and not args.dry_run:
        p.error("--dry-run-mode y --dry-run-http solo con --dry-run")
    return args


async def amain(args, settings, out: Path):
    import httpx

    from app.services import schema_ai_service as ai

    cases = load_corpus(args.sheets)
    guard = smoke.CallGuard(args.max_calls)
    guard.scenario = 0
    patches = smoke.Patches()
    dry = DryServer(args.dry_run_mode, cases, args.dry_run_fail_at) if args.dry_run else None
    meta = {"mode": "dry-run" if args.dry_run else "REAL", "dry_run_mode": args.dry_run_mode if args.dry_run else None,
            "dry_run_http": bool(args.dry_run and args.dry_run_http), "model": settings.GEMINI_MODEL,
            "max_calls": args.max_calls, "sheets": [c.id for c in cases], "thinking_level": "low",
            "stamp": datetime.datetime.now().isoformat(timespec="seconds")}
    override = {"INTAKE_AI_ENABLED": True, "INTAKE_AI_MAX_CALLS_PER_ORG_HOUR": 0,
                "INTAKE_AI_MAX_CALLS_PER_REQUEST": ABS_MAX_CALLS}
    if args.dry_run and args.dry_run_mode == "timeout":
        override["INTAKE_AI_TIMEOUT_SECONDS"] = 2.0
    proxy = SettingsProxy(settings, **override)
    summary, aborted = None, None
    patches.setattr(ai, "get_settings", lambda: proxy)
    try:
        smoke.install_http_guard(guard, patches)
        if args.dry_run and not args.dry_run_http:
            from google import genai

            fake = dry.fake_client()
            real_generate = fake.aio.models.generate_content

            async def counted(*, model, contents, config=None):
                return await guard.call(lambda: real_generate(model=model, contents=contents, config=config))

            fake.aio.models.generate_content = counted
            patches.setattr(genai, "Client", lambda *a, **k: fake)
        else:
            from google.genai import models as gmodels

            smoke.install_client_factory(
                patches, expect_key=settings.GOOGLE_API_KEY,
                transport=httpx.MockTransport(dry.http_handler) if args.dry_run else None)
            original = gmodels.AsyncModels.generate_content

            async def guarded(self, *, model, contents, config=None):
                return await guard.call(lambda: original(self, model=model, contents=contents, config=config))

            patches.setattr(gmodels.AsyncModels, "generate_content", guarded)
        say(f"Hojas del set: {len(cases)} | tope de llamadas={args.max_calls}")
        summary = await run_cases(args, settings, guard, cases, dry)
        exit_code = EXIT_OK
    except smoke.RunAborted as exc:
        aborted = {"kind": exc.kind, "detail": exc.detail}
        say(f"ABORTADO: {exc.detail}")
        exit_code = exc.exit_code
    finally:
        patches.close()
        write_report(out, meta, summary, guard, aborted, dry)
    return exit_code, summary, guard, dry


def print_summary(summary: dict | None, guard, dry) -> None:
    if not summary:
        return
    say("\n=== RESUMEN ===")
    for key in ("sheets", "gemini_calls", "http_requests", "resolved_without_model", "resolved_with_model", "from_cache",
                "kind_accuracy", "roles_accuracy", "kind_accuracy_model_sheets", "roles_accuracy_model_sheets",
                "kind_accuracy_deterministic_sheets", "unexpected_calls", "failures", "tokens_total",
                "tokens_per_ambiguous_sheet_avg", "estimated_prompt_tokens_chars_div_4"):
        if key in summary:
            say(f"  {key}: {summary[key]}")
    if "projection_per_org" in summary:
        say(f"  projection_per_org: {json.dumps(summary['projection_per_org'], ensure_ascii=False)}")
    if dry is not None and dry.requests:
        r = dry.requests[0]
        say(f"[dry-run-http] primera peticion que el SDK REAL enviaria: host={r['host']} metodo={r['path']} "
            f"mime={r['responseMimeType']} esquema={r['has_schema']} (enum de tipos={r['schema_kind_enum']}) "
            f"thinking={r['thinkingConfig']} maxOut={r['maxOutputTokens']} temp={r['temperature']} tools={r['tools']} "
            f"payload_chars={r['payload_chars']} sys_chars={r['systemInstruction_chars']} api_key_en_header={r['has_api_key_header']}")


def main(argv=None) -> int:
    args = parse_args(argv)
    smoke.setup_logging()
    say(f"Smoke agente de esquema | modo={'DRY-RUN' if args.dry_run else 'REAL'} | tope de llamadas={args.max_calls}")
    try:
        settings = smoke.load_settings(SimpleNamespace(dry_run=args.dry_run, dry_run_mode="normal"))
    except smoke.RunAborted as exc:
        say(f"ERROR de configuracion: {exc.detail}")
        return EXIT_CONFIG
    key = (settings.GOOGLE_API_KEY or "").strip()
    if not key or key == "tu-google-api-key":
        say("ERROR: GOOGLE_API_KEY esta vacia o es la de ejemplo en Settings (.env/entorno). No se llamo a nada.")
        return EXIT_CONFIG
    smoke._SECRETS.append(settings.GOOGLE_API_KEY)
    say(f"Config: modelo={settings.GEMINI_MODEL} razonamiento=low api_key_presente=si")
    net = smoke.Patches()
    if args.dry_run:
        smoke.install_network_guard(net)
        say("DRY-RUN: red no-loopback bloqueada por codigo; ninguna llamada a Gemini es posible.")
    out = Path(args.out) if args.out else Path(tempfile.gettempdir()) / (
        f"intake_smoke_{datetime.datetime.now():%Y%m%d_%H%M%S}{'_dry' if args.dry_run else ''}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        exit_code, summary, guard, dry = asyncio.run(amain(args, settings, out))
    except KeyboardInterrupt:
        say("Interrumpido por el usuario.")
        return EXIT_ERROR
    except smoke.RunAborted as exc:
        say(f"ABORTADO: {exc.detail}")
        return exc.exit_code
    finally:
        net.close()
    print_summary(summary, guard, dry)
    say(f"JSON: {out}")
    say(f"Codigo de salida: {exit_code}")
    say(f"TOTAL: llamadas a Gemini {guard.calls}/{args.max_calls} | http {guard.http_calls}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
