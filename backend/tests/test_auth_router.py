"""Integration tests for auth_router.py — PI0320251.

Tests cookie behaviour, token-in-body absence, refresh logic, logout,
and rate limiting for /register and /login.

All DB calls are mocked — no real PostgreSQL required.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_HOST", "localhost")
os.environ.setdefault("DATABASE_PORT", "5432")
os.environ.setdefault("DATABASE_USER", "postgres")
os.environ.setdefault("DATABASE_PASSWORD", "postgres")
os.environ.setdefault("DATABASE_NAME", "pi_main")
os.environ.setdefault("GOOGLE_API_KEY", "test-google-api-key")
os.environ.setdefault("APP_SECRET_KEY", "test-app-secret-key-at-least-32-chars-ok")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("BCRYPT_ROUNDS", "10")


# ---------------------------------------------------------------------------
# Shared token helpers
# ---------------------------------------------------------------------------

def _make_tokens():
    """Return a real TokenResponse with short-lived tokens for tests."""
    from app.auth import create_access_token, create_refresh_token

    access = create_access_token(
        user_id="user-test-id",
        org_id="org-test-id",
        email="test@example.com",
        role="owner",
    )
    refresh = create_refresh_token(user_id="user-test-id")
    return access, refresh


def _make_token_response():
    from app.models.schemas import TokenResponse

    access, refresh = _make_tokens()
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=3600,
    )


# ---------------------------------------------------------------------------
# Fixture: client with all DB mocked out
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client() -> TestClient:
    from app.config import Settings

    test_settings = Settings(
        APP_SECRET_KEY="test-app-secret-key-at-least-32-chars-ok",
        APP_ENV="development",
        BCRYPT_ROUNDS=10,
        DATABASE_HOST="localhost",
        DATABASE_PORT=5432,
        DATABASE_USER="postgres",
        DATABASE_PASSWORD="postgres",
        DATABASE_NAME="pi_main",
        GOOGLE_API_KEY="test-key",
    )

    with patch("app.config.get_settings", return_value=test_settings):
        # Patch lru_cache inside auth and router modules as well
        with patch("app.auth.get_settings", return_value=test_settings):
            with patch("app.routers.auth_router.get_settings", return_value=test_settings):
                from main import create_app
                application = create_app()

    return TestClient(application, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# /login — cookie attributes and no token in body
# ---------------------------------------------------------------------------

class TestLoginCookies:
    """POST /api/v1/auth/login must set HttpOnly cookies and not expose tokens."""

    def _patched_login(self, client: TestClient, email: str = "owner@test.com", password: str = "Secret123!"):
        token_resp = _make_token_response()
        with patch(
            "app.routers.auth_router.login_user",
            AsyncMock(return_value=token_resp),
        ):
            return client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password},
            )

    def test_login_retorna_200(self, client: TestClient):
        response = self._patched_login(client)
        assert response.status_code == 200

    def test_login_setea_cookie_access_token(self, client: TestClient):
        """access_token cookie must be present in Set-Cookie header."""
        response = self._patched_login(client)
        set_cookie = response.headers.get("set-cookie", "")
        assert "access_token" in set_cookie

    def test_login_setea_cookie_httponly(self, client: TestClient):
        """access_token cookie must have HttpOnly attribute."""
        response = self._patched_login(client)
        set_cookie = response.headers.get("set-cookie", "").lower()
        assert "httponly" in set_cookie

    def test_login_setea_cookie_samesite_strict(self, client: TestClient):
        """access_token cookie must have SameSite=strict."""
        response = self._patched_login(client)
        set_cookie = response.headers.get("set-cookie", "").lower()
        assert "samesite=strict" in set_cookie

    def test_login_no_retorna_access_token_en_body(self, client: TestClient):
        """Response body must NOT contain access_token key."""
        response = self._patched_login(client)
        body = response.json()
        assert "access_token" not in body

    def test_login_no_retorna_refresh_token_en_body(self, client: TestClient):
        """Response body must NOT contain refresh_token key."""
        response = self._patched_login(client)
        body = response.json()
        assert "refresh_token" not in body

    def test_login_body_contiene_message(self, client: TestClient):
        """Response body must contain a 'message' field."""
        response = self._patched_login(client)
        body = response.json()
        assert "message" in body


# ---------------------------------------------------------------------------
# /register — cookie attributes
# ---------------------------------------------------------------------------

class TestRegisterCookies:
    """POST /api/v1/auth/register must set HttpOnly cookies."""

    _REGISTER_BODY = {
        "email": "nuevo@empresa.com",
        "password": "SecurePass123!",
        "full_name": "Nuevo Usuario",
        "org_name": "Empresa Test",
        "sector": "comercio",
        "size": "pequeña",
        "city": "Bogotá",
    }

    def _patched_register(self, client: TestClient):
        token_resp = _make_token_response()
        with patch(
            "app.routers.auth_router.register_organization",
            AsyncMock(return_value=token_resp),
        ):
            return client.post("/api/v1/auth/register", json=self._REGISTER_BODY)

    def test_register_retorna_201(self, client: TestClient):
        response = self._patched_register(client)
        assert response.status_code == 201

    def test_register_setea_cookie_access_token(self, client: TestClient):
        response = self._patched_register(client)
        set_cookie = response.headers.get("set-cookie", "")
        assert "access_token" in set_cookie

    def test_register_setea_cookie_httponly(self, client: TestClient):
        response = self._patched_register(client)
        set_cookie = response.headers.get("set-cookie", "").lower()
        assert "httponly" in set_cookie

    def test_register_no_retorna_tokens_en_body(self, client: TestClient):
        """Register response body must not expose tokens."""
        response = self._patched_register(client)
        body = response.json()
        assert "access_token" not in body
        assert "refresh_token" not in body


# ---------------------------------------------------------------------------
# /refresh — reads cookie, not body
# ---------------------------------------------------------------------------

class TestRefreshToken:
    """POST /api/v1/auth/refresh must work with cookie and fail without it."""

    @staticmethod
    def _make_pool_mock():
        fake_user = {
            "id": "user-test-id",
            "email": "test@example.com",
            "org_id": "org-test-id",
            "role": "owner",
        }
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=fake_user)
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        return pool

    def test_refresh_sin_cookie_retorna_401(self, client: TestClient):
        """Without refresh_token cookie the endpoint must return 401."""
        # Clear any cookies left over from previous tests in the shared client jar
        client.cookies.clear()
        pool = self._make_pool_mock()
        with patch("app.database.get_main_pool", AsyncMock(return_value=pool)):
            response = client.post("/api/v1/auth/refresh")
        assert response.status_code == 401

    def test_refresh_con_cookie_invalida_retorna_401(self, client: TestClient):
        """A tampered refresh_token cookie must return 401."""
        pool = self._make_pool_mock()
        with patch("app.database.get_main_pool", AsyncMock(return_value=pool)):
            client.cookies.set("refresh_token", "invalid.token.here")
            response = client.post("/api/v1/auth/refresh")
            client.cookies.clear()
        assert response.status_code == 401

    def test_refresh_con_cookie_valida_retorna_200(self, client: TestClient):
        """A valid refresh_token cookie and mocked DB must return 200."""
        _, refresh = _make_tokens()
        pool = self._make_pool_mock()

        with patch("app.database.get_main_pool", AsyncMock(return_value=pool)):
            client.cookies.set("refresh_token", refresh)
            response = client.post("/api/v1/auth/refresh")
            client.cookies.clear()

        assert response.status_code == 200

    def test_refresh_rota_cookies_en_respuesta(self, client: TestClient):
        """Successful refresh must set new cookies in response."""
        _, refresh = _make_tokens()
        pool = self._make_pool_mock()

        with patch("app.database.get_main_pool", AsyncMock(return_value=pool)):
            client.cookies.set("refresh_token", refresh)
            response = client.post("/api/v1/auth/refresh")
            client.cookies.clear()

        set_cookie = response.headers.get("set-cookie", "")
        assert "access_token" in set_cookie


# ---------------------------------------------------------------------------
# /logout — deletes cookies
# ---------------------------------------------------------------------------

class TestLogout:
    """POST /api/v1/auth/logout must clear authentication cookies."""

    def test_logout_borra_cookies_con_max_age_0(self, client: TestClient):
        """Logout response must include Set-Cookie with max-age=0 (delete_cookie)."""
        from app.auth import CurrentUser, get_current_user

        fake_user = CurrentUser(
            user_id="user-test-id",
            org_id="org-test-id",
            email="test@example.com",
            role="owner",
        )

        # Override the FastAPI dependency so /logout sees an authenticated user
        app = client.app  # type: ignore[attr-defined]
        app.dependency_overrides[get_current_user] = lambda: fake_user

        try:
            access, _ = _make_tokens()
            client.cookies.set("access_token", access)
            response = client.post("/api/v1/auth/logout")
            client.cookies.clear()
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        # FastAPI delete_cookie sets max-age=0
        set_cookie_header = response.headers.get("set-cookie", "").lower()
        assert response.status_code == 200
        assert "max-age=0" in set_cookie_header

    def test_logout_sin_autenticacion_retorna_401(self, client: TestClient):
        """Logout without a valid token must return 401."""
        response = client.post("/api/v1/auth/logout")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiting:
    """Verify that rate limits are enforced on /register and /login."""

    @pytest.mark.slow
    def test_rate_limit_register_5_per_minute(self, client: TestClient):
        """6th POST /register within a minute must receive 429."""
        token_resp = _make_token_response()

        with patch(
            "app.routers.auth_router.register_organization",
            AsyncMock(return_value=token_resp),
        ):
            body = {
                "email": "ratetest@example.com",
                "password": "SecurePass123!",
                "full_name": "Rate Test",
                "org_name": "Rate Org",
                "sector": "comercio",
                "size": "micro",
                "city": "Bogotá",
            }
            statuses = []
            for i in range(6):
                body["email"] = f"rate{i}@example.com"
                r = client.post("/api/v1/auth/register", json=body)
                statuses.append(r.status_code)

        # At least one request must have been rate limited
        assert 429 in statuses, (
            f"Expected 429 after 5 register attempts; got statuses: {statuses}"
        )

    @pytest.mark.slow
    def test_rate_limit_login_10_per_minute(self, client: TestClient):
        """11th POST /login within a minute must receive 429."""
        token_resp = _make_token_response()

        with patch(
            "app.routers.auth_router.login_user",
            AsyncMock(return_value=token_resp),
        ):
            statuses = []
            for _ in range(11):
                r = client.post(
                    "/api/v1/auth/login",
                    json={"email": "owner@test.com", "password": "Secret123!"},
                )
                statuses.append(r.status_code)

        assert 429 in statuses, (
            f"Expected 429 after 10 login attempts; got statuses: {statuses}"
        )


# ---------------------------------------------------------------------------
# GET /me — profile endpoint coverage
# ---------------------------------------------------------------------------

class TestMeEndpoint:
    """GET /api/v1/auth/me must require a valid access_token cookie."""

    def test_me_sin_cookie_retorna_401(self, client: TestClient):
        """Calling /me with no cookies at all must return 401."""
        client.cookies.clear()
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401

    def test_me_con_cookie_invalida_retorna_401(self, client: TestClient):
        """A tampered access_token cookie must be rejected with 401."""
        client.cookies.clear()
        client.cookies.set("access_token", "not.a.valid.jwt")
        response = client.get("/api/v1/auth/me")
        client.cookies.clear()
        assert response.status_code == 401

    def test_me_con_cookie_valida_retorna_user_profile(self, client: TestClient):
        """A valid access_token cookie and mocked DB must return 200 with user profile."""
        import datetime
        from app.auth import get_current_user, CurrentUser

        fake_user = CurrentUser(
            user_id="user-me-id",
            org_id="org-me-id",
            email="me@example.com",
            role="owner",
        )
        fake_profile = {
            "id": "user-me-id",
            "email": "me@example.com",
            "full_name": "Me User",
            "org_id": "org-me-id",
            "role": "owner",
            "avatar_url": None,
            "created_at": datetime.datetime.now(datetime.timezone.utc),
        }

        app = client.app  # type: ignore[attr-defined]
        app.dependency_overrides[get_current_user] = lambda: fake_user

        try:
            with patch(
                "app.routers.auth_router.get_user_profile",
                AsyncMock(return_value=__import__("app.models.schemas", fromlist=["UserProfileResponse"]).UserProfileResponse(
                    user_id="user-me-id",
                    org_id="org-me-id",
                    email="me@example.com",
                    full_name="Me User",
                    role="owner",
                    avatar_url=None,
                    created_at=fake_profile["created_at"],
                )),
            ):
                response = client.get("/api/v1/auth/me")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert response.status_code == 200
        body = response.json()
        assert body["email"] == "me@example.com"

    def test_me_no_acepta_token_via_bearer_post_round5(self, client: TestClient):
        """After M-01 fix: Authorization Bearer header must NOT authenticate /me (cookie-only)."""
        access, _ = _make_tokens()
        client.cookies.clear()
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access}"},
        )
        # With cookie-only auth, Bearer header alone must yield 401
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Cookie Secure attribute — production vs development
# ---------------------------------------------------------------------------

class TestCookieSecureAttribute:
    """Login must set Secure flag on cookies in production, not in development."""

    def _make_fresh_client(self, env: str) -> TestClient:
        """Build a fresh TestClient isolated from module-level rate limit state."""
        from app.config import Settings

        settings = Settings(
            APP_SECRET_KEY="test-app-secret-key-at-least-32-chars-ok",
            APP_ENV=env,
            BCRYPT_ROUNDS=10,
            DATABASE_HOST="localhost",
            DATABASE_PORT=5432,
            DATABASE_USER="postgres",
            DATABASE_PASSWORD="postgres",
            DATABASE_NAME="pi_main",
            GOOGLE_API_KEY="test-key",
        )
        with patch("app.config.get_settings", return_value=settings):
            with patch("app.auth.get_settings", return_value=settings):
                with patch("app.routers.auth_router.get_settings", return_value=settings):
                    from main import create_app
                    application = create_app()
        return TestClient(application, raise_server_exceptions=False)

    def _login_with_env(self, env: str):
        """Perform a mocked login using a fresh per-test client with rate limiting reset."""
        from app.config import Settings
        from app.auth import limiter as _limiter

        env_settings = Settings(
            APP_SECRET_KEY="test-app-secret-key-at-least-32-chars-ok",
            APP_ENV=env,
            BCRYPT_ROUNDS=10,
            DATABASE_HOST="localhost",
            DATABASE_PORT=5432,
            DATABASE_USER="postgres",
            DATABASE_PASSWORD="postgres",
            DATABASE_NAME="pi_main",
            GOOGLE_API_KEY="test-key",
        )
        token_resp = _make_token_response()
        fresh_client = self._make_fresh_client(env)

        # Reset the in-memory rate limit storage so prior TestRateLimiting
        # exhaustion does not cause 429 here.
        try:
            _limiter.reset()
        except Exception:
            pass

        # Patch get_settings in all modules that call it at request time so
        # is_production reflects the desired environment during cookie writing.
        with patch("app.config.get_settings", return_value=env_settings), \
             patch("app.auth.get_settings", return_value=env_settings), \
             patch("app.routers.auth_router.get_settings", return_value=env_settings), \
             patch("app.routers.auth_router.login_user", AsyncMock(return_value=token_resp)):
            return fresh_client.post(
                "/api/v1/auth/login",
                json={"email": "secure-test@test.com", "password": "Secret123!"},
            )

    def test_login_cookie_secure_en_production(self):
        """In production mode, access_token Set-Cookie must contain 'secure'."""
        response = self._login_with_env("production")
        assert response.status_code == 200, f"Expected 200 but got {response.status_code}"
        # Collect all Set-Cookie header values (may be multiple cookies)
        raw_headers = response.headers.items()
        cookies_raw = [v for k, v in raw_headers if k.lower() == "set-cookie"]
        access_cookie = next(
            (c for c in cookies_raw if "access_token" in c.lower()),
            "",
        )
        assert "secure" in access_cookie.lower(), (
            f"Expected 'secure' in Set-Cookie for production. Got: {access_cookie!r}"
        )

    def test_login_cookie_secure_false_en_development(self):
        """In development mode, access_token Set-Cookie must NOT have 'secure' flag."""
        response = self._login_with_env("development")
        assert response.status_code == 200, f"Expected 200 but got {response.status_code}"
        raw_headers = response.headers.items()
        cookies_raw = [v for k, v in raw_headers if k.lower() == "set-cookie"]
        access_cookie = next(
            (c for c in cookies_raw if "access_token" in c.lower()),
            "",
        )
        # In development, 'secure' must be absent from the access_token cookie
        assert "secure" not in access_cookie.lower(), (
            f"'secure' must not appear in Set-Cookie in development. Got: {access_cookie!r}"
        )
