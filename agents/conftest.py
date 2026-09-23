"""
conftest.py de nivel raiz del paquete agents.

Se ejecuta ANTES de que pytest intente importar cualquier modulo del
paquete. Aqui se parchean dependencias de infraestructura no disponibles
en el entorno de test:

1. google.adk.tools — agrega el decorator 'tool' que no existe en
   google-adk==0.3.0 pero que etl_tools.py importa.
2. psycopg2 — se mockea si no esta disponible para evitar errores de
   importacion en agents.config.
"""

import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# 1. Proxy de google.adk.tools que expone 'tool' como passthrough decorator.
#    Usamos un proxy en lugar de setattr porque 'from module import name'
#    requiere que el atributo este resolvible via __getattr__ en el modulo
#    registrado en sys.modules.
# ---------------------------------------------------------------------------
import google.adk.tools as _real_adk_tools


class _ADKToolsProxy:
    """Proxy que agrega el decorator 'tool' al modulo real de google.adk.tools."""

    def __init__(self, real_module):
        object.__setattr__(self, "_real", real_module)

    def __getattr__(self, name: str):
        if name == "tool":
            # Passthrough decorator compatible con la firma usada en etl_tools
            return lambda f: f
        return getattr(object.__getattribute__(self, "_real"), name)


sys.modules["google.adk.tools"] = _ADKToolsProxy(_real_adk_tools)  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# 2. Patch psycopg2 con mocks si no esta instalado.
# ---------------------------------------------------------------------------
try:
    import psycopg2  # noqa: F401  — solo verificar disponibilidad
except ImportError:
    sys.modules["psycopg2"] = MagicMock()
    sys.modules["psycopg2.extras"] = MagicMock()
