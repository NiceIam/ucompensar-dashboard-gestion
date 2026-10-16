"""Helpers para simular respuestas de google.genai sin red — PI0320251.

Todas las respuestas son tipos REALES de google.genai (GenerateContentResponse, FunctionCall...), asi el
codigo bajo prueba usa las mismas propiedades que con Gemini real (function_calls, usage_metadata...).
"""

from google.genai import types as genai_types


def usage(prompt: int = 0, output: int = 0, thoughts: int | None = None, cached: int | None = None):
    total = prompt + output + (thoughts or 0)
    return genai_types.GenerateContentResponseUsageMetadata(
        prompt_token_count=prompt, candidates_token_count=output, thoughts_token_count=thoughts,
        cached_content_token_count=cached, total_token_count=total,
    )


def text_response(text, usage_metadata=None):
    """GenerateContentResponse real (sin red) con un candidato de texto."""
    if text is None:
        return genai_types.GenerateContentResponse(candidates=[], usage_metadata=usage_metadata)
    return genai_types.GenerateContentResponse(
        candidates=[
            genai_types.Candidate(
                content=genai_types.Content(role="model", parts=[genai_types.Part(text=text)])
            )
        ],
        usage_metadata=usage_metadata,
    )


def call_response(*calls, text: str | None = None, usage_metadata=None):
    """Respuesta del modelo que pide herramientas. Cada llamada: (nombre, args) o (nombre, args, id)."""
    parts = [genai_types.Part(text=text)] if text else []
    for i, call in enumerate(calls):
        name, args = call[0], call[1]
        call_id = call[2] if len(call) > 2 else f"call-{i}"
        parts.append(genai_types.Part(function_call=genai_types.FunctionCall(id=call_id, name=name, args=args)))
    return genai_types.GenerateContentResponse(
        candidates=[genai_types.Candidate(content=genai_types.Content(role="model", parts=parts))],
        usage_metadata=usage_metadata,
    )


def sent_function_responses(send, call_index: int) -> list:
    """FunctionResponse que el codigo envio al modelo en la llamada numero `call_index` a send_message."""
    parts = send.call_args_list[call_index].args[0]
    return [p.function_response for p in parts]


def make_fake_genai(default_text: str = "Respuesta de prueba"):
    """Cliente google.genai COMPLETO simulado (API async: client.aio.chats.create + await send_message).

    Devuelve SimpleNamespace(client, chat, create, send, aclose). `send` es AsyncMock:
    `send.side_effect = <excepcion | funcion async | lista de respuestas>` y `send.return_value = <respuesta>`.
    """
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    client = MagicMock(name="genai.Client()")
    chat = MagicMock(name="AsyncChat")
    chat.send_message = AsyncMock(return_value=text_response(default_text))
    client.aio.chats.create.return_value = chat
    client.aio.aclose = AsyncMock()
    return SimpleNamespace(
        client=client,
        chat=chat,
        create=client.aio.chats.create,
        send=chat.send_message,
        aclose=client.aio.aclose,
    )
