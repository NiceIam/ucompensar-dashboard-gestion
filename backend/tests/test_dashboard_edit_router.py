"""Router de deshacer y versiones de ediciones de tableros — PI0320251.

POST /api/v1/dashboards/{id}/undo-edit y GET /api/v1/dashboards/{id}/versions. BD emulada, sin red.
La edicion se aplica con el servicio (el mismo camino que la herramienta del chat); aqui se prueba el contrato REST:
codigos de estado, cuerpo, roles, aislamiento entre organizaciones y que el borrado de tableros sigue restringido.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
from tests.dash_support import ORG_A, ORG_B, env, gemini, settings_stub  # noqa: F401
from tests.test_dashboard_edit import W_CONTEO, W_METODO, make_board, run, state

USER = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def login(app):
    def _login(org_id: str = ORG_A, role: str = "member"):
        user = CurrentUser(user_id=USER, org_id=org_id, email="u@example.com", role=role)
        app.dependency_overrides[get_current_user] = lambda: user

    yield _login
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def api(client: TestClient, login, env):  # noqa: F811
    login()
    return client


def undo(api, board, version, **extra):
    return api.post(f"/api/v1/dashboards/{board}/undo-edit", json={"version": str(version), **extra})


class TestDeshacer:
    async def test_deshacer_restaura_y_responde_con_el_resumen(self, api, env):
        db, bid, *_ = await make_board(env)
        before = state(db, bid)
        e = await run(env, "Ventas por día", [{"op": "rename", "title": "Nuevo"}, {"op": "add_widget", "spec": W_METODO}])
        res = undo(api, bid, e["version"])
        assert res.status_code == 200
        assert res.json() == {"id": str(bid), "name": "Ventas por día", "widgets": 3, "discarded_newer": 0}
        assert state(db, bid) == before
        listed = api.get("/api/v1/dashboards").json()
        assert [d["name"] for d in listed] == ["Ventas por día"] and listed[0]["widget_count"] == 3

    async def test_cualquier_miembro_puede_deshacer_igual_que_pedir_la_edicion(self, api, env, login):
        db, bid, *_ = await make_board(env)
        for role in ("owner", "admin", "member", "viewer"):
            e = await run(env, "Ventas por día", [{"op": "add_widget", "spec": W_METODO}])
            login(ORG_A, role)
            assert undo(api, bid, e["version"]).status_code == 200

    async def test_el_borrado_de_tableros_sigue_restringido_a_owner_y_admin(self, api, env, login):
        db, bid, *_ = await make_board(env)
        login(ORG_A, "member")
        assert api.delete(f"/api/v1/dashboards/{bid}").status_code == 403
        login(ORG_A, "owner")
        assert api.delete(f"/api/v1/dashboards/{bid}").status_code == 200

    async def test_version_inexistente_ya_usada_o_mal_formada_es_404(self, api, env):
        db, bid, *_ = await make_board(env)
        e = await run(env, "Ventas por día", [{"op": "add_widget", "spec": W_METODO}])
        assert undo(api, bid, e["version"]).status_code == 200
        again = undo(api, bid, e["version"])
        assert again.status_code == 404 and "ya no se puede deshacer" in again.json()["detail"]
        for version in ("no-es-uuid", str(uuid.uuid4())):
            assert undo(api, bid, version).status_code == 404

    async def test_tablero_inexistente_o_borrado_es_404(self, api, env):
        db, bid, *_ = await make_board(env)
        e = await run(env, "Ventas por día", [{"op": "add_widget", "spec": W_METODO}])
        assert undo(api, uuid.uuid4(), e["version"]).status_code == 404
        assert undo(api, "no-es-uuid", e["version"]).status_code == 404
        db.dashboards[bid]["deleted_at"] = db.dashboards[bid]["created_at"]
        assert undo(api, bid, e["version"]).status_code == 404

    async def test_ediciones_posteriores_devuelven_409_con_el_conteo_y_se_confirman(self, api, env):
        db, bid, *_ = await make_board(env)
        s0 = state(db, bid)
        e1 = await run(env, "Ventas por día", [{"op": "add_widget", "spec": W_METODO}])
        e2 = await run(env, "Ventas por día", [{"op": "add_widget", "spec": W_CONTEO}])
        s2 = state(db, bid)
        res = undo(api, bid, e1["version"])
        assert res.status_code == 409
        assert res.json()["detail"]["code"] == "newer_edits" and res.json()["detail"]["count"] == 1
        assert "más recientes" in res.json()["detail"]["message"] and state(db, bid) == s2
        done = undo(api, bid, e1["version"], include_newer=True)
        assert done.status_code == 200 and done.json()["discarded_newer"] == 1 and state(db, bid) == s0
        assert undo(api, bid, e2["version"]).status_code == 404

    async def test_una_version_de_otra_organizacion_es_404_y_no_toca_nada(self, api, env, login):
        db_a, bid_a, *_ = await make_board(env, org=ORG_A)
        db_b, bid_b, *_ = await make_board(env, org=ORG_B)
        e = await run(env, "Ventas por día", [{"op": "add_widget", "spec": W_METODO}], org=ORG_A)
        before = (state(db_a, bid_a), state(db_b, bid_b))
        login(ORG_B, "owner")
        assert undo(api, bid_a, e["version"]).status_code == 404       # el tablero de A no existe en la BD de B
        assert undo(api, bid_b, e["version"]).status_code == 404       # y esa version tampoco
        assert (state(db_a, bid_a), state(db_b, bid_b)) == before

    @pytest.mark.parametrize("body", [
        {}, {"version": ""}, {"version": "x" * 65}, {"version": 5}, {"version": str(uuid.uuid4()), "force": True},
        {"version": str(uuid.uuid4()), "include_newer": "tal vez"}, {"versions": [1]},
    ])
    async def test_cuerpo_invalido_es_422(self, api, env, body):
        db, bid, *_ = await make_board(env)
        assert api.post(f"/api/v1/dashboards/{bid}/undo-edit", json=body).status_code == 422

    async def test_sin_sesion_es_401(self, client, env, app):
        app.dependency_overrides.pop(get_current_user, None)
        assert client.post(f"/api/v1/dashboards/{uuid.uuid4()}/undo-edit", json={"version": str(uuid.uuid4())}).status_code in (401, 403)
        assert client.get(f"/api/v1/dashboards/{uuid.uuid4()}/versions").status_code in (401, 403)


class TestVersiones:
    async def test_lista_las_versiones_sin_datos_de_la_mas_nueva_a_la_mas_vieja(self, api, env):
        db, bid, *_ = await make_board(env)
        e1 = await run(env, "Ventas por día", [{"op": "add_widget", "spec": W_METODO}])
        e2 = await run(env, "Ventas por día", [{"op": "remove_widget", "target": "cifra"}, {"op": "rename", "title": "Dos"}])
        res = api.get(f"/api/v1/dashboards/{bid}/versions")
        assert res.status_code == 200
        items = res.json()
        assert [v["version"] for v in items] == [e2["version"], e1["version"]]
        assert items[0]["name"] == "Ventas por día" and items[0]["widgets"] == 4
        assert items[0]["summary"] == {"added": 0, "replaced": 0, "removed": 1, "renamed": True}
        assert set(items[0]) == {"version", "created_at", "name", "widgets", "summary"}
        assert "sum(total)" not in res.text and "preview" not in res.text

    async def test_tablero_sin_ediciones_devuelve_lista_vacia(self, api, env):
        db, bid, *_ = await make_board(env)
        assert api.get(f"/api/v1/dashboards/{bid}/versions").json() == []

    async def test_inexistente_o_de_otra_organizacion_es_404(self, api, env, login):
        db, bid, *_ = await make_board(env)
        assert api.get(f"/api/v1/dashboards/{uuid.uuid4()}/versions").status_code == 404
        assert api.get("/api/v1/dashboards/no-es-uuid/versions").status_code == 404
        login(ORG_B)
        assert api.get(f"/api/v1/dashboards/{bid}/versions").status_code == 404
