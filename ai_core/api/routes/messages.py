import json
import re
import uuid
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


def _safe_callback_value(value: object) -> str:
    raw = str(value or "option").strip().lower()
    safe = re.sub(r"[^a-z0-9_-]+", "_", raw).strip("_")
    return safe or "option"


def _build_ask_user_buttons(args: dict) -> tuple[list[Button], dict[str, str], str]:
    question = str(args.get("question") or "").strip()
    options = args.get("options") or []

    buttons: list[Button] = []
    mapping: dict[str, str] = {}

    for option in options[:5]:
        if not isinstance(option, dict):
            continue

        label = str(option.get("label") or "").strip()
        user_message = str(option.get("user_message") or "").strip()
        value = _safe_callback_value(option.get("value"))

        if not label or not user_message:
            continue

        callback_data = f"reply:{value[:45]}:{uuid.uuid4().hex[:8]}"
        buttons.append(Button(text=label, callback_data=callback_data))
        mapping[callback_data] = user_message

    return buttons, mapping, question


async def _stream_agent_response(
    graph,
    memory: MemoryManager,
    payload: IncomingMessage,
) -> AsyncIterator[str]:
    initial_buttons: list[Button] = await graph.adecide_buttons(payload)
    yield ButtonsMessage(session_id=payload.session_id, buttons=initial_buttons).model_dump_json() + "\n"

    buttons_metadata: dict[str, str] = {b.callback_data: b.text for b in initial_buttons}
    pending_button_events: list[ButtonsMessage] = []
    pending_text_chunks: list[str] = []

    async def on_tool_call(name: str, args: dict, result: str) -> None:
        await memory.messages.append_tool_call(payload.session_id, tool_name=name, tool_args=args, tool_result=result)

    async def on_ask_user(args: dict, result: str) -> None:
        buttons, mapping, question = _build_ask_user_buttons(args)

        if buttons:
            buttons_metadata.update(mapping)
            pending_button_events.append(
                ButtonsMessage(session_id=payload.session_id, buttons=buttons)
            )

        if question:
            pending_text_chunks.append(question)

    async def flush_pending_events() -> AsyncIterator[str]:
        while pending_button_events:
            yield pending_button_events.pop(0).model_dump_json() + "\n"

        while pending_text_chunks:
            text = pending_text_chunks.pop(0)
            accumulated_chunks.append(text)
            yield json.dumps(make_text_chunk(payload.session_id, text), ensure_ascii=False) + "\n"

    accumulated_chunks: list[str] = []
    async for chunk in graph.astream_response(
        payload,
        on_tool_call=on_tool_call,
        on_ask_user=on_ask_user,
    ):
        async for event in flush_pending_events():
            yield event

        accumulated_chunks.append(chunk)
        yield json.dumps(make_text_chunk(payload.session_id, chunk), ensure_ascii=False) + "\n"

    async for event in flush_pending_events():
        yield event

    yield json.dumps(make_stream_end(payload.session_id), ensure_ascii=False) + "\n"
    full_response = "".join(accumulated_chunks)
    metadata = {"buttons": buttons_metadata} if buttons_metadata else {}
    await memory.messages.append_message(payload.session_id, "assistant", full_response, metadata=metadata)

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
    