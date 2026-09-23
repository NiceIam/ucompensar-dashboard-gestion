"""
Tests del singleton de sesiones ADK en agents/pipeline.py.

Verifica que _chat_session_service y _analytical_session_service son
singleton a nivel de modulo y que las sesiones creadas persisten entre
llamadas al mismo objeto.
"""

import pytest
import pytest_asyncio

import agents.pipeline as pipeline_module
from agents.pipeline import _chat_session_service, _analytical_session_service


# ---------------------------------------------------------------------------
# Singleton identity
# ---------------------------------------------------------------------------


def test_chat_session_service_es_module_singleton():
    """Importar _chat_session_service dos veces debe dar el mismo objeto."""
    # Segunda importacion desde el modulo directamente
    from agents.pipeline import _chat_session_service as service_b
    assert id(_chat_session_service) == id(service_b)


def test_analytical_session_service_es_module_singleton():
    """Importar _analytical_session_service dos veces debe dar el mismo objeto."""
    from agents.pipeline import _analytical_session_service as service_b
    assert id(_analytical_session_service) == id(service_b)


def test_chat_service_referencia_modulo_es_mismo_objeto():
    """El atributo en el modulo debe apuntar al mismo objeto que la variable importada."""
    assert id(pipeline_module._chat_session_service) == id(_chat_session_service)


def test_analytical_service_referencia_modulo_es_mismo_objeto():
    """El atributo en el modulo debe apuntar al mismo objeto que la variable importada."""
    assert id(pipeline_module._analytical_session_service) == id(_analytical_session_service)


def test_chat_y_analytical_son_instancias_distintas():
    """Los dos singletons deben ser objetos distintos entre si."""
    assert id(_chat_session_service) != id(_analytical_session_service)


# ---------------------------------------------------------------------------
# Persistencia de sesiones entre llamadas
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_singleton_persiste_sesiones_entre_llamadas():
    """
    Crea una sesion via el servicio singleton, la recupera por session_id
    en una segunda llamada — debe ser el mismo objeto.
    """
    service = _chat_session_service
    user_id = "test-user-singleton"

    # Primera llamada: crear sesion
    session_a = await service.create_session(
        app_name="chat",
        user_id=user_id,
        state={"authenticated_org_id": "550e8400-e29b-41d4-a716-446655440000"},
    )

    # Segunda llamada: recuperar por session_id
    session_b = await service.get_session(
        app_name="chat",
        user_id=user_id,
        session_id=session_a.id,
    )

    assert session_b is not None
    assert session_a.id == session_b.id


@pytest.mark.asyncio
async def test_singleton_analytical_persiste_sesiones_entre_llamadas():
    """
    Misma prueba de persistencia para _analytical_session_service.
    """
    service = _analytical_session_service
    user_id = "test-user-analytical"

    session_a = await service.create_session(
        app_name="analytical",
        user_id=user_id,
        state={"authenticated_org_id": "550e8400-e29b-41d4-a716-446655440000"},
    )

    session_b = await service.get_session(
        app_name="analytical",
        user_id=user_id,
        session_id=session_a.id,
    )

    assert session_b is not None
    assert session_a.id == session_b.id


@pytest.mark.asyncio
async def test_sesion_inexistente_retorna_none():
    """Recuperar un session_id que no existe debe retornar None sin error."""
    service = _chat_session_service
    result = await service.get_session(
        app_name="chat",
        user_id="ghost-user",
        session_id="nonexistent-session-id-xyz",
    )
    assert result is None
