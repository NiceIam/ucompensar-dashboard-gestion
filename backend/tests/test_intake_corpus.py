"""Hojas desordenadas con verdad esperada (tests/intake_corpus.py) y el script de validacion con Gemini real — PI0320251.

1. El paso determinista NUNCA debe declarar "claro" un tipo equivocado (si lo hiciera, el modelo ni se consultaria y
   el error quedaria guardado): invariante sobre todo el set.
2. Los controles se resuelven sin modelo y las hojas dificiles SI quedan para el modelo.
3. El script scripts/intake_smoke_real_gemini.py se ejecuta SOLO en --dry-run (sin red ni clave): topes, parada ante
   el primer 4xx, cuerpo que el SDK real enviaria, y se niega a correr sin clave.
"""

import json
import os
import subprocess
import sys
import warnings
from pathlib import Path

import pandas as pd
import pytest

from app.services import intake_service as intake
from app.services import schema_understanding as su
from tests.intake_corpus import BY_ID, CASES

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "intake_smoke_real_gemini.py"


def deterministic(case):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        prep = intake.prepare_sheet(pd.DataFrame(list(case.rows), columns=list(case.headers)))
    return su.understand_deterministic(prep.profiles, sheet_name=case.sheet, file_name=case.file)


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_el_determinista_nunca_declara_claro_un_tipo_equivocado(case):
    u = deterministic(case)
    if u.clear:
        assert u.kind == case.kind, f"{case.id}: claro pero {u.kind} != {case.kind}"
        wrong = [(c.original, c.role, e) for c, e in zip(u.columns, case.roles) if c.role != e and c.role != "otro"]
        assert not wrong, f"{case.id}: roles claros equivocados {wrong}"


def test_controles_sin_modelo_y_dificiles_con_modelo():
    for case in CASES:
        if case.expect_model is False:
            u = deterministic(case)
            assert u.clear and u.kind == case.kind, case.id
    must_ask = ["tienda_generica", "tienda_generica_repetida", "drogueria_inventario", "taller_ordenes", "fiados_tienda",
                "empleados_nomina", "inyeccion_en_celdas"]
    for cid in must_ask:
        assert not deterministic(BY_ID[cid]).clear, cid


def test_set_cubre_rubros_y_los_ocho_tipos_de_hoja_y_tiene_entre_diez_y_veinte_hojas():
    assert 10 <= len(CASES) <= 20
    assert {c.kind for c in CASES} == {"productos", "ventas", "compras", "cuentas_por_cobrar", "movimientos_inventario",
                                       "clientes", "proveedores", "otro"}
    for c in CASES:
        assert len(c.headers) == len(c.roles) and all(len(r) == len(c.headers) for r in c.rows), c.id


def run_script(*args, env_extra=None):
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run([sys.executable, "-I", str(SCRIPT), *args], capture_output=True, text=True, env=env,
                          cwd=str(BACKEND), timeout=180, encoding="utf-8", errors="replace")


def test_script_en_seco_ok_y_sin_gastar_mas_de_una_llamada_por_hoja_ambigua(tmp_path):
    out = tmp_path / "r.json"
    r = run_script("--dry-run", "--out", str(out))
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    data = json.loads(out.read_text(encoding="utf-8"))
    s = data["summary"]
    assert s["kind_accuracy"] == 1.0 and s["roles_accuracy"] == 1.0 and s["unexpected_calls"] == []
    ambiguas = sum(1 for c in CASES if not deterministic(c).clear)
    assert s["gemini_calls"] == s["resolved_with_model"] == ambiguas - s["from_cache"] and s["from_cache"] == 1
    assert data["meta"]["mode"] == "dry-run" and "dry-run-fake-key" not in out.read_text(encoding="utf-8").replace("dry-run-fake-key-not-a-secret", "")


def test_script_parada_inmediata_ante_el_primer_4xx(tmp_path):
    out = tmp_path / "r.json"
    r = run_script("--dry-run", "--dry-run-mode", "error400", "--dry-run-fail-at", "2", "--out", str(out))
    assert r.returncode == 2
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["aborted"]["kind"] == "http_4xx" and len(data["gemini_calls"]) == 2          # ni una llamada despues del 4xx


def test_script_tope_duro_de_llamadas(tmp_path):
    out = tmp_path / "r.json"
    r = run_script("--dry-run", "--dry-run-mode", "overbudget", "--max-calls", "2", "--out", str(out))
    assert r.returncode == 3 and "TOPE DE LLAMADAS" in r.stdout
    assert len(json.loads(out.read_text(encoding="utf-8"))["gemini_calls"]) == 2


def test_script_con_el_sdk_real_sobre_transporte_falso_envia_la_peticion_esperada(tmp_path):
    out = tmp_path / "r.json"
    r = run_script("--dry-run", "--dry-run-http", "--out", str(out))
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    data = json.loads(out.read_text(encoding="utf-8"))
    reqs = data["dry_run_requests"]
    assert reqs and len(reqs) == data["summary"]["gemini_calls"] == data["summary"]["http_requests"]
    for q in reqs:
        assert q["host"] == "generativelanguage.googleapis.com" and q["path"].endswith(":generateContent")
        assert q["responseMimeType"] == "application/json" and q["has_schema"] and q["schema_kind_enum"] == 8
        assert q["thinkingConfig"] == {"thinking_level": "LOW"} and q["tools"] == 0 and q["temperature"] == 0.0
        assert q["maxOutputTokens"] == 1200 and q["contents"] == 1 and q["has_api_key_header"]
        assert q["payload_chars"] < 3000                                  # nunca el archivo completo


def test_script_real_sin_clave_no_llama_a_nada():
    r = run_script("--out", str(Path(tempfile_dir()) / "x.json"), env_extra={"GOOGLE_API_KEY": ""})
    assert r.returncode == 5 and "GOOGLE_API_KEY esta vacia" in r.stdout


def test_script_pide_confirmacion_para_mas_de_15_llamadas_y_nunca_mas_de_50():
    assert run_script("--dry-run", "--max-calls", "16").returncode == 5
    assert run_script("--dry-run", "--max-calls", "51", "--i-know-this-spends-money").returncode == 5


def tempfile_dir() -> str:
    import tempfile

    return tempfile.gettempdir()
