"""Tests del router GET /api/v1/insights — PI0320251.

De punta a punta: router -> business_insights_service -> motor, con la BD de la org emulada
(tests/fake_org_db.py) y el motor reemplazado por el oraculo pandas. Gemini NO existe en este camino: se
verifica que ni se construye el cliente ni se toca la cuota de mensajes del chat.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
from tests.fake_org_db import FakeOrgDBs
from tests.insights_support import ORG_A, ORG_B, PROD_COLS, SALE_COLS, prods, read_csv, sales
from tests.query_oracle import fake_run_plans

USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"
URL = "/api/v1/insights"


@pytest.fixture
def env():
    dbs = FakeOrgDBs()
    _, rows = read_csv("productos")
    dbs.db(ORG_A).add_table("productos", ["nombre", "categoria", "precio_compra", "precio_venta", "stock"],
                            [{k: r[k] for k in ("nombre", "categoria", "precio_compra", "precio_venta", "stock")}
                             for r in rows], display_name="Productos",
                            column_types={"precio_compra": "number", "precio_venta": "number", "stock": "integer"})
    _, rows = read_csv("ventas")
    dbs.db(ORG_A).add_table("ventas", ["fecha", "producto", "cantidad", "precio_unitario", "total", "cliente"],
                            [{k: r[k] for k in ("fecha", "producto", "cantidad", "precio_unitario", "total", "cliente")}
                             for r in rows], display_name="Ventas",
                            column_types={"fecha": "date", "cantidad": "integer", "precio_unitario": "number",
                                          "total": "number"})
    dbs.db(ORG_B).add_table("productos", list(PROD_COLS), prods(("Zeta", 10, 100)), display_name="Productos",
                            column_types=PROD_COLS)
    dbs.db(ORG_B).add_table("ventas", list(SALE_COLS), sales(("2025-05-01", "Zeta", 1, 50, "Unico"),
                                                             ("2025-05-09", "Zeta", 2, 50, "Unico")),
                            display_name="Ventas", column_types=SALE_COLS)

    def boom(*args, **kwargs):
        raise AssertionError("el endpoint de hallazgos NO debe usar Gemini ni la cuota del chat")

    with patch("app.services.business_insights_service.get_org_pool", dbs.get_org_pool), patch(
        "app.services.data_query_engine.run_plans", fake_run_plans()
    ), patch("google.genai.Client", side_effect=boom) as client_ctor, patch(
        "app.services.chat_service.reserve_user_message", side_effect=boom
    ) as reserve:
        yield SimpleNamespace(dbs=dbs, client_ctor=client_ctor, reserve=reserve)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from app.auth import limiter

    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def as_user(app):
    def _login(org_id: str, user_id: str = USER_A):
        user = CurrentUser(user_id=user_id, org_id=org_id, email="u@example.com", role="admin")
        app.dependency_overrides[get_current_user] = lambda: user

    yield _login
    app.dependency_overrides.pop(get_current_user, None)


class TestInsightsRouter:
    def test_sin_sesion_responde_401(self, client: TestClient, env):
        client.cookies.clear()
        resp = client.get(URL)
        assert resp.status_code == 401
        assert resp.json()["detail"] == "No autenticado."

    def test_200_con_la_forma_del_contrato(self, client: TestClient, env, as_user):
        as_user(ORG_A)
        resp = client.get(URL)
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {"generated_at", "recipe_pack", "period", "items", "missing", "summary_text"}
        assert body["recipe_pack"] == "ferreteria"
        assert body["generated_at"].endswith("Z") and "T" in body["generated_at"]
        assert body["period"] == {"from": "2025-07-02", "to": "2025-10-08", "days": 99}     # clave "from", no "from_"
        assert len(body["items"]) == 6
        first = body["items"][0]
        assert set(first) == {"id", "kind", "severity", "title", "sentence", "metrics", "action", "ask", "how"}
        assert first["id"] == "capital_inventario"
        assert first["metrics"][0] == {"label": "Mercancía a costo", "value": 47_620_000, "unit": "money"}
        assert set(first["how"]) == {"steps", "tables", "rows_used", "notes"}
        assert body["missing"] == [{"id": "cartera", "title": "Cuánto te deben tus clientes",
                                    "needs": "Una hoja con cliente, valor y fecha de vencimiento de cada cuenta por "
                                             "cobrar."}]
        assert body["summary_text"].startswith("Resumen de tu negocio (")
        assert resp.headers["content-type"].startswith("application/json")

    def test_la_organizacion_sale_del_token(self, client: TestClient, env, as_user):
        as_user(ORG_B)
        body = client.get(URL).json()
        assert body["period"]["from"] == "2025-05-01"
        assert env.dbs.requested_org_ids == [ORG_B]
        assert "Cemento" not in str(body)        # nada de la org A
        as_user(ORG_A)
        assert client.get(URL).json()["period"]["from"] == "2025-07-02"
        assert env.dbs.requested_org_ids == [ORG_B, ORG_A]

    def test_ignora_cualquier_org_pedida_por_el_cliente(self, client: TestClient, env, as_user):
        as_user(ORG_B)
        resp = client.get(URL, params={"org_id": ORG_A}, headers={"X-Org-Id": ORG_A})
        assert resp.json()["period"]["from"] == "2025-05-01"
        assert env.dbs.requested_org_ids == [ORG_B]

    def test_no_usa_gemini_ni_la_cuota_del_chat(self, client: TestClient, env, as_user):
        as_user(ORG_A)
        assert client.get(URL).status_code == 200
        env.client_ctor.assert_not_called()
        env.reserve.assert_not_called()
        assert env.dbs.db(ORG_A).chat == []
        assert all(q.startswith("select") for q in env.dbs.db(ORG_A).sql_log)     # solo lectura

    def test_limite_de_30_por_minuto_por_usuario(self, client: TestClient, env, as_user):
        as_user(ORG_A, USER_A)
        assert all(client.get(URL).status_code == 200 for _ in range(30))
        resp = client.get(URL)
        assert resp.status_code == 429
        detail = resp.json()["detail"]      # misma estructura que el 429 del chat
        assert detail["code"] == "rate_limit_user" and detail["retry_after_seconds"] == 60
        assert detail["message"] == "Estás consultando tus hallazgos muy seguido. Intenta de nuevo en 60 segundos."
        assert resp.headers["Retry-After"] == "60"
        # otro usuario tiene su propio cupo
        as_user(ORG_A, USER_B)
        assert client.get(URL).status_code == 200

    def test_las_peticiones_sin_sesion_no_consumen_cupo(self, client: TestClient, env, as_user):
        client.cookies.clear()
        assert all(client.get(URL).status_code == 401 for _ in range(35))
        as_user(ORG_A)
        assert client.get(URL).status_code == 200

    def test_servicio_no_disponible_responde_503_con_mensaje(self, client: TestClient, env, as_user):
        from app.services.business_insights_service import InsightsUnavailable

        as_user(ORG_A)

        async def unavailable(org_id):
            raise InsightsUnavailable("No pude leer tus datos ahora. Intenta de nuevo en un momento.")

        with patch("app.routers.insights.get_business_insights", unavailable):
            resp = client.get(URL)
        assert resp.status_code == 503
        assert resp.json()["detail"] == "No pude leer tus datos ahora. Intenta de nuevo en un momento."

    def test_org_sin_datos_responde_200_con_missing(self, client: TestClient, env, as_user):
        as_user("99999999-9999-9999-9999-999999999999")
        resp = client.get(URL)
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == [] and body["period"] is None
        assert [m["id"] for m in body["missing"]][-1] == "cartera" and len(body["missing"]) == 7

    def test_solo_get(self, client: TestClient, env, as_user):
        as_user(ORG_A)
        assert client.post(URL).status_code == 405
        assert client.delete(URL).status_code == 405
