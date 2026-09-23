"""Utilidades de seguridad compartidas entre tools del pipeline.

Los tools del pipeline reciben `org_id` como parametro desde el LLM, pero
ese valor NO es confiable: un ataque de prompt injection puede intentar
modificarlo para acceder a datos de otra organizacion. El contexto de
confianza se establece al crear la sesion ADK en `agents/pipeline.py`
(clave `authenticated_org_id` en el state) y los tools deben validar cada
llamada contra ese valor.

Uso:

    from agents.tools._security import validate_org_id

    @tool
    def my_tool(org_id: str, tool_context: ToolContext) -> dict:
        err = validate_org_id(org_id, tool_context)
        if err:
            return err
        ...
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("agents.tools.security")


def validate_org_id(
    org_id: str,
    tool_context: Any,
) -> Optional[dict]:
    """Valida que el org_id recibido coincida con el authenticated_org_id
    guardado en el state de la sesion ADK.

    Retorna None si todo esta bien. Retorna un dict `{"error": ...}` si
    hay mismatch o contexto faltante, para que el tool lo devuelva al LLM.
    No levanta excepciones para evitar que el LLM lo capture como excusa
    para reintentar.
    """
    state = getattr(tool_context, "state", None) or {}
    trusted = state.get("authenticated_org_id")

    if not trusted:
        logger.warning(
            "Tool invoked without authenticated_org_id in state. "
            "This indicates a pipeline entry point did not set trusted "
            "context. Rejecting."
        )
        return {
            "error": "missing_auth_context",
            "message": (
                "El tool no puede ejecutarse: falta el contexto de "
                "autenticacion. Reporta este error al administrador."
            ),
        }

    if str(org_id) != str(trusted):
        logger.warning(
            "Cross-tenant access attempt: tool called with org_id=%s but "
            "authenticated_org_id=%s. Rejecting.",
            org_id,
            trusted,
        )
        return {
            "error": "org_mismatch",
            "message": (
                "No tienes permiso para acceder a datos de esa "
                "organizacion."
            ),
        }

    return None


def get_authenticated_org_id(tool_context: Any) -> Optional[str]:
    """Obtiene el authenticated_org_id desde el state (atajo para tools que
    prefieren usarlo directamente sin aceptar org_id como parametro)."""
    state = getattr(tool_context, "state", None) or {}
    val = state.get("authenticated_org_id")
    return str(val) if val else None
