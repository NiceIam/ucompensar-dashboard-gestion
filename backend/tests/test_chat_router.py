"""Tests del router /api/v1/chat (+ send_message / get_history de chat_service) — PI0320251.

Se prueba de punta a punta lo que SI es testeable sin infraestructura:
router -> chat_service -> process_with_gemini, con la BD de la org emulada
(tests/fake_org_db.py), la BD principal emulada y `google.genai.Client`
reemplazado por un mock (NUNCA se llama a Gemini real).

NO cubierto: POST /chat/upload (depende de parse_file/store_file/smart_upload y
del sistema de archivos), ni el comportamiento real de asyncpg/Postgres.
"""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors

from app.auth import CurrentUser, get_current_user
from tests.fake_gemini import make_fake_genai, text_response
from tests.fake_org_db import FakeMainPool, FakeOrgDBs

ORG_A = "550e8400-e29b-41d4-a716-446655440000"
ORG_B = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"

SECRET_KEY = "AIzaSy-ROUTER-SECRET-KEY"
RAW = "RAWMARKER"
BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def chat_env():
    """BDs en memoria + Gemini mockeado, instalados en chat_service y agent_tools_service."""
    dbs = FakeOrgDBs()
    main = FakeMainPool()
    main.orgs[ORG_A] = {"name": "Ferreteria Alfa", "sector": "comercio", "city": "Bogota"}
    main.orgs[ORG_B] = {"name": "Restaurante Beta", "sector": "comercio", "city": "Cali"}

    fake = make_fake_genai()
    settings = SimpleNamespace(
        GOOGLE_API_KEY=SECRET_KEY, GEMINI_MODEL="gemini-test-model", GEMINI_TIMEOUT_SECONDS=25.0
    )

    with patch("app.services.chat_service.get_org_pool", dbs.get_org_pool), patch(
        "app.services.agent_tools_service.get_org_pool", dbs.get_org_pool
    ), patch("app.services.agent_tools_service.get_main_pool", main.get_main_pool), patch(
        "app.services.agent_tools_service.get_settings", return_value=settings
    ), patch("google.genai.Client", return_value=fake.client) as ctor:
        yield SimpleNamespace(
            dbs=dbs, main=main, ctor=ctor, create=fake.create, send=fake.send
        )


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """El limiter es un singleton en memoria (app.auth.limiter): sin reset, los cupos se acumulan entre tests."""
    from app.auth import limiter

    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def as_user(app):
    """Autentica las peticiones como un usuario de una org dada."""

    def _login(org_id: str, user_id: str = USER_A):
        user = CurrentUser(user_id=user_id, org_id=org_id, email="u@example.com", role="admin")
        app.dependency_overrides[get_current_user] = lambda: user

    yield _login
    app.dependency_overrides.pop(get_current_user, None)


def seed_ventas(chat_env, org_id: str = ORG_A, producto: str = "Martillo"):
    chat_env.dbs.db(org_id).add_table(
        "ventas", ["producto", "total"], [{"producto": producto, "total": 100}], display_name="Ventas"
    )


def seed_chat(chat_env, org_id: str, n: int, user_id: str = USER_A) -> None:
    """n mensajes alternados user/assistant, con created_at creciente."""
    db = chat_env.dbs.db(org_id)
    for i in range(n):
        db.chat.append({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "role": "user" if i % 2 == 0 else "assistant",
            "content": f"mensaje {i}",
            "created_at": BASE + timedelta(minutes=i),
        })


def system_prompt(chat_env) -> str:
    return chat_env.create.call_args.kwargs["config"].system_instruction


# ---------------------------------------------------------------------------
# Autenticacion y validacion
# ---------------------------------------------------------------------------

class TestAutenticacionYValidacion:
    def test_sin_cookie_de_sesion_responde_401(self, client: TestClient, chat_env):
        client.cookies.clear()

        assert client.post("/api/v1/chat/message", json={"content": "hola"}).status_code == 401
        assert client.get("/api/v1/chat/history").status_code == 401
        chat_env.ctor.assert_not_called()

    @pytest.mark.parametrize("content", ["", "x" * 4001])
    def test_contenido_vacio_o_demasiado_largo_responde_422_sin_llamar_a_gemini(
        self, client: TestClient, chat_env, as_user, content
    ):
        as_user(ORG_A)

        resp = client.post("/api/v1/chat/message", json={"content": content})

        assert resp.status_code == 422
        chat_env.ctor.assert_not_called()

    def test_contenido_de_4000_caracteres_es_valido(self, client: TestClient, chat_env, as_user):
        as_user(ORG_A)

        assert client.post("/api/v1/chat/message", json={"content": "x" * 4000}).status_code == 200


