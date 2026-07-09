import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ai_core.contracts.schemas import Button, ButtonsMessage, IncomingMessage, make_stream_end, make_text_chunk
from memory import MemoryManager

router = APIRouter(prefix="/agent", tags=["agent"])

BUTTON_NOT_FOUND_MESSAGE = (
    "Не удалось распознать выбор — возможно, эта кнопка уже устарела. "
    "Пожалуйста, напишите ваш вопрос текстом."
)


async def _stream_agent_response(
    graph,
    memory: MemoryManager,
    payload: IncomingMessage,
) -> AsyncIterator[str]:
    buttons: list[Button] = await graph.adecide_buttons(payload)
    buttons_msg = ButtonsMessage(session_id=payload.session_id, buttons=buttons)
    yield buttons_msg.model_dump_json() + "\n"

    accumulated_chunks: list[str] = []
    async for chunk in graph.astream_response(payload):
        accumulated_chunks.append(chunk)
        yield json.dumps(make_text_chunk(payload.session_id, chunk), ensure_ascii=False) + "\n"

    yield json.dumps(make_stream_end(payload.session_id), ensure_ascii=False) + "\n"

    full_response = "".join(accumulated_chunks)
    buttons_metadata = {"buttons": {b.callback_data: b.text for b in buttons}} if buttons else {}
    await memory.messages.append_message(
        payload.session_id, "assistant", full_response, metadata=buttons_metadata,
    )


async def _stream_fallback_message(session_id: str, text: str) -> AsyncIterator[str]:
    """Короткий поток без обращения к графу — используется, когда callback_data
    не удалось распознать. Не тратим вызов LLM на бессмысленный технический идентификатор."""
    empty_buttons = ButtonsMessage(session_id=session_id, buttons=[])
    yield empty_buttons.model_dump_json() + "\n"
    yield json.dumps(make_text_chunk(session_id, text), ensure_ascii=False) + "\n"
    yield json.dumps(make_stream_end(session_id), ensure_ascii=False) + "\n"


@router.post("/process")
async def process_message(payload: IncomingMessage, request: Request) -> StreamingResponse:
    graph = request.app.state.graph
    memory = request.app.state.memory

    if payload.message_type == "callback":
        label_text = await memory.messages.find_buttons_context(
            payload.session_id, payload.user_message,
        )

        if label_text is None:
            # Контекст кнопки не найден — не отправляем мусор в граф,
            # сразу просим пользователя написать текстом.
            await memory.messages.append_message(
                payload.session_id,
                "user",
                payload.user_message,
                metadata={"message_type": "callback", "callback_data": payload.user_message, "resolved": False},
            )
            await memory.messages.append_message(
                payload.session_id, "assistant", BUTTON_NOT_FOUND_MESSAGE,
            )
            return StreamingResponse(
                _stream_fallback_message(payload.session_id, BUTTON_NOT_FOUND_MESSAGE),
                media_type="application/x-ndjson",
            )

        await memory.messages.append_message(
            payload.session_id,
            "user",
            label_text,
            metadata={"message_type": "callback", "callback_data": payload.user_message, "resolved": True},
        )
        payload = payload.model_copy(update={"user_message": label_text})
    else:
        await memory.messages.append_message(payload.session_id, "user", payload.user_message)

    return StreamingResponse(
        _stream_agent_response(graph, memory, payload),
        media_type="application/x-ndjson",
    )