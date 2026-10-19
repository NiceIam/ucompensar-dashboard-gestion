"""Router /api/v1/intake y PUT /api/v1/schema/tables/{id}/roles — PI0320251.

De punta a punta con TestClient: sesion, validacion estricta del plan, errores humanos, aislamiento por organizacion
y topes. BD emulada y Gemini ausente (sin clave).
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
from app.services import schema_ai_service as ai
from tests.fake_org_db import FakeOrgDBs
from tests.test_intake_service import ORG_A, ORG_B, VENTAS_CSV, INVENTARIO_CSV

USER_A = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def env():
    ai.clear_memory_cache()
    dbs = FakeOrgDBs()
    settings = SimpleNamespace(GOOGLE_API_KEY="", GEMINI_MODEL="m", INTAKE_AI_ENABLED=True, INTAKE_AI_TIMEOUT_SECONDS=5.0,
                               INTAKE_AI_MAX_OUTPUT_TOKENS=1200, INTAKE_THINKING_LEVEL="low",
                               INTAKE_AI_MAX_CALLS_PER_REQUEST=8, INTAKE_AI_MAX_CALLS_PER_ORG_HOUR=40)
    with patch("app.services.schema_agent_service.get_org_pool", dbs.get_org_pool), \
            patch("app.services.schema_ai_service.get_settings", return_value=settings):
        yield dbs
    ai.clear_memory_cache()


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from app.auth import limiter

    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def as_user(app):
    def _login(org_id: str = ORG_A, user_id: str = USER_A):
        user = CurrentUser(user_id=user_id, org_id=org_id, email="u@example.com", role="admin")
        app.dependency_overrides[get_current_user] = lambda: user

    yield _login
    app.dependency_overrides.pop(get_current_user, None)


def files(*pairs):
    return [("files", (name, content.encode("utf-8"), "text/csv")) for name, content in pairs]


class TestAnalyze:
    def test_sin_sesion_401(self, client: TestClient, env):
        client.cookies.clear()
        assert client.post("/api/v1/intake/analyze", files=files(("v.csv", VENTAS_CSV))).status_code == 401

    def test_varios_archivos_en_una_llamada(self, client, env, as_user):
        as_user()
        resp = client.post("/api/v1/intake/analyze", files=files(("ventas.csv", VENTAS_CSV), ("inventario.csv", INVENTARIO_CSV)))
        assert resp.status_code == 200
        body = resp.json()
        kinds = [f["sheets"][0]["kind"] for f in body["files"]]
        assert kinds == ["ventas", "productos"]
        s = body["files"][0]["sheets"][0]
        assert set(s) >= {"key", "sheet_name", "status", "rows", "columns_count", "kind", "kind_label", "kind_confidence",
                          "mapping_source", "needs_review", "review_reasons", "summary", "kind_phrase", "stats", "period",
                          "columns", "kinds", "allowed_roles", "tokens", "signature", "destination"}
        assert set(s["columns"][0]) == {"index", "name", "original_name", "role", "role_label", "explain", "confidence",
                                        "type", "sample", "source"}
        assert env.db(ORG_A).tables == {}

    def test_sin_archivos_422(self, client, env, as_user):
        as_user()
        assert client.post("/api/v1/intake/analyze").status_code == 422

    def test_archivo_roto_no_es_500(self, client, env, as_user):
        as_user()
        resp = client.post("/api/v1/intake/analyze", files=[("files", ("x.xlsx", b"no", "application/octet-stream"))])
        assert resp.status_code == 200 and resp.json()["files"][0]["error"]["code"] == "unreadable"

    def test_freno_por_usuario(self, client, env, as_user):
        as_user()
        codes = [client.post("/api/v1/intake/analyze", files=files(("v.csv", VENTAS_CSV))).status_code for _ in range(22)]
        assert codes[:20] == [200] * 20 and codes[20] == 429
        detail = client.post("/api/v1/intake/analyze", files=files(("v.csv", VENTAS_CSV))).json()["detail"]
        assert detail["code"] == "rate_limit_user" and "subiendo archivos muy rápido" in detail["message"]


class TestCommit:
    def _plan(self, **over):
        item = {"file_name": "ventas.csv", "sheet_name": None, "action": "create", "display_name": "Mis ventas"}
        item.update(over)
        return json.dumps({"sheets": [item]})

    def test_guarda_y_devuelve_resultado_por_hoja(self, client, env, as_user):
        as_user()
        resp = client.post("/api/v1/intake/commit", files=files(("ventas.csv", VENTAS_CSV)), data={"plan": self._plan()})
        assert resp.status_code == 200
        body = resp.json()
        r = body["results"][0]
        assert r["status"] == "created" and r["rows_inserted"] == 3 and r["display_name"] == "Mis ventas"
        assert r["kind"] == "ventas" and body["totals"]["created"] == 1
        assert len(env.db(ORG_A).tables) == 1 and env.db(ORG_B).tables == {}

    @pytest.mark.parametrize("plan", ["no es json", "[]", "{}", '{"sheets": []}',
                                      '{"sheets": [{"file_name": "a", "action": "borrar"}]}',
                                      '{"sheets": [{"file_name": "a", "action": "create", "extra": 1}]}',
                                      '{"sheets": [{"file_name": "a", "action": "create", "columns": [{"name": "x", "role": "y", "confidence": 5}]}]}'])
    def test_plan_invalido_422_con_mensaje_humano(self, client, env, as_user, plan):
        as_user()
        resp = client.post("/api/v1/intake/commit", files=files(("ventas.csv", VENTAS_CSV)), data={"plan": plan})
        assert resp.status_code == 422
        assert resp.json()["detail"] == "No entendí qué querías guardar. Vuelve a subir los archivos."
        assert env.db(ORG_A).tables == {}

    def test_sin_sesion_401(self, client, env):
        client.cookies.clear()
        assert client.post("/api/v1/intake/commit", files=files(("v.csv", VENTAS_CSV)), data={"plan": self._plan()}).status_code == 401

    def test_append_a_tabla_de_otra_org_es_un_error_de_la_hoja_no_una_fuga(self, client, env, as_user):
        tid = env.db(ORG_B).add_table("ventas", ["fecha", "producto", "cantidad", "total"], [], display_name="V")
        as_user(ORG_A)
        resp = client.post("/api/v1/intake/commit", files=files(("ventas.csv", VENTAS_CSV)),
                           data={"plan": self._plan(action="append", table_id=str(tid))})
        assert resp.status_code == 200 and resp.json()["results"][0]["error"]["code"] == "table_not_found"
        assert env.db(ORG_B).rows_of(tid) == []


class TestRolesEndpoint:
    def _crear(self, client, env):
        resp = client.post("/api/v1/intake/commit", files=files(("hoja.csv", "C1,C2,C3,C4\n2026-05-02,Gasas,3,1500\n")),
                           data={"plan": json.dumps({"sheets": [{"file_name": "hoja.csv", "action": "create"}]})})
        return resp.json()["results"][0]["table_id"]

    def test_corrige_roles(self, client, env, as_user):
        as_user()
        tid = self._crear(client, env)
        resp = client.put(f"/api/v1/schema/tables/{tid}/roles", json={"kind": "ventas", "roles": {"c1": "fecha", "c4": "total"}})
        assert resp.status_code == 200
        body = resp.json()
        assert body["kind"] == "ventas" and body["mapping_source"] == "user"
        assert {c["name"]: c["role"] for c in body["columns"]}["c4"] == "total"

    @pytest.mark.parametrize("body,status", [
        ({"kind": "ventas", "roles": {"c1": "costo_unitario"}}, 422),
        ({"kind": "inventado", "roles": {}}, 422),
        ({"roles": {"zzz": "fecha"}}, 422),
        ({"kind": "ventas", "roles": {"c1": "fecha", "c2": "fecha"}}, 422),
    ])
    def test_errores_humanos(self, client, env, as_user, body, status):
        as_user()
        tid = self._crear(client, env)
        resp = client.put(f"/api/v1/schema/tables/{tid}/roles", json=body)
        assert resp.status_code == status and isinstance(resp.json()["detail"], str)

    def test_tabla_inexistente_ajena_o_mal_formada_404(self, client, env, as_user):
        as_user()
        tid = self._crear(client, env)
        assert client.put("/api/v1/schema/tables/basura/roles", json={"roles": {}}).status_code == 404
        assert client.put("/api/v1/schema/tables/00000000-0000-0000-0000-000000000000/roles", json={"roles": {}}).status_code == 404
        as_user(ORG_B)
        assert client.put(f"/api/v1/schema/tables/{tid}/roles", json={"roles": {"c1": "fecha"}, "kind": "ventas"}).status_code == 404

    def test_sin_sesion_401(self, client, env):
        client.cookies.clear()
        assert client.put("/api/v1/schema/tables/00000000-0000-0000-0000-000000000000/roles", json={"roles": {}}).status_code == 401


class TestUndoEndpoint:
    def _dos_cargas(self, client, env):
        plan = lambda: json.dumps({"sheets": [{"file_name": "v.csv", "sheet_name": None, "action": "create", "display_name": "V"}]})
        client.post("/api/v1/intake/commit", files=files(("v.csv", VENTAS_CSV)), data={"plan": plan()})
        tid = str(next(iter(env.db(ORG_A).tables)))
        plan2 = json.dumps({"sheets": [{"file_name": "v2.csv", "sheet_name": None, "action": "append", "table_id": tid}]})
        resp = client.post("/api/v1/intake/commit", files=files(("v2.csv", VENTAS_CSV.replace("Ana", "Eva"))), data={"plan": plan2})
        return tid, resp.json()["results"][0]

    def test_deshace_la_carga(self, client, env, as_user):
        as_user()
        tid, r = self._dos_cargas(client, env)
        assert r["status"] == "appended"
        resp = client.post("/api/v1/intake/undo", json={"table_id": tid, "loaded_at": r["undo"]["loaded_at"]})
        assert resp.status_code == 200 and resp.json() == {"table_id": tid, "rows_deleted": 3, "total_rows": 3}

    @pytest.mark.parametrize("body,status", [
        ({"table_id": "no-uuid", "loaded_at": "2026-10-19T12:00:00+00:00"}, 404),
        ({"table_id": "00000000-0000-0000-0000-000000000000", "loaded_at": "2026-10-19T12:00:00+00:00"}, 404),
        ({"table_id": "00000000-0000-0000-0000-000000000000", "loaded_at": "x"}, 422),
        ({"table_id": "00000000-0000-0000-0000-000000000000"}, 422),
        ({"table_id": "00000000-0000-0000-0000-000000000000", "loaded_at": "2026-10-19T12:00:00+00:00", "extra": 1}, 422),
    ])
    def test_errores(self, client, env, as_user, body, status):
        as_user()
        assert client.post("/api/v1/intake/undo", json=body).status_code == status

    def test_otra_org_no_puede_deshacer(self, client, env, as_user):
        as_user(ORG_A)
        tid, r = self._dos_cargas(client, env)
        as_user(ORG_B)
        resp = client.post("/api/v1/intake/undo", json={"table_id": tid, "loaded_at": r["undo"]["loaded_at"]})
        assert resp.status_code == 404
        assert env.db(ORG_A).tables[next(iter(env.db(ORG_A).tables))]["row_count"] == 6

    def test_sin_sesion_401(self, client, env):
        client.cookies.clear()
        assert client.post("/api/v1/intake/undo", json={"table_id": "x", "loaded_at": "2026-10-19T12:00:00+00:00"}).status_code == 401