# ---------------------------------------------------------------------------
# POST /message
# ---------------------------------------------------------------------------

class TestMessage:
    def test_camino_feliz_responde_y_persiste_ambos_mensajes(self, client: TestClient, chat_env, as_user):
        as_user(ORG_A, USER_A)
        seed_ventas(chat_env)

        resp = client.post("/api/v1/chat/message", json={"content": "cuanto vendi?"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["role"] == "assistant"
        assert body["content"] == "Respuesta de prueba"
        assert body["message_id"] and body["created_at"]
        saved = chat_env.dbs.db(ORG_A).chat
        assert [(m["role"], m["content"], m["user_id"]) for m in saved] == [
            ("user", "cuanto vendi?", USER_A),
            ("assistant", "Respuesta de prueba", USER_A),
        ]
        assert chat_env.send.call_count == 1

    def test_el_contexto_sale_de_la_org_del_usuario_autenticado(self, client: TestClient, chat_env, as_user):
        """Aislamiento por org: el org_id viene del token, no del body."""
        seed_ventas(chat_env, ORG_A, producto="DATO_DE_A")
        seed_ventas(chat_env, ORG_B, producto="DATO_DE_B")
        as_user(ORG_B, USER_B)

        client.post("/api/v1/chat/message", json={"content": "ventas", "file_id": ORG_A})

        prompt = system_prompt(chat_env)
        assert "DATO_DE_B" in prompt and "Restaurante Beta" in prompt
        assert "DATO_DE_A" not in prompt and "Ferreteria Alfa" not in prompt
        assert set(chat_env.dbs.requested_org_ids) == {ORG_B}
        assert chat_env.dbs.db(ORG_A).chat == []

    def test_los_charts_se_agregan_al_contenido_como_bloque_chart(self, client: TestClient, chat_env, as_user):
        as_user(ORG_A)
        chat_env.send.return_value = text_response(
            'Mira:\n```chart\n{"type":"bar","title":"T","data":[{"name":"a","value":1}]}\n```'
        )

        body = client.post("/api/v1/chat/message", json={"content": "grafico"}).json()

        assert body["content"].startswith("Mira:")
        assert '```chart\n{"type": "bar", "title": "T", "data": [{"name": "a", "value": 1}]}\n```' in body["content"]

    def test_gemini_cae_con_cuota_agotada_responde_200_no_500(self, client: TestClient, chat_env, as_user):
        as_user(ORG_A)
        chat_env.send.side_effect = genai_errors.ClientError(
            429, {"error": {"code": 429, "message": f"Quota exceeded {RAW}", "status": "RESOURCE_EXHAUSTED"}}
        )

        resp = client.post("/api/v1/chat/message", json={"content": "hola"})

        assert resp.status_code == 200
        assert len(chat_env.dbs.db(ORG_A).chat) == 2

    def test_gemini_caido_el_usuario_y_el_historial_ven_un_mensaje_amable(
        self, client: TestClient, chat_env, as_user
    ):
        as_user(ORG_A)
        seed_ventas(chat_env)
        chat_env.send.side_effect = httpx.ConnectError(f"all connection attempts failed {RAW} {SECRET_KEY}")

        body = client.post("/api/v1/chat/message", json={"content": "ventas"}).json()

        persisted = chat_env.dbs.db(ORG_A).chat[-1]["content"]
        for text in (body["content"], persisted):
            assert RAW not in text and SECRET_KEY not in text and "Error con Gemini" not in text
            assert "no está disponible" in text.lower()
            assert "Martillo" in text  # resumen local de datos reales
        assert body["content"] == persisted

    def test_respuesta_bloqueada_por_gemini_da_mensaje_con_causa(self, client: TestClient, chat_env, as_user):
        from google.genai import types

        as_user(ORG_A)
        chat_env.send.return_value = types.GenerateContentResponse(
            prompt_feedback=types.GenerateContentResponsePromptFeedback(block_reason=types.BlockedReason.SAFETY)
        )

        body = client.post("/api/v1/chat/message", json={"content": "algo"}).json()

        assert "bloque" in body["content"].lower()

    def test_el_mensaje_actual_no_se_envia_duplicado_a_gemini(self, client: TestClient, chat_env, as_user):
        as_user(ORG_A)
        seed_chat(chat_env, ORG_A, 2)

        client.post("/api/v1/chat/message", json={"content": "pregunta actual"})

        history = chat_env.create.call_args.kwargs["history"]
        assert [c.parts[0].text for c in history].count("pregunta actual") == 0
        chat_env.send.assert_called_once_with("pregunta actual")

    def test_el_historial_enviado_a_gemini_son_exactamente_los_mensajes_previos(
        self, client: TestClient, chat_env, as_user
    ):
        as_user(ORG_A)
        seed_chat(chat_env, ORG_A, 3)

        client.post("/api/v1/chat/message", json={"content": "pregunta actual"})

        sent = chat_env.create.call_args.kwargs["history"]
        assert [(c.role, c.parts[0].text) for c in sent] == [
            ("user", "mensaje 0"), ("model", "mensaje 1"), ("user", "mensaje 2"),
        ]

    def test_el_mensaje_actual_se_persiste_igual_aunque_no_vaya_en_el_historial(
        self, client: TestClient, chat_env, as_user
    ):
        as_user(ORG_A)
        seed_chat(chat_env, ORG_A, 2)

        client.post("/api/v1/chat/message", json={"content": "pregunta actual"})

        saved = chat_env.dbs.db(ORG_A).chat
        assert [(m["role"], m["content"]) for m in saved[-2:]] == [
            ("user", "pregunta actual"), ("assistant", "Respuesta de prueba"),
        ]
        hist = client.get("/api/v1/chat/history").json()["messages"]
        assert [m["content"] for m in hist][-2:] == ["pregunta actual", "Respuesta de prueba"]

    def test_el_historial_enviado_a_gemini_son_los_mensajes_previos_de_la_org(
        self, client: TestClient, chat_env, as_user
    ):
        as_user(ORG_A)
        seed_chat(chat_env, ORG_A, 3)
        seed_chat(chat_env, ORG_B, 2)
        chat_env.dbs.db(ORG_B).chat[0]["content"] = "CHAT_PRIVADO_DE_B"

        client.post("/api/v1/chat/message", json={"content": "nueva"})

        sent = [c.parts[0].text for c in chat_env.create.call_args.kwargs["history"]]
        assert "mensaje 0" in sent and "mensaje 2" in sent
        assert "CHAT_PRIVADO_DE_B" not in sent


# ---------------------------------------------------------------------------
# GET /history
# ---------------------------------------------------------------------------

class TestHistory:
    def test_devuelve_mensajes_en_orden_cronologico_con_total(self, client: TestClient, chat_env, as_user):
        as_user(ORG_A)
        seed_chat(chat_env, ORG_A, 4)

        body = client.get("/api/v1/chat/history").json()

        assert body["total"] == 4
        assert [m["content"] for m in body["messages"]] == [f"mensaje {i}" for i in range(4)]
        assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user", "assistant"]

    def test_historial_vacio(self, client: TestClient, chat_env, as_user):
        as_user(ORG_A)

        assert client.get("/api/v1/chat/history").json() == {"messages": [], "total": 0}

    def test_aislamiento_por_org(self, client: TestClient, chat_env, as_user):
        seed_chat(chat_env, ORG_A, 3)
        as_user(ORG_B, USER_B)

        assert client.get("/api/v1/chat/history").json()["total"] == 0

    def test_limit_se_respeta_y_se_topa_en_200(self, client: TestClient, chat_env, as_user):
        as_user(ORG_A)
        seed_chat(chat_env, ORG_A, 205)

        assert client.get("/api/v1/chat/history?limit=2").json()["total"] == 2
        capped = client.get("/api/v1/chat/history?limit=1000").json()["messages"]
        assert len(capped) == 200
        assert capped[0]["content"] == "mensaje 5" and capped[-1]["content"] == "mensaje 204"  # los 200 ULTIMOS

    def test_limit_pequeno_devuelve_los_ultimos_en_orden_cronologico(self, client: TestClient, chat_env, as_user):
        as_user(ORG_A)
        seed_chat(chat_env, ORG_A, 10)

        contents = [m["content"] for m in client.get("/api/v1/chat/history?limit=3").json()["messages"]]

        assert contents == ["mensaje 7", "mensaje 8", "mensaje 9"]

    def test_con_mas_mensajes_que_el_limit_se_devuelven_los_mas_recientes(
        self, client: TestClient, chat_env, as_user
    ):
        as_user(ORG_A)
        seed_chat(chat_env, ORG_A, 60)

        contents = [m["content"] for m in client.get("/api/v1/chat/history").json()["messages"]]

        assert "mensaje 59" in contents
        assert contents == sorted(contents, key=lambda c: int(c.split()[1]))  # sigue en orden cronologico


# ---------------------------------------------------------------------------
# Rate limit de POST /message (slowapi, mismo limiter que auth)
# ---------------------------------------------------------------------------

@pytest.fixture
def chat_limit():
    """Fija CHAT_RATE_LIMIT para el test (el router lo lee en cada peticion)."""

    def _set(value: str):
        return patch("app.routers.chat.get_settings", return_value=SimpleNamespace(CHAT_RATE_LIMIT=value))

    return _set


class TestRateLimit:
    def test_la_peticion_n_mas_1_recibe_429_y_no_consume_gemini(self, client: TestClient, chat_env, as_user, chat_limit):
        as_user(ORG_A, USER_A)

        with chat_limit("3/minute"):
            statuses = [
                client.post("/api/v1/chat/message", json={"content": f"m{i}"}).status_code for i in range(5)
            ]

        assert statuses == [200, 200, 200, 429, 429]
        assert chat_env.send.call_count == 3                      # el 429 no llama a Gemini (cuesta dinero)
        assert len(chat_env.dbs.db(ORG_A).chat) == 6              # ni guarda mensajes

    def test_otro_usuario_de_otra_org_no_se_ve_afectado(self, client: TestClient, chat_env, as_user, chat_limit):
        with chat_limit("2/minute"):
            as_user(ORG_A, USER_A)
            assert [client.post("/api/v1/chat/message", json={"content": "x"}).status_code for _ in range(3)] == [
                200, 200, 429,
            ]
            as_user(ORG_B, USER_B)
            assert client.post("/api/v1/chat/message", json={"content": "x"}).status_code == 200

    def test_otro_usuario_de_la_misma_org_tiene_su_propio_cupo(self, client: TestClient, chat_env, as_user, chat_limit):
        with chat_limit("1/minute"):
            as_user(ORG_A, USER_A)
            assert client.post("/api/v1/chat/message", json={"content": "x"}).status_code == 200
            assert client.post("/api/v1/chat/message", json={"content": "x"}).status_code == 429
            as_user(ORG_A, USER_B)
            assert client.post("/api/v1/chat/message", json={"content": "x"}).status_code == 200

    def test_peticiones_sin_sesion_no_consumen_cupo(self, client: TestClient, chat_env, chat_limit):
        client.cookies.clear()
        with chat_limit("2/minute"):
            statuses = [client.post("/api/v1/chat/message", json={"content": "x"}).status_code for _ in range(5)]

        assert statuses == [401] * 5

    def test_history_no_esta_limitado(self, client: TestClient, chat_env, as_user, chat_limit):
        as_user(ORG_A)
        with chat_limit("1/minute"):
            assert all(client.get("/api/v1/chat/history").status_code == 200 for _ in range(5))

    def test_el_cupo_se_reinicia_con_reset(self, client: TestClient, chat_env, as_user, chat_limit):
        from app.auth import limiter

        as_user(ORG_A)
        with chat_limit("1/minute"):
            assert client.post("/api/v1/chat/message", json={"content": "x"}).status_code == 200
            assert client.post("/api/v1/chat/message", json={"content": "x"}).status_code == 429
            limiter.reset()
            assert client.post("/api/v1/chat/message", json={"content": "x"}).status_code == 200

    def test_el_429_de_slowapi_en_el_chat_usa_la_misma_estructura_que_el_de_cuota(
        self, client: TestClient, chat_env, as_user, chat_limit
    ):
        as_user(ORG_A)
        with chat_limit("1/minute"):
            client.post("/api/v1/chat/message", json={"content": "x"})
            resp = client.post("/api/v1/chat/message", json={"content": "x"})

        assert resp.status_code == 429
        detail = resp.json()["detail"]
        assert set(detail) == {"code", "message", "retry_after_seconds", "retry_at"}
        assert detail["code"] == "rate_limit_user"
        assert detail["retry_after_seconds"] == 60
        assert resp.headers["Retry-After"] == "60"
        assert "60 segundos" in detail["message"]

    def test_el_429_de_slowapi_fuera_del_chat_conserva_su_cuerpo_por_defecto(self, client: TestClient):
        """auth sigue devolviendo {"error": "Rate limit exceeded: ..."}: el handler solo cambia /api/v1/chat."""
        from fastapi import HTTPException

        from unittest.mock import AsyncMock

        client.cookies.clear()
        with patch("app.routers.auth_router.login_user", AsyncMock(side_effect=HTTPException(401, "no"))):
            responses = [
                client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "Secret123!"})
                for _ in range(11)
            ]

        limited = [r for r in responses if r.status_code == 429]
        assert limited, [r.status_code for r in responses]
        assert limited[0].json() == {"error": "Rate limit exceeded: 10 per 1 minute"}

    def test_default_20_por_minuto_y_configurable_por_entorno(self, monkeypatch):
        from app.config import Settings

        monkeypatch.delenv("CHAT_RATE_LIMIT", raising=False)
        assert Settings(_env_file=None).CHAT_RATE_LIMIT == "20/minute"
        monkeypatch.setenv("CHAT_RATE_LIMIT", "5/minute")
        assert Settings(_env_file=None).CHAT_RATE_LIMIT == "5/minute"

    def test_con_el_default_real_el_21_recibe_429(self, client: TestClient, chat_env, as_user):
        """Sin parchear la configuracion: usa el default real de Settings."""
        as_user(ORG_A)

        statuses = [client.post("/api/v1/chat/message", json={"content": "x"}).status_code for _ in range(21)]

        assert statuses[:20] == [200] * 20 and statuses[20] == 429

    def test_con_jwt_real_en_cookie_cada_usuario_tiene_su_cupo(self, client: TestClient, chat_env, chat_limit):
        """Sin dependency_overrides: la clave sale del usuario del token validado, no de la IP."""
        from app.auth import create_access_token

        def login(user_id: str, org_id: str) -> None:
            client.cookies.clear()
            client.cookies.set("access_token", create_access_token(user_id, org_id, "u@example.com", "owner"))

        try:
            with chat_limit("1/minute"):
                login(USER_A, ORG_A)
                assert client.post("/api/v1/chat/message", json={"content": "x"}).status_code == 200
                assert client.post("/api/v1/chat/message", json={"content": "x"}).status_code == 429
                login(USER_B, ORG_B)
                assert client.post("/api/v1/chat/message", json={"content": "x"}).status_code == 200
        finally:
            client.cookies.clear()


