"""Helpers para simular respuestas de google.genai sin red — PI0320251."""

from google.genai import types as genai_types


def text_response(text):
    """GenerateContentResponse real (sin red) con un candidato de texto."""
    if text is None:
        return genai_types.GenerateContentResponse(candidates=[])
    return genai_types.GenerateContentResponse(
        candidates=[
            genai_types.Candidate(
                content=genai_types.Content(role="model", parts=[genai_types.Part(text=text)])
            )
        ]
    )


def make_fake_genai(default_text: str = "Respuesta de prueba"):
    """Cliente google.genai COMPLETO simulado (API async: client.aio.chats.create + await send_message).

    Devuelve SimpleNamespace(client, chat, create, send, aclose). `send` es AsyncMock:
    `send.side_effect = <excepcion | funcion async>` y `send.return_value = <respuesta>`.
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
