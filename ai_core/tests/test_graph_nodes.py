import json

from langchain_core.messages import AIMessage, ToolMessage

from ai_core.graph.nodes import tool_output_guard


def _tool_message(payload: object, call_id: str) -> ToolMessage:
    content = payload if isinstance(payload, str) else json.dumps(payload)
    return ToolMessage(content=content, tool_call_id=call_id)


def test_tool_output_guard_uses_all_results_from_current_tool_batch() -> None:
    result = tool_output_guard(
        {
            "messages": [
                AIMessage(content="", tool_calls=[]),
                _tool_message({"status": "completed"}, "first"),
                _tool_message({"status": "waiting_user"}, "second"),
            ]
        }
    )

    assert result["blocked"] is True
    assert result["block_reason"] == "waiting_user"
    assert json.loads(result["tool_result"]) == {
        "results": [
            {"status": "completed"},
            {"status": "waiting_user"},
        ]
    }


def test_tool_output_guard_ignores_tool_messages_from_older_batches() -> None:
    result = tool_output_guard(
        {
            "messages": [
                _tool_message({"status": "waiting_user"}, "old"),
                AIMessage(content="", tool_calls=[]),
                _tool_message({"status": "completed"}, "current"),
            ]
        }
    )

    assert result["intent"] == "task_completed"
    assert "blocked" not in result


def test_tool_output_guard_preserves_single_result_shape() -> None:
    result = tool_output_guard(
        {"messages": [_tool_message({"status": "handoff_requested"}, "only")]}
    )

    assert result["intent"] == "handoff_to_operator"
    assert json.loads(result["tool_result"]) == {"status": "handoff_requested"}