# ---------------------------------------------------------------------------
# Topes de uso compartidos (contados en Postgres sobre chat_messages)
# ---------------------------------------------------------------------------

def quota_settings(user: int = 20, window: int = 60, org: int = 300):
    """Parchea los topes que lee chat_service (los defaults reales se prueban aparte)."""
    return patch(
        "app.services.chat_service.get_settings",
        return_value=SimpleNamespace(
            CHAT_USER_MAX_MESSAGES=user, CHAT_USER_WINDOW_SECONDS=window, CHAT_ORG_DAILY_MESSAGES=org
        ),
    )


def seed_user_messages(chat_env, org_id: str, user_id: str, ages_seconds: list[float], role: str = "user") -> None:
    """Un mensaje por cada edad (segundos hacia atras desde ahora, hora UTC como la que guarda send_message)."""
    now = datetime.now(timezone.utc)
    for age in ages_seconds:
        chat_env.dbs.db(org_id).chat.append({
            "id": str(uuid.uuid4()), "user_id": user_id, "role": role,
            "content": f"{role} hace {age}s", "created_at": now - timedelta(seconds=age),
        })


def post(client: TestClient, content: str = "hola"):
    return client.post("/api/v1/chat/message", json={"content": content})


def assert_sin_efectos(chat_env, org_id: str, mensajes_antes: int) -> None:
    """Un 429 por cuota no guarda mensaje ni toca a Gemini."""
    assert len(chat_env.dbs.db(org_id).chat) == mensajes_antes
    chat_env.ctor.assert_not_called()
    chat_env.send.assert_not_called()


