"""Shared pytest fixtures for backend tests — PI0320251."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Environment bootstrap — must happen before importing app modules
# ---------------------------------------------------------------------------
os.environ.setdefault("DATABASE_HOST", "localhost")
os.environ.setdefault("DATABASE_PORT", "5432")
os.environ.setdefault("DATABASE_USER", "postgres")
os.environ.setdefault("DATABASE_PASSWORD", "postgres")
os.environ.setdefault("DATABASE_NAME", "pi_main")
os.environ.setdefault("GOOGLE_API_KEY", "test-google-api-key")
os.environ.setdefault("APP_SECRET_KEY", "test-app-secret-key-at-least-32-chars-ok")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("BCRYPT_ROUNDS", "10")
# Las cargas de los tests no deben intentar sugerir tableros (usaria una BD real); las pruebas de sugerencias lo encienden.
os.environ.setdefault("DASHBOARD_AUTO_SUGGEST", "false")


# ---------------------------------------------------------------------------
# Settings fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def mock_settings():
    """Pydantic Settings with safe test values."""
    from app.config import Settings

    return Settings(
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


# ---------------------------------------------------------------------------
# FastAPI app fixture with DB dependency override
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app() -> FastAPI:
    """Return the FastAPI app with database dependency skipped."""
    from app.config import get_settings
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

    # Patch get_settings before importing main so lru_cache picks up test value
    with patch("app.config.get_settings", return_value=test_settings):
        from main import create_app
        application = create_app()

    return application


@pytest.fixture(scope="module")
def client(app: FastAPI) -> TestClient:
    """Sync TestClient for the FastAPI app."""
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Async client fixture (httpx)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def async_client(app: FastAPI):
    """httpx AsyncClient using ASGITransport — use inside async tests."""
    import httpx

    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


# ---------------------------------------------------------------------------
# Mock asyncpg pool
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_pool():
    """AsyncMock for an asyncpg pool with acquire() context manager.

    NOTE (rereview-tests round5): This fixture is NOT currently injected by any
    test — individual test modules inline their own pool mocks to keep test
    setup explicit and avoid hidden fixture coupling.  Keeping this fixture for
    future tests that need a shared pool mock; delete it if it still has zero
    usages after the next coverage review.
    """
    conn = AsyncMock()
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


# ---------------------------------------------------------------------------
# Rate limiter freeze fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def freeze_limiter():
    """Patch slowapi Limiter.limit so rate-limit decorators become no-ops."""
    with patch("slowapi.Limiter.limit", return_value=lambda f: f):
        yield
