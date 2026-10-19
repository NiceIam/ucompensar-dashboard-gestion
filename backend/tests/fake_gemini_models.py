"""Cliente google.genai simulado para llamadas SIN chat (`client.aio.models.generate_content`) — PI0320251.

Lo usa el agente de esquema (schema_ai_service). Las respuestas son tipos REALES de google.genai.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from tests.fake_gemini import text_response, usage


def make_fake_genai_models(payload=None, text: str | None = None, usage_metadata=None):
    """`payload` (dict/list) se serializa como la respuesta JSON del modelo; `text` la fija tal cual (para respuestas
    mal formadas). Devuelve SimpleNamespace(client, generate, aclose); `generate` es AsyncMock con las llamadas."""
    client = MagicMock(name="genai.Client()")
    body = text if text is not None else json.dumps(payload if payload is not None else {})
    generate = AsyncMock(return_value=text_response(body, usage_metadata or usage(prompt=700, output=120, thoughts=60)))
    client.aio.models.generate_content = generate
    client.aio.aclose = AsyncMock()
    return SimpleNamespace(client=client, generate=generate, aclose=client.aio.aclose)


def ai_answer(kind: str, confidence: float, roles: dict[int, tuple], n_columns: int | None = None) -> dict:
    """Respuesta valida del modelo: roles = {indice: (rol, confianza[, desc])}. Las columnas sin rol salen como 'otro'."""
    cols = []
    for i in range(n_columns if n_columns is not None else (max(roles) + 1 if roles else 0)):
        r = roles.get(i, ("otro", 0.2))
        item = {"i": i, "role": r[0], "confidence": r[1]}
        if len(r) > 2:
            item["desc"] = r[2]
        cols.append(item)
    return {"kind": kind, "confidence": confidence, "columns": cols}