class TestCuotaCompartida:
    def test_tope_por_usuario_responde_429_con_detalle_y_retry_after(self, client: TestClient, chat_env, as_user):
        as_user(ORG_A, USER_A)
        seed_user_messages(chat_env, ORG_A, USER_A, [10, 20, 30])

        with quota_settings(user=3, window=60):
            resp = post(client)

        assert resp.status_code == 429
        detail = resp.json()["detail"]
        assert set(detail) == {"code", "message", "retry_after_seconds", "retry_at", "limit"}
        assert detail["code"] == "rate_limit_user" and detail["limit"] == 3
        # el cupo se libera cuando sale de la ventana el 3er mensaje mas nuevo (hace 30 s): en ~30 s
        assert 29 <= detail["retry_after_seconds"] <= 31
        assert resp.headers["Retry-After"] == str(detail["retry_after_seconds"])
        assert "30 segundos" in detail["message"] and "3 mensajes" in detail["message"]
        retry_at = datetime.fromisoformat(detail["retry_at"])
        assert abs((retry_at - datetime.now(timezone.utc)).total_seconds() - detail["retry_after_seconds"]) < 3
        assert_sin_efectos(chat_env, ORG_A, mensajes_antes=3)

    def test_bajo_el_tope_pasa(self, client: TestClient, chat_env, as_user):
        as_user(ORG_A, USER_A)
        seed_user_messages(chat_env, ORG_A, USER_A, [10, 20])

        with quota_settings(user=3, window=60):
            assert post(client).status_code == 200

    def test_mensajes_fuera_de_la_ventana_no_cuentan(self, client: TestClient, chat_env, as_user):
        as_user(ORG_A, USER_A)
        seed_user_messages(chat_env, ORG_A, USER_A, [120, 300, 3600])

        with quota_settings(user=3, window=60):
            assert post(client).status_code == 200

    def test_los_mensajes_del_asistente_no_cuentan(self, client: TestClient, chat_env, as_user):
        as_user(ORG_A, USER_A)
        seed_user_messages(chat_env, ORG_A, USER_A, [5, 6, 7, 8, 9], role="assistant")

        with quota_settings(user=3, window=60, org=3):
            assert post(client).status_code == 200

    def test_el_tope_por_usuario_no_afecta_a_otro_usuario_de_la_misma_org(self, client: TestClient, chat_env, as_user):
        seed_user_messages(chat_env, ORG_A, USER_A, [10, 20, 30])

        with quota_settings(user=3, window=60):
            as_user(ORG_A, USER_A)
            assert post(client).status_code == 429
            as_user(ORG_A, USER_B)
            assert post(client).status_code == 200

    def test_tope_diario_de_la_org_responde_429_y_otra_org_no_se_ve_afectada(self, client: TestClient, chat_env, as_user):
        seed_user_messages(chat_env, ORG_A, USER_A, [3600])
        seed_user_messages(chat_env, ORG_A, USER_B, [7200, 10800])

        with quota_settings(user=100, org=3):
            as_user(ORG_A, USER_A)
            resp = post(client)
            as_user(ORG_B, USER_B)
            ok = post(client)

        assert resp.status_code == 429
        detail = resp.json()["detail"]
        assert detail["code"] == "quota_org_daily" and detail["limit"] == 3
        # se libera cuando sale de la ventana de 24 h el 3er mensaje mas nuevo (hace 3 h): en ~21 h
        assert abs(detail["retry_after_seconds"] - 21 * 3600) <= 2
        assert resp.headers["Retry-After"] == str(detail["retry_after_seconds"])
        assert "límite diario" in detail["message"] and "21 horas" in detail["message"]
        assert ok.status_code == 200
        assert len(chat_env.dbs.db(ORG_A).chat) == 3          # el 429 no guardo nada en la org bloqueada

    def test_el_tope_diario_cuenta_ventana_de_24h_los_mas_viejos_no_cuentan(self, client: TestClient, chat_env, as_user):
        as_user(ORG_A, USER_A)
        seed_user_messages(chat_env, ORG_A, USER_B, [25 * 3600, 30 * 3600, 48 * 3600, 3600, 7200])

        with quota_settings(user=100, org=3):
            assert post(client).status_code == 200            # solo 2 dentro de 24 h

        # ahora hay 3 dentro de la ventana (2 + el recien enviado): el siguiente se bloquea
        with quota_settings(user=100, org=3):
            assert post(client).status_code == 429

    def test_si_ambos_topes_estan_excedidos_se_informa_el_diario(self, client: TestClient, chat_env, as_user):
        as_user(ORG_A, USER_A)
        seed_user_messages(chat_env, ORG_A, USER_A, [10, 20, 30])

        with quota_settings(user=3, org=3):
            assert post(client).json()["detail"]["code"] == "quota_org_daily"

    @pytest.mark.parametrize("user, org", [(0, 0), (-1, -1)])
    def test_un_valor_menor_o_igual_a_cero_desactiva_el_tope(self, client: TestClient, chat_env, as_user, user, org):
        as_user(ORG_A, USER_A)
        seed_user_messages(chat_env, ORG_A, USER_A, [1] * 50)

        with quota_settings(user=user, org=org):
            assert post(client).status_code == 200

    def test_el_tope_es_compartido_entre_instancias_no_depende_del_limiter_en_memoria(
        self, client: TestClient, chat_env, as_user
    ):
        """Simula varias instancias serverless: el contador de slowapi se reinicia en cada peticion
        (como si cada una cayera en un proceso distinto) y el tope en Postgres igual bloquea."""
        from app.auth import limiter

        as_user(ORG_A, USER_A)
        statuses = []
        with quota_settings(user=2, window=60):
            for _ in range(4):
                limiter.reset()
                statuses.append(post(client).status_code)

        assert statuses == [200, 200, 429, 429]
        assert chat_env.send.call_count == 2
        assert len(chat_env.dbs.db(ORG_A).chat) == 4          # 2 pares user/assistant; los 429 no guardan

    def test_los_topes_se_cuentan_con_el_created_at_que_guarda_el_chat(self, client: TestClient, chat_env, as_user):
        """Los mensajes que guarda send_message (hora UTC de la app) son los que luego cuenta el tope."""
        as_user(ORG_A, USER_A)

        with quota_settings(user=100, org=2):
            assert post(client).status_code == 200
            assert post(client).status_code == 200
            resp = post(client)

        assert resp.status_code == 429 and resp.json()["detail"]["code"] == "quota_org_daily"

    def test_slowapi_sigue_siendo_la_primera_capa_y_no_interfiere(self, client: TestClient, chat_env, as_user, chat_limit):
        as_user(ORG_A, USER_A)

        with chat_limit("2/minute"), quota_settings(user=100, org=100):
            statuses = [post(client).status_code for _ in range(3)]

        assert statuses == [200, 200, 429]
        assert chat_env.send.call_count == 2                  # el 429 de slowapi tampoco llama a Gemini

    def test_error_de_bd_al_contar_no_se_traga_y_no_llama_a_gemini(self, client: TestClient, chat_env, as_user):
        """Politica documentada: falla cerrado (500), nunca deja pasar sin contar."""
        as_user(ORG_A, USER_A)
        chat_env.dbs.db(ORG_A).fail_when = lambda q, args: "created_at > $" in q

        with quota_settings():
            resp = post(client)

        assert resp.status_code == 500
        assert_sin_efectos(chat_env, ORG_A, mensajes_antes=0)


