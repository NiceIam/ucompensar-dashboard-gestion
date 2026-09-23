"""
Fixtures compartidas para los tests del paquete agents.

Las patches de infraestructura (google.adk.tools, psycopg2) se realizan
en agents/conftest.py que se ejecuta antes que este archivo.
"""

from unittest.mock import MagicMock

import pytest


FIXED_ORG_ID = "550e8400-e29b-41d4-a716-446655440000"


@pytest.fixture
def mock_org_id() -> str:
    """UUID valido fijo para testing — no genera conexion real."""
    return FIXED_ORG_ID


@pytest.fixture
def mock_authenticated_state() -> dict:
    """State ADK con authenticated_org_id seteado correctamente."""
    return {
        "authenticated_org_id": FIXED_ORG_ID,
        "authenticated_user_id": "user-test-001",
        "org_id": FIXED_ORG_ID,
    }


@pytest.fixture
def mock_tool_context(mock_authenticated_state) -> MagicMock:
    """ToolContext mock con state autenticado listo para usar en tools."""
    ctx = MagicMock()
    ctx.state = mock_authenticated_state
    return ctx
