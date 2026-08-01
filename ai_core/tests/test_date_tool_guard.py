import json
from datetime import datetime, timezone

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
import pytest

from ai_core.graph.nodes import DateToolGuardNode, route_after_agent_with_date_guard
from ai_core.tools import create_current_datetime_tool


def _external_date_call(value: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "id": "search-1",
                "name": "mcp_example__search",
                "args": {"check_in": value, "adults": 2},
            }
        ],
    )


def test_date_tool_call_is_blocked_until_current_time_is_in_context() -> None:
    state = {
        "messages": [
            HumanMessage(content="Find availability on August 15"),
            _external_date_call("2999-08-15"),
        ]
    }

    assert (
        route_after_agent_with_date_guard(state, primary_timezone="UTC")
        == "date_guard"
    )


def test_future_date_tool_call_runs_after_time_context_is_available() -> None:
    state = {
        "messages": [
            HumanMessage(content="Find availability on August 15"),
            ToolMessage(
                content='{"primary_date":"2026-08-01"}',
                tool_call_id="time-1",
                name="get_current_datetime",
            ),
            _external_date_call("2999-08-15"),
        ]
    }

    assert route_after_agent_with_date_guard(state, primary_timezone="UTC") == "tools"


def test_past_date_is_blocked_even_after_time_context() -> None:
    state = {
        "messages": [
            HumanMessage(content="Find availability"),
            ToolMessage(
                content='{"primary_date":"2026-08-01"}',
                tool_call_id="time-1",
                name="get_current_datetime",
            ),
            _external_date_call("2000-08-15"),
        ]
    }

    assert (
        route_after_agent_with_date_guard(state, primary_timezone="UTC")
        == "date_guard"
    )


@pytest.mark.asyncio
async def test_date_guard_returns_runtime_time_and_rejects_past_date() -> None:
    tool = create_current_datetime_tool(
        "Europe/Moscow",
        clock=lambda: datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc),
    )
    node = DateToolGuardNode(tool)

    result = await node(
        {
            "messages": [
                HumanMessage(content="Find availability"),
                _external_date_call("15-08-2024"),
            ]
        }
    )

    payload = json.loads(result["messages"][0].content)
    assert payload["reason"] == "date_is_in_the_past"
    assert payload["past_dates"] == ["2024-08-15"]
    assert payload["current_datetime"]["primary_date"] == "2026-08-01"
    assert result["messages"][0].additional_kwargs["date_guard_checked"] is True