class TestDefaultsDeCuota:
    def test_defaults_y_sobrescritura_por_entorno(self, monkeypatch):
        from app.config import Settings

        for name in ("CHAT_USER_MAX_MESSAGES", "CHAT_USER_WINDOW_SECONDS", "CHAT_ORG_DAILY_MESSAGES"):
            monkeypatch.delenv(name, raising=False)
        s = Settings(_env_file=None)
        assert (s.CHAT_USER_MAX_MESSAGES, s.CHAT_USER_WINDOW_SECONDS, s.CHAT_ORG_DAILY_MESSAGES) == (20, 60, 300)

        monkeypatch.setenv("CHAT_USER_MAX_MESSAGES", "5")
        monkeypatch.setenv("CHAT_USER_WINDOW_SECONDS", "30")
        monkeypatch.setenv("CHAT_ORG_DAILY_MESSAGES", "50")
        s = Settings(_env_file=None)
        assert (s.CHAT_USER_MAX_MESSAGES, s.CHAT_USER_WINDOW_SECONDS, s.CHAT_ORG_DAILY_MESSAGES) == (5, 30, 50)


class TestCuotaAtomica:
    def test_chequeo_e_insert_van_en_una_transaccion_bajo_lock_y_gemini_fuera(
        self, client: TestClient, chat_env, as_user
    ):
        as_user(ORG_A, USER_A)
        db = chat_env.dbs.db(ORG_A)
        gemini_en_tx: list[int] = []

        async def send(_msg):
            gemini_en_tx.append(db.tx_depth)   # 0 = fuera de toda transaccion (y del lock)
            return text_response("ok")

        chat_env.send.side_effect = send

        with quota_settings(user=5, org=100):
            assert post(client).status_code == 200

        log = list(zip(db.sql_log, db.tx_flags))
        idx = {
            "historial": next(i for i, (q, _) in enumerate(log) if q.startswith("select role, content from chat_messages")),
            "lock": next(i for i, (q, _) in enumerate(log) if "pg_advisory_xact_lock" in q),
            "org": next(i for i, (q, _) in enumerate(log) if q.startswith("select created_at") and "user_id" not in q),
            "user": next(i for i, (q, _) in enumerate(log) if q.startswith("select created_at") and "user_id = $1" in q),
            "insert": next(i for i, (q, _) in enumerate(log) if "'user'" in q and q.startswith("insert into chat_messages")),
        }
        assert idx["historial"] < idx["lock"] < idx["org"] < idx["user"] < idx["insert"]
        assert not log[idx["historial"]][1]                      # el historial se lee antes y fuera de la transaccion
        assert all(log[idx[k]][1] for k in ("lock", "org", "user", "insert"))
        assert gemini_en_tx == [0]

    def test_un_429_deja_la_transaccion_sin_insertar(self, client: TestClient, chat_env, as_user):
        as_user(ORG_A, USER_A)
        seed_user_messages(chat_env, ORG_A, USER_A, [10, 20])
        db = chat_env.dbs.db(ORG_A)

        with quota_settings(user=2):
            assert post(client).status_code == 429

        assert not any(q.startswith("insert into chat_messages") for q in db.sql_log)
        assert db.tx_depth == 0
        assert len(db.chat) == 2


