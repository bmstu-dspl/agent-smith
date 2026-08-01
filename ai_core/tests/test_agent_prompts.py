from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
import pytest

from ai_core.graph.nodes import AgentNode


class RecordingLlm:
    def __init__(self) -> None:
        self.messages = []

    async def ainvoke(self, messages):
        self.messages = messages
        return AIMessage(content="ok")


@pytest.mark.asyncio
async def test_agent_receives_neutral_core_workflows_and_configurable_persona() -> None:
    llm = RecordingLlm()
    persona = "You are a hotel concierge. Answer in English."
    node = AgentNode(llm, persona_prompt=persona)

    await node({"messages": [HumanMessage(content="Hello")]})

    system_messages = [
        message for message in llm.messages if isinstance(message, SystemMessage)
    ]
    assert len(system_messages) == 2
    core_prompt = system_messages[0].content
    assert "ask_user" in core_prompt
    assert "get_current_datetime" in core_prompt
    assert "Если вопрос сложный, возникла ошибка" in core_prompt
    assert "handoff_to_operator" in core_prompt
    assert "отел" not in core_prompt.lower()
    assert system_messages[1].content == persona
