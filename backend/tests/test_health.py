"""Tests básicos del health check — PI0320251."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Crea un cliente de test sin levantar dependencias externas."""
    import os

    # Valores mínimos para que Settings no falle al importar
    os.environ.setdefault("DATABASE_HOST", "localhost")
    os.environ.setdefault("DATABASE_PORT", "5432")
    os.environ.setdefault("DATABASE_USER", "postgres")
    os.environ.setdefault("DATABASE_PASSWORD", "postgres")
    os.environ.setdefault("DATABASE_NAME", "pi_main")
    os.environ.setdefault("GOOGLE_API_KEY", "test-google-api-key")
    os.environ.setdefault("APP_SECRET_KEY", "test-app-secret-key-at-least-32-chars-ok")

    from main import app

    return TestClient(app, raise_server_exceptions=False)


class TestHealthLiveness:
    """GET /api/health — liveness probe sin auth."""

    def test_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_body_has_status_ok(self, client: TestClient) -> None:
        data = client.get("/api/health").json()
        assert data["status"] == "ok"

    def test_body_has_version(self, client: TestClient) -> None:
        data = client.get("/api/health").json()
        assert "version" in data

    def test_no_auth_required(self, client: TestClient) -> None:
        """El endpoint no debe devolver 401 sin Authorization header."""
        response = client.get("/api/health")
        assert response.status_code != 401


class TestHealthDetailed:
    """GET /api/health/detailed — readiness probe, puede degradar si PostgreSQL no está."""

    def test_returns_200_or_503(self, client: TestClient) -> None:
        response = client.get("/api/health/detailed")
        assert response.status_code in (200, 503)

    def test_body_has_dependencies_key(self, client: TestClient) -> None:
        data = client.get("/api/health/detailed").json()
        assert "dependencies" in data

    def test_body_has_status(self, client: TestClient) -> None:
        data = client.get("/api/health/detailed").json()
        assert data["status"] in ("ok", "healthy", "degraded")

    def test_no_auth_required(self, client: TestClient) -> None:
        response = client.get("/api/health/detailed")
        assert response.status_code != 401


class TestOpenAPISchema:
    """Verifica que FastAPI genere el schema OpenAPI correctamente."""

    def test_openapi_accessible(self, client: TestClient) -> None:
        response = client.get("/openapi.json")
        assert response.status_code == 200

    def test_docs_accessible(self, client: TestClient) -> None:
        response = client.get("/docs")
        assert response.status_code == 200

    def test_api_title(self, client: TestClient) -> None:
        schema = client.get("/openapi.json").json()
        assert "PI0320251" in schema["info"]["title"]
