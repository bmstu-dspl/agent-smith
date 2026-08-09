import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_core.api.routes.messages import router


class FakeMessages:
    def __init__(self):
        self.tool_calls = []

    async def append_tool_call(self, *args, **kwargs) -> None:
        self.tool_calls.append(kwargs)

    async def append_message(self, *args, **kwargs) -> None:
        return None


class FakeMemory:
    def __init__(self):
        self.messages = FakeMessages()


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


class ModelTextThenAskUserGraph(McpThenAskUserGraph):
    async def astream_response(
        self,
        payload,
        on_tool_call=None,
        on_ask_user=None,
    ):
        question = "How many guests will stay?"
        yield question
        await on_ask_user(
            {
                "question": question,
                "options": [
                    {
                        "label": "Two",
                        "value": "2",
                        "user_message": "There will be two guests.",
                    }
                ],
            },
            '{"status": "waiting_user"}',
        )


def test_ask_user_does_not_duplicate_question_already_emitted_by_model() -> None:
    app = FastAPI()
    app.include_router(router)
    app.state.graph = ModelTextThenAskUserGraph()
    app.state.memory = FakeMemory()

    with TestClient(app) as client:
        response = client.post(
            "/agent/process",
            json={"session_id": "single-question", "user_message": "Find a room"},
        )

    events = [json.loads(line) for line in response.text.splitlines()]
    text = "".join(
        event["content"] for event in events if event["type"] == "text_chunk"
    )
    button_events = [event for event in events if event["type"] == "buttons"]

    assert text == "How many guests will stay?"
    assert [button["text"] for button in button_events[-1]["buttons"]] == ["Two"]


class FailedThenSuccessfulAskUserGraph(McpThenAskUserGraph):
    async def astream_response(
        self,
        payload,
        on_tool_call=None,
        on_ask_user=None,
    ):
        question = "How many guests will stay?"
        failed_args = {"question": question, "options": ["One", "Two"]}
        await on_ask_user(
            failed_args,
            "Error invoking tool 'ask_user': options must contain objects",
        )
        await on_tool_call(
            "ask_user",
            failed_args,
            "Error invoking tool 'ask_user': options must contain objects",
        )
        successful_args = {
            "question": question,
            "options": [
                {
                    "label": "Two",
                    "value": "2",
                    "user_message": "There will be two guests.",
                }
            ],
        }
        await on_ask_user(
            successful_args,
            json.dumps({"status": "waiting_user", "question": question}),
        )
        await on_tool_call(
            "ask_user",
            successful_args,
            json.dumps({"status": "waiting_user", "question": question}),
        )
        if False:
            yield ""


def test_failed_ask_user_retry_emits_one_question_and_keyboard() -> None:
    app = FastAPI()
    app.include_router(router)
    app.state.graph = FailedThenSuccessfulAskUserGraph()
    app.state.memory = FakeMemory()

    with TestClient(app) as client:
        response = client.post(
            "/agent/process",
            json={"session_id": "ask-retry", "user_message": "Find a room"},
        )

    events = [json.loads(line) for line in response.text.splitlines()]
    text = "".join(
        event["content"] for event in events if event["type"] == "text_chunk"
    )
    button_events = [event for event in events if event["type"] == "buttons"]

    assert text == "How many guests will stay?"
    assert [button["text"] for button in button_events[-1]["buttons"]] == ["Two"]


class LoadSkillGraph:
    async def adecide_buttons(self, payload):
        return []

    async def astream_response(self, payload, on_tool_call=None, on_ask_user=None):
        await on_tool_call(
            "load_skill",
            {"name": "room-availability"},
            json.dumps(
                {
                    "status": "loaded",
                    "skill_id": "skill-1",
                    "name": "room-availability",
                    "version": 4,
                    "instructions": "secret full workflow body",
                }
            ),
        )
        yield "Ready."


def test_load_skill_audit_entry_omits_the_full_instruction_body() -> None:
    app = FastAPI()
    app.include_router(router)
    app.state.graph = LoadSkillGraph()
    memory = FakeMemory()
    app.state.memory = memory

    with TestClient(app) as client:
        response = client.post(
            "/agent/process",
            json={"session_id": "skill-audit", "user_message": "Find a room"},
        )

    assert response.status_code == 200
    assert memory.messages.tool_calls == [
        {
            "tool_name": "load_skill",
            "tool_args": {"name": "room-availability"},
            "tool_result": json.dumps(
                {
                    "status": "loaded",
                    "skill_id": "skill-1",
                    "name": "room-availability",
                    "version": 4,
                },
                ensure_ascii=False,
            ),
        }
    ]
