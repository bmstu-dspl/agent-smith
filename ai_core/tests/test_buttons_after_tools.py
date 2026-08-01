import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_core.api.routes.messages import router


class FakeMessages:
    async def append_tool_call(self, *args, **kwargs) -> None:
        return None

    async def append_message(self, *args, **kwargs) -> None:
        return None


class FakeMemory:
    messages = FakeMessages()


class McpThenAskUserGraph:
    async def adecide_buttons(self, payload):
        return []

    async def astream_response(
        self,
        payload,
        on_tool_call=None,
        on_ask_user=None,
    ):
        await on_tool_call(
            "mcp_example__search",
            {"query": "available options"},
            '{"items": ["standard", "priority"]}',
        )
        await on_ask_user(
            {
                "question": "Which option do you prefer?",
                "options": [
                    {
                        "label": "Standard",
                        "value": "standard",
                        "user_message": "I prefer the standard option.",
                    },
                    {
                        "label": "Priority",
                        "value": "priority",
                        "user_message": "I prefer the priority option.",
                    },
                ],
            },
            '{"status": "waiting_user"}',
        )
        if False:
            yield ""


def test_buttons_are_streamed_after_an_mcp_tool_result() -> None:
    app = FastAPI()
    app.include_router(router)
    app.state.graph = McpThenAskUserGraph()
    app.state.memory = FakeMemory()

    with TestClient(app) as client:
        response = client.post(
            "/agent/process",
            json={"session_id": "buttons-after-mcp", "user_message": "Find options"},
        )

    events = [json.loads(line) for line in response.text.splitlines()]
    button_events = [event for event in events if event["type"] == "buttons"]
    text = "".join(
        event["content"] for event in events if event["type"] == "text_chunk"
    )

    assert button_events[0]["buttons"] == []
    assert [button["text"] for button in button_events[1]["buttons"]] == [
        "Standard",
        "Priority",
    ]
    assert text == "Which option do you prefer?"
