import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ai_core.contracts.schemas import ButtonsMessage, IncomingMessage, make_stream_end, make_text_chunk
from memory import MemoryManager

router = APIRouter(prefix="/agent", tags=["agent"])


async def _stream_agent_response(
    graph,
    memory: MemoryManager,
    payload: IncomingMessage,
) -> AsyncIterator[str]:
    """Генератор NDJSON-строк: кнопки -> текстовые чанки -> конец потока.
    Параллельно копит текст ассистента, чтобы сохранить его в память
    одним финальным сообщением, когда стрим завершится."""

    buttons = await graph.adecide_buttons(payload)
    buttons_msg = ButtonsMessage(session_id=payload.session_id, buttons=buttons)
    yield buttons_msg.model_dump_json() + "\n"

    accumulated_chunks: list[str] = []
    async for chunk in graph.astream_response(payload):
        accumulated_chunks.append(chunk)
        yield json.dumps(make_text_chunk(payload.session_id, chunk), ensure_ascii=False) + "\n"

    yield json.dumps(make_stream_end(payload.session_id), ensure_ascii=False) + "\n"

    full_response = "".join(accumulated_chunks)
    await memory.messages.append_message(payload.session_id, "assistant", full_response)


@router.post("/process")
async def process_message(payload: IncomingMessage, request: Request) -> StreamingResponse:
    graph = request.app.state.graph
    memory = request.app.state.memory

    await memory.messages.append_message(payload.session_id, "user", payload.user_message)

    return StreamingResponse(
        _stream_agent_response(graph, memory, payload),
        media_type="application/x-ndjson",
    )