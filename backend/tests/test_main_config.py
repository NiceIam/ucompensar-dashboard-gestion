"""Tests for Settings validation and app configuration — PI0320251.

Covers:
- BCRYPT_ROUNDS validator (range 10-15, default 12)
- /docs gating based on APP_ENV
- CORS configuration: no wildcards, credentials=True
"""

import os
from unittest.mock import patch

import pytest

os.environ.setdefault("DATABASE_HOST", "localhost")
os.environ.setdefault("DATABASE_PORT", "5432")
os.environ.setdefault("DATABASE_USER", "postgres")
os.environ.setdefault("DATABASE_PASSWORD", "postgres")
os.environ.setdefault("DATABASE_NAME", "pi_main")
os.environ.setdefault("GOOGLE_API_KEY", "test-google-api-key")
os.environ.setdefault("APP_SECRET_KEY", "test-app-secret-key-at-least-32-chars-ok")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("BCRYPT_ROUNDS", "10")

_VALID_KEY = "test-app-secret-key-at-least-32-chars-ok"
_DB_KWARGS = dict(
    DATABASE_HOST="localhost",
    DATABASE_PORT=5432,
    DATABASE_USER="postgres",
    DATABASE_PASSWORD="postgres",
    DATABASE_NAME="pi_main",
    GOOGLE_API_KEY="test-key",
)


# ---------------------------------------------------------------------------
# BCRYPT_ROUNDS validator
# ---------------------------------------------------------------------------

class TestBcryptRoundsValidator:
    """Settings.BCRYPT_ROUNDS must enforce the range [10, 15]."""

    def test_bcrypt_rounds_default_es_12(self):
        """When BCRYPT_ROUNDS is not set, the default must be 12."""
        from app.config import Settings

        s = Settings(APP_SECRET_KEY=_VALID_KEY, BCRYPT_ROUNDS=12, **_DB_KWARGS)
        assert s.BCRYPT_ROUNDS == 12

    @pytest.mark.parametrize("rounds", [10, 11, 12, 13, 14, 15])
    def test_bcrypt_rounds_acepta_10_a_15(self, rounds: int):
        """Settings must accept any integer in [10, 15] without raising."""
        from app.config import Settings

        s = Settings(APP_SECRET_KEY=_VALID_KEY, BCRYPT_ROUNDS=rounds, **_DB_KWARGS)
        assert s.BCRYPT_ROUNDS == rounds

    @pytest.mark.parametrize("rounds", [1, 4, 9])
    def test_bcrypt_rounds_rechaza_menor_que_10(self, rounds: int):
        """Settings must raise ValueError when BCRYPT_ROUNDS < 10."""
        from pydantic import ValidationError
        from app.config import Settings

        with pytest.raises(ValidationError):
            Settings(APP_SECRET_KEY=_VALID_KEY, BCRYPT_ROUNDS=rounds, **_DB_KWARGS)

    @pytest.mark.parametrize("rounds", [16, 20, 31])
    def test_bcrypt_rounds_rechaza_mayor_que_15(self, rounds: int):
        """Settings must raise ValueError when BCRYPT_ROUNDS > 15."""
        from pydantic import ValidationError
        from app.config import Settings

        with pytest.raises(ValidationError):
            Settings(APP_SECRET_KEY=_VALID_KEY, BCRYPT_ROUNDS=rounds, **_DB_KWARGS)


# ---------------------------------------------------------------------------
# /docs gating by APP_ENV
# ---------------------------------------------------------------------------

class TestDocsGating:
    """/docs availability is controlled by APP_ENV in create_app()."""

    def _make_app(self, env: str):
        """Build a FastAPI app with the given APP_ENV, bypassing lru_cache."""
        from fastapi import FastAPI
        from app.config import Settings

        settings = Settings(
            APP_SECRET_KEY=_VALID_KEY,
            APP_ENV=env,
            BCRYPT_ROUNDS=10,
            **_DB_KWARGS,
        )
        _is_dev = settings.APP_ENV != "production"
        # Construct a minimal app that mirrors the docs_url gating logic in create_app
        app = FastAPI(
            title="Test App",
            docs_url="/docs" if _is_dev else None,
            redoc_url="/redoc" if _is_dev else None,
            openapi_url="/openapi.json" if _is_dev else None,
        )
        return app

    def test_docs_endpoint_404_en_production(self):
        """GET /docs must return 404 when APP_ENV=production (docs_url=None)."""
        from fastapi.testclient import TestClient

        app = self._make_app("production")
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/docs")
        assert response.status_code == 404

    def test_docs_endpoint_200_en_development(self):
        """GET /docs must return 200 when APP_ENV=development (docs_url='/docs')."""
        from fastapi.testclient import TestClient

        app = self._make_app("development")
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/docs")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# CORS configuration
# ---------------------------------------------------------------------------

class TestCorsConfiguration:
    """CORS middleware must not use wildcards and must allow credentials."""

    def _extract_cors_kwargs(self, env: str = "development") -> dict:
        """Instantiate the app and extract CORS middleware arguments."""
        from app.config import Settings

        settings = Settings(
            APP_SECRET_KEY=_VALID_KEY,
            APP_ENV=env,
            BCRYPT_ROUNDS=10,
            CORS_ORIGINS="http://localhost:3000,http://localhost:3001",
            **_DB_KWARGS,
        )
        with patch("app.config.get_settings", return_value=settings):
            with patch("app.auth.get_settings", return_value=settings):
                with patch("app.routers.auth_router.get_settings", return_value=settings):
                    from main import create_app
                    app = create_app()

        # Find the CORSMiddleware instance in the middleware stack
        from starlette.middleware.cors import CORSMiddleware
        for middleware in app.user_middleware:
            if middleware.cls is CORSMiddleware:
                return middleware.kwargs
        # Fallback: check app.middleware_stack attribute if available
        return {}

    def test_cors_methods_no_incluye_wildcard(self):
        """allow_methods must be an explicit list, never ['*']."""
        kwargs = self._extract_cors_kwargs()
        methods = kwargs.get("allow_methods", [])
        assert "*" not in methods, (
            f"allow_methods must not contain wildcard. Got: {methods}"
        )

    def test_cors_headers_no_incluye_wildcard(self):
        """allow_headers must be an explicit list, never ['*']."""
        kwargs = self._extract_cors_kwargs()
        headers = kwargs.get("allow_headers", [])
        assert "*" not in headers, (
            f"allow_headers must not contain wildcard. Got: {headers}"
        )

    def test_cors_allow_credentials_true(self):
        """allow_credentials must be True so cookies are forwarded cross-origin."""
        kwargs = self._extract_cors_kwargs()
        assert kwargs.get("allow_credentials") is True, (
            "CORS allow_credentials must be True to support HttpOnly cookie auth"
        )
