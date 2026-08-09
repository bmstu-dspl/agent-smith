import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ai_core.api.routes.messages import _claims_completed_handoff, _stream_agent_response
from ai_core.contracts.schemas import IncomingMessage


class FakeGraph:
    def __init__(self, text: str, *, call_handoff: bool = False) -> None:
        self.text = text
        self.call_handoff = call_handoff

    async def adecide_buttons(self, _payload):
        return []

    async def astream_response(self, _payload, *, on_tool_call, on_ask_user):
        if self.call_handoff:
            await on_tool_call(
                "handoff_to_operator",
                {"reason": "requested", "summary": "Нужен сотрудник"},
                '{"status":"handoff_requested"}',
            )
        yield self.text


def _memory():
    messages = SimpleNamespace(
        append_tool_call=AsyncMock(),
        append_message=AsyncMock(),
        get_handoff_history=AsyncMock(return_value=[]),
    )
    return SimpleNamespace(messages=messages)


async def _events(graph: FakeGraph, memory) -> list[dict]:
    payload = IncomingMessage(
        session_id="handoff-guard-test",
        user_message="Не могу найти фен",
        timestamp=datetime.now(timezone.utc),
    )
    return [
        json.loads(line)
        async for line in _stream_agent_response(graph, memory, payload)
    ]


def test_completed_handoff_claim_detector_ignores_offers_and_future_tense() -> None:
    assert _claims_completed_handoff("Я передала информацию администратору.")
    assert _claims_completed_handoff("Ваш запрос уже направлен менеджеру.")
    assert not _claims_completed_handoff("Я могу передать запрос администратору.")
    assert not _claims_completed_handoff("Давайте я передам запрос оператору.")


@pytest.mark.asyncio
async def test_claim_without_tool_call_emits_real_handoff_before_end() -> None:
    memory = _memory()
    events = await _events(
        FakeGraph("Спасибо! Я передала информацию администратору."),
        memory,
    )

    types = [event["type"] for event in events]
    assert types.count("handoff") == 1
    assert types.index("handoff") < types.index("end")
    handoff = next(event for event in events if event["type"] == "handoff")
    assert handoff["reason"] == "assistant_claimed_handoff"
    assert memory.messages.append_tool_call.await_args.kwargs["tool_result"].endswith(
        '"claimed_handoff_guard"}'
    )


@pytest.mark.asyncio
async def test_explicit_handoff_tool_call_is_not_duplicated_by_guard() -> None:
    events = await _events(
        FakeGraph("Я передала запрос оператору.", call_handoff=True),
        _memory(),
    )

    assert [event["type"] for event in events].count("handoff") == 1
