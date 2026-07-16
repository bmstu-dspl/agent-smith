import pytest
from unittest.mock import AsyncMock

from ai_core.contracts.schemas import IncomingMessage

# вызов: uv run python -m  pytest memory/tests/test_tool_call_logging.py -v -s
class FakeToolCallGraph:
    """Симулирует граф с одним tool-вызовом, без реальной LLM."""

    async def adecide_buttons(self, payload):
        return []

    async def astream_response(self, payload, on_tool_call=None):
        if on_tool_call is not None:
            await on_tool_call(
                "handoff_to_operator",
                {"reason": "сложный вопрос", "summary": "пользователь просит оператора"},
                '{"status": "handoff_requested"}',
            )
        yield "Передаю ваш вопрос оператору."


@pytest.mark.asyncio
async def test_tool_call_is_logged_to_memory(messages_store):
    graph = FakeToolCallGraph()
    payload = IncomingMessage(session_id="test-tool-log", user_message="позовите оператора")

    async def on_tool_call(name, args, result):
        await messages_store.append_tool_call(payload.session_id, tool_name=name, tool_args=args, tool_result=result)

    async for _ in graph.astream_response(payload, on_tool_call=on_tool_call):
        pass

    history = await messages_store.get_full_history(payload.session_id, include_drafts=True)
    tool_entries = [m for m in history if m["role"] == "tool"]
    print("\n\n=== ЗАПИСИ В БД ===")
    for entry in history:
        print(entry)
    print("===================\n")
    assert len(tool_entries) == 1
    assert tool_entries[0]["metadata"]["tool_name"] == "handoff_to_operator"
    assert tool_entries[0]["metadata"]["tool_args"]["reason"] == "сложный вопрос"