import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ai_core.contracts.schemas import ButtonsMessage, IncomingMessage, make_stream_end, make_text_chunk

router = APIRouter(prefix="/agent", tags=["agent"])


async def _stream_agent_response(graph, payload: IncomingMessage) -> AsyncIterator[str]:
    """Генератор NDJSON-строк: сначала кнопки, потом текстовые чанки, потом сигнал конца."""

    # 1. Кнопки — единственная часть, которую валидируем через Pydantic,
    #    т.к. это одна законченная структура, а не поток.
    buttons = await graph.adecide_buttons(payload)
    buttons_msg = ButtonsMessage(session_id=payload.session_id, buttons=buttons)
    yield buttons_msg.model_dump_json() + "\n"

    # 2. Текстовые чанки — просто dict -> json, без Pydantic-модели (см. schemas.py).
    async for chunk in graph.astream_response(payload):
        yield json.dumps(make_text_chunk(payload.session_id, chunk), ensure_ascii=False) + "\n"

    # 3. Явный сигнал конца потока — чтобы бот знал, когда закончить сборку сообщения.
    yield json.dumps(make_stream_end(payload.session_id), ensure_ascii=False) + "\n"


@router.post("/process")
async def process_message(payload: IncomingMessage, request: Request) -> StreamingResponse:
    graph = request.app.state.graph
    return StreamingResponse(
        _stream_agent_response(graph, payload),
        media_type="application/x-ndjson",
    )