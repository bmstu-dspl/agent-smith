import json
import logging
import re
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ai_core.contracts.schemas import (
    Button,
    ButtonsMessage,
    HistoryItem,
    IncomingMessage,
    make_handoff,
    make_stream_end,
    make_text_chunk,
)
from memory import MemoryManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])

BUTTON_NOT_FOUND_MESSAGE = (
    "Не удалось распознать выбор — возможно, эта кнопка уже устарела. "
    "Пожалуйста, напишите ваш вопрос текстом."
)
STREAM_ERROR_MESSAGE = "Не удалось обработать ваш запрос — передаю обращение оператору."
STREAM_ERROR_REASON = "technical_error"
STREAM_ERROR_SUMMARY = "Сбой при генерации ответа агента, требуется вмешательство оператора."

HANDOFF_HOURS = 24
HANDOFF_FALLBACK_COUNT = 20


def _safe_callback_value(value: object) -> str:
    raw = str(value or "option").strip().lower()
    safe = re.sub(r"[^a-z0-9_-]+", "_", raw).strip("_")
    return safe or "option"


def _normalized_visible_text(value: str) -> str:
    return " ".join(value.split())


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


async def _build_handoff_history(memory: MemoryManager, session_id: str) -> list[HistoryItem]:
    """Сообщения диалога за последние сутки; если их слишком мало — последние HANDOFF_FALLBACK_COUNT сообщений.
    Если БД недоступна — возвращает пустую историю, но не роняет весь стрим."""
    try:
        history = await memory.messages.get_handoff_history(
            session_id, hours=HANDOFF_HOURS, fallback_count=HANDOFF_FALLBACK_COUNT
        )
    except Exception:
        logger.exception("failed to build handoff history for session_id=%s", session_id)
        return []
    return [
        {
            "role": item["role"],
            "content": item["content"],
            "created_at": item["created_at"].isoformat(),
        }
        for item in history
    ]


async def _yield_handoff(memory: MemoryManager, session_id: str, reason: str, summary: str) -> AsyncIterator[str]:
    """Формирует и отдаёт в поток одну handoff-строку с актуальной историей диалога."""
    history = await _build_handoff_history(memory, session_id)
    yield json.dumps(make_handoff(session_id, reason=reason, summary=summary, history=history), ensure_ascii=False) + "\n"


async def _stream_agent_response(
    graph,
    memory: MemoryManager,
    payload: IncomingMessage,
) -> AsyncIterator[str]:
    try:
        initial_buttons: list[Button] = await graph.adecide_buttons(payload)
    except Exception:
        logger.exception("adecide_buttons failed for session_id=%s", payload.session_id)
        initial_buttons = []

    yield ButtonsMessage(session_id=payload.session_id, buttons=initial_buttons).model_dump_json() + "\n"

    buttons_metadata: dict[str, str] = {b.callback_data: b.text for b in initial_buttons}
    pending_button_events: list[ButtonsMessage] = []
    pending_text_chunks: list[str] = []
    handoff_events: list[dict] = []
    accumulated_chunks: list[str] = []

    async def on_tool_call(name: str, args: dict, result: str) -> None:
        audit_result = result
        if name == "load_skill":
            try:
                parsed = json.loads(result)
            except (TypeError, json.JSONDecodeError):
                parsed = {"status": "invalid_tool_output"}
            if isinstance(parsed, dict):
                audit_result = json.dumps(
                    {
                        key: parsed[key]
                        for key in ("status", "skill_id", "name", "version")
                        if key in parsed
                    },
                    ensure_ascii=False,
                )
        try:
            await memory.messages.append_tool_call(
                payload.session_id,
                tool_name=name,
                tool_args=args,
                tool_result=audit_result,
            )
        except Exception:
            logger.exception("failed to persist tool call session_id=%s tool=%s", payload.session_id, name)
        if name == "handoff_to_operator":
            handoff_events.append({"reason": args.get("reason", ""), "summary": args.get("summary", "")})

    async def on_ask_user(args: dict, result: str) -> None:
        try:
            parsed_result = json.loads(result)
        except (TypeError, json.JSONDecodeError):
            parsed_result = None
        if not isinstance(parsed_result, dict) or parsed_result.get("status") != "waiting_user":
            return

        buttons, mapping, question = _build_ask_user_buttons(args)

        if buttons:
            buttons_metadata.update(mapping)
            pending_button_events.append(
                ButtonsMessage(session_id=payload.session_id, buttons=buttons)
            )

        # ask_user is authoritative for the visible question. Some models also
        # emit the same sentence immediately before the tool call; do not add a
        # second copy when that text is already present in the response stream.
        visible_text = _normalized_visible_text(
            "".join([*accumulated_chunks, *pending_text_chunks])
        )
        normalized_question = _normalized_visible_text(question)
        if normalized_question and not visible_text.endswith(normalized_question):
            pending_text_chunks.append(question)

    async def flush_pending_events() -> AsyncIterator[str]:
        while pending_button_events:
            yield pending_button_events.pop(0).model_dump_json() + "\n"

        while pending_text_chunks:
            text = pending_text_chunks.pop(0)
            accumulated_chunks.append(text)
            yield json.dumps(make_text_chunk(payload.session_id, text), ensure_ascii=False) + "\n"

    stream_failed = False

    try:
        async for chunk in graph.astream_response(
            payload,
            on_tool_call=on_tool_call,
            on_ask_user=on_ask_user,
        ):
            async for event in flush_pending_events():
                yield event

            accumulated_chunks.append(chunk)
            yield json.dumps(make_text_chunk(payload.session_id, chunk), ensure_ascii=False) + "\n"

            while handoff_events:
                event = handoff_events.pop(0)
                async for line in _yield_handoff(memory, payload.session_id, **event):
                    yield line
    except Exception:
        logger.exception("graph.astream_response failed for session_id=%s", payload.session_id)
        stream_failed = True

        try:
            await memory.messages.append_tool_call(
                payload.session_id,
                tool_name="handoff_to_operator",
                tool_args={"reason": STREAM_ERROR_REASON, "summary": STREAM_ERROR_SUMMARY},
                tool_result='{"status": "handoff_requested", "trigger": "stream_error"}',
            )
        except Exception:
            logger.exception("failed to persist auto-handoff tool call for session_id=%s", payload.session_id)

        yield json.dumps(make_text_chunk(payload.session_id, STREAM_ERROR_MESSAGE), ensure_ascii=False) + "\n"
        accumulated_chunks.append(STREAM_ERROR_MESSAGE)
        async for line in _yield_handoff(memory, payload.session_id, STREAM_ERROR_REASON, STREAM_ERROR_SUMMARY):
            yield line

    async for event in flush_pending_events():
        yield event

    # handoff мог произойти на последнем шаге, когда текста после него больше не было
    while handoff_events:
        event = handoff_events.pop(0)
        async for line in _yield_handoff(memory, payload.session_id, **event):
            yield line

    yield json.dumps(make_stream_end(payload.session_id), ensure_ascii=False) + "\n"

    full_response = "".join(accumulated_chunks)
    metadata = {"buttons": buttons_metadata} if buttons_metadata else {}
    try:
        await memory.messages.append_message(payload.session_id, "assistant", full_response, metadata=metadata)
    except Exception:
        logger.exception("failed to persist assistant message for session_id=%s", payload.session_id)


async def _stream_fallback_message(session_id: str, text: str) -> AsyncIterator[str]:
    """Короткий поток без обращения к графу — используется, когда callback_data
    не удалось распознать."""
    empty_buttons = ButtonsMessage(session_id=session_id, buttons=[])
    yield empty_buttons.model_dump_json() + "\n"
    yield json.dumps(make_text_chunk(session_id, text), ensure_ascii=False) + "\n"
    yield json.dumps(make_stream_end(session_id), ensure_ascii=False) + "\n"


@router.post("/process")
async def process_message(payload: IncomingMessage, request: Request) -> StreamingResponse:
    graph_provider = getattr(request.app.state, "graph_provider", None)
    graph = (
        await graph_provider.get_graph()
        if graph_provider is not None
        else request.app.state.graph
    )
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