class TestCuotaEnAnalytics:
    """POST /api/v1/analytics/query puede llegar a Gemini: comparte los topes del chat."""

    @pytest.fixture
    def analytics_env(self, chat_env):
        from unittest.mock import AsyncMock

        fallback = AsyncMock(return_value="Analisis de prueba")
        with patch("app.services.analytics_service.get_org_pool", chat_env.dbs.get_org_pool), patch(
            "app.services.analytics_service._fallback_analysis", fallback
        ):
            yield SimpleNamespace(fallback=fallback)

    @staticmethod
    def query(client: TestClient):
        return client.post("/api/v1/analytics/query", json={"query": "analiza mis ventas"})

    def test_bajo_el_tope_responde_y_guarda_ambos_mensajes(self, client: TestClient, chat_env, as_user, analytics_env):
        as_user(ORG_A, USER_A)

        with quota_settings(user=5):
            resp = self.query(client)

        assert resp.status_code == 200 and resp.json()["content"] == "Analisis de prueba"
        assert [(m["role"], m["content"]) for m in chat_env.dbs.db(ORG_A).chat] == [
            ("user", "analiza mis ventas"), ("assistant", "Analisis de prueba"),
        ]

    def test_tope_por_usuario_429_antes_de_gastar_y_sin_guardar(self, client: TestClient, chat_env, as_user, analytics_env):
        as_user(ORG_A, USER_A)
        seed_user_messages(chat_env, ORG_A, USER_A, [10, 20, 30])

        with quota_settings(user=3):
            resp = self.query(client)

        assert resp.status_code == 429
        assert resp.json()["detail"]["code"] == "rate_limit_user"
        assert "Retry-After" in resp.headers
        analytics_env.fallback.assert_not_called()
        chat_env.ctor.assert_not_called()
        assert len(chat_env.dbs.db(ORG_A).chat) == 3

    def test_tope_diario_de_la_org_aplica_y_otra_org_no_se_ve_afectada(self, client: TestClient, chat_env, as_user, analytics_env):
        seed_user_messages(chat_env, ORG_A, USER_B, [3600, 7200, 10800])

        with quota_settings(user=100, org=3):
            as_user(ORG_A, USER_A)
            blocked = self.query(client)
            as_user(ORG_B, USER_B)
            ok = self.query(client)

        assert blocked.status_code == 429 and blocked.json()["detail"]["code"] == "quota_org_daily"
        assert ok.status_code == 200
        analytics_env.fallback.assert_called_once()

    def test_comparte_cupo_con_el_chat(self, client: TestClient, chat_env, as_user, analytics_env):
        """Chat y analytics suman en el mismo contador: alternar entre ambos no evade el tope."""
        as_user(ORG_A, USER_A)

        with quota_settings(user=2):
            assert post(client).status_code == 200
            assert self.query(client).status_code == 200
            assert post(client).status_code == 429
            assert self.query(client).status_code == 429


class TestPrefijoDelHandlerDeSlowapi:
    @pytest.mark.parametrize(
        "path, es_chat",
        [("/api/v1/chat/message", True), ("/api/v1/chatty", False), ("/api/v1/chat", False), ("/api/v1/auth/login", False)],
    )
    def test_solo_las_rutas_bajo_chat_usan_el_formato_estructurado(self, path, es_chat):
        import main

        request = SimpleNamespace(url=SimpleNamespace(path=path))
        exc = SimpleNamespace(limit=SimpleNamespace(limit=SimpleNamespace(get_expiry=lambda: 60)))

        with patch("main._rate_limit_exceeded_handler", return_value="DEFAULT"):
            resp = main._on_rate_limit_exceeded(request, exc)

        assert (resp != "DEFAULT") is es_chat
