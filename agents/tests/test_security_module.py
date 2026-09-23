"""
Tests de agents/tools/_security.py.

Cubre validate_org_id: aceptacion por match, rechazo por mismatch,
rechazo por contexto ausente y rechazo por UUID invalido.
"""

import uuid
from unittest.mock import MagicMock

import pytest

from agents.tools._security import validate_org_id, get_authenticated_org_id

VALID_ORG_ID = "550e8400-e29b-41d4-a716-446655440000"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_context(state: dict) -> MagicMock:
    ctx = MagicMock()
    ctx.state = state
    return ctx


# ---------------------------------------------------------------------------
# validate_org_id — aceptacion
# ---------------------------------------------------------------------------


def test_validate_org_id_acepta_match():
    """org_id igual al authenticated_org_id en state debe retornar None."""
    ctx = _make_tool_context({"authenticated_org_id": VALID_ORG_ID})
    result = validate_org_id(VALID_ORG_ID, ctx)
    assert result is None


def test_validate_org_id_acepta_match_con_campos_extra():
    """State con campos extra no debe interferir con la validacion exitosa."""
    ctx = _make_tool_context({
        "authenticated_org_id": VALID_ORG_ID,
        "authenticated_user_id": "user-123",
        "org_id": VALID_ORG_ID,
    })
    result = validate_org_id(VALID_ORG_ID, ctx)
    assert result is None


# ---------------------------------------------------------------------------
# validate_org_id — rechazo por mismatch
# ---------------------------------------------------------------------------


def test_validate_org_id_rechaza_mismatch():
    """org_id distinto al authenticated_org_id debe retornar dict de error."""
    other_org = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    ctx = _make_tool_context({"authenticated_org_id": VALID_ORG_ID})
    result = validate_org_id(other_org, ctx)
    assert result is not None
    assert isinstance(result, dict)
    assert result.get("error") == "org_mismatch"


def test_validate_org_id_mismatch_contiene_mensaje():
    """El dict de error por mismatch debe incluir clave 'message'."""
    other_org = "00000000-0000-0000-0000-000000000001"
    ctx = _make_tool_context({"authenticated_org_id": VALID_ORG_ID})
    result = validate_org_id(other_org, ctx)
    assert "message" in result


# ---------------------------------------------------------------------------
# validate_org_id — rechazo por contexto ausente
# ---------------------------------------------------------------------------


def test_validate_org_id_rechaza_authenticated_ausente():
    """State sin authenticated_org_id debe retornar error missing_auth_context."""
    ctx = _make_tool_context({"org_id": VALID_ORG_ID})
    result = validate_org_id(VALID_ORG_ID, ctx)
    assert result is not None
    assert result.get("error") == "missing_auth_context"


def test_validate_org_id_rechaza_state_vacio():
    """State completamente vacio debe retornar error missing_auth_context."""
    ctx = _make_tool_context({})
    result = validate_org_id(VALID_ORG_ID, ctx)
    assert result is not None
    assert result.get("error") == "missing_auth_context"


def test_validate_org_id_rechaza_tool_context_sin_state():
    """ToolContext sin atributo 'state' debe retornar error missing_auth_context."""
    ctx = MagicMock(spec=[])  # sin atributo state
    result = validate_org_id(VALID_ORG_ID, ctx)
    assert result is not None
    assert result.get("error") == "missing_auth_context"


# ---------------------------------------------------------------------------
# validate_org_id — UUID invalido (mismatch de cadena)
# ---------------------------------------------------------------------------


def test_validate_org_id_rechaza_uuid_invalido():
    """org_id 'not-a-uuid' no coincide con un UUID valido en state — debe ser bloqueado."""
    ctx = _make_tool_context({"authenticated_org_id": VALID_ORG_ID})
    result = validate_org_id("not-a-uuid", ctx)
    assert result is not None
    assert result.get("error") == "org_mismatch"


def test_validate_org_id_rechaza_uuid_vacio():
    """org_id vacio no debe coincidir con un UUID valido en state."""
    ctx = _make_tool_context({"authenticated_org_id": VALID_ORG_ID})
    result = validate_org_id("", ctx)
    assert result is not None
    assert result.get("error") == "org_mismatch"


# ---------------------------------------------------------------------------
# get_authenticated_org_id
# ---------------------------------------------------------------------------


def test_get_authenticated_org_id_retorna_valor_presente():
    """Debe retornar el authenticated_org_id como string cuando esta presente."""
    ctx = _make_tool_context({"authenticated_org_id": VALID_ORG_ID})
    val = get_authenticated_org_id(ctx)
    assert val == VALID_ORG_ID


def test_get_authenticated_org_id_retorna_none_cuando_ausente():
    """Debe retornar None cuando authenticated_org_id no existe en el state."""
    ctx = _make_tool_context({})
    val = get_authenticated_org_id(ctx)
    assert val is None
