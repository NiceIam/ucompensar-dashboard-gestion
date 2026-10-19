"""Router /api/v1/dashboards: lista, detalle, execute, suggest, borrado por rol — PI0320251.

BD emulada, sin red. Los scripts .py ya no existen: sus rutas devuelven 404/405.
"""

import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
from tests.dash_support import ORG_A, ORG_B, env, gemini, load_ferreteria, settings_stub  # noqa: F401

USER = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def login(app):
    def _login(org_id: str = ORG_A, role: str = "owner"):
        user = CurrentUser(user_id=USER, org_id=org_id, email="u@example.com", role=role)
        app.dependency_overrides[get_current_user] = lambda: user

    yield _login
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def api(client: TestClient, login, env):  # noqa: F811
    login()
    load_ferreteria(env.dbs.db(ORG_A))
    env.settings.GOOGLE_API_KEY = ""
    return client


class TestSugerirYListar:
    def test_suggest_crea_y_la_lista_trae_lo_necesario_para_las_tarjetas(self, api):
        out = api.post("/api/v1/dashboards/suggest", json={"auto": True}).json()
        assert out["status"] == "created" and out["source"] == "rules"
        assert [d["name"] for d in out["dashboards"]] == ["Resumen de Ventas", "Resumen de Productos"]

        items = api.get("/api/v1/dashboards").json()
        assert len(items) == 2
        ventas = next(d for d in items if d["name"] == "Resumen de Ventas")
        assert ventas["widget_count"] == 5 and ventas["source"] == "rules" and ventas["preview"]["type"] == "line"
        assert ventas["highlights"] and ventas["description"].startswith("Sugerido")

    def test_suggest_sin_cuerpo_tambien_funciona_y_es_idempotente(self, api):
        first = api.post("/api/v1/dashboards/suggest").json()
        second = api.post("/api/v1/dashboards/suggest").json()
        assert first["status"] == "created" and second["status"] == "exists"
        assert len(api.get("/api/v1/dashboards").json()) == 2

    def test_suggest_auto_con_tableros_existentes_no_hace_nada(self, api, env):
        env.dbs.db(ORG_A).add_dashboard("uno")
        assert api.post("/api/v1/dashboards/suggest", json={"auto": True}).json()["status"] == "has_dashboards"

    def test_suggest_sin_datos(self, client, login, env):
        login(ORG_B)
        assert client.post("/api/v1/dashboards/suggest", json={"auto": True}).json()["status"] == "no_data"

    def test_execute_calcula_el_tablero(self, api):
        board = api.post("/api/v1/dashboards/suggest").json()["dashboards"][0]
        out = api.post(f"/api/v1/dashboards/{board['id']}/execute").json()
        assert out["legacy"] is False
        assert {k["label"]: k["value"] for k in out["kpis"]}["Suma de total"] == 10_234_700

    def test_execute_de_un_tablero_inexistente_o_de_otra_org_es_404(self, api, env, login):
        board = api.post("/api/v1/dashboards/suggest").json()["dashboards"][0]
        assert api.post("/api/v1/dashboards/00000000-0000-4000-8000-000000000000/execute").status_code == 404
        login(ORG_B)
        assert api.post(f"/api/v1/dashboards/{board['id']}/execute").status_code == 404

    def test_el_detalle_trae_los_widgets_con_su_especificacion(self, api):
        board = api.post("/api/v1/dashboards/suggest").json()["dashboards"][0]
        detail = api.get(f"/api/v1/dashboards/{board['id']}").json()
        assert len(detail["widgets"]) == 5
        assert all(w["data_source_query"]["v"] == 1 for w in detail["widgets"])

    @pytest.mark.parametrize("path", ["script", "script/download"])
    def test_las_rutas_de_script_ya_no_existen(self, api, path):
        board = api.post("/api/v1/dashboards/suggest").json()["dashboards"][0]
        assert api.get(f"/api/v1/dashboards/{board['id']}/{path}").status_code in (404, 405)


class TestBorrado:
    def test_owner_y_admin_borran_y_el_tablero_deja_de_listarse(self, api, login, env):
        board = api.post("/api/v1/dashboards/suggest").json()["dashboards"][0]
        assert api.delete(f"/api/v1/dashboards/{board['id']}").status_code == 200
        assert board["id"] not in [d["dashboard_id"] for d in api.get("/api/v1/dashboards").json()]
        assert api.delete(f"/api/v1/dashboards/{board['id']}").status_code == 404

    @pytest.mark.parametrize("role", ["viewer", "member", ""])
    def test_otros_roles_no_borran(self, api, login, role):
        board = api.post("/api/v1/dashboards/suggest").json()["dashboards"][0]
        login(ORG_A, role)
        assert api.delete(f"/api/v1/dashboards/{board['id']}").status_code == 403
        assert len(api.get("/api/v1/dashboards").json()) == 2
