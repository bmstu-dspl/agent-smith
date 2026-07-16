from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ai_core.graph.prompts import AGENT_SYSTEM_PROMPT
from ai_core.graph.state import AgentState


def input_guard(state: AgentState) -> dict:
    user_message = state.get("user_message", "").strip()

    if not user_message:
        return {
              "blocked": True,
              "block_reason": "empty_message",
              "messages": [AIMessage(content="Пожалуйста, напишите ваш вопрос.")],
        }

    return {
        "blocked": False,
        "messages": [HumanMessage(content=user_message)],
    }


def route_after_input_guard(state: AgentState) -> Literal["agent", "end"]:
    if state.get("blocked"):
        return "end"
    return "agent"


class AgentNode:
    def __init__(self, llm) -> None:
        self.llm = llm

    async def __call__(self, state: AgentState) -> dict:
        messages = [
              SystemMessage(content=AGENT_SYSTEM_PROMPT),
              *state.get("messages", []),
        ]

        response = await self.llm.ainvoke(messages)

        return {
              "messages": [response],
              "answer": getattr(response, "content", ""),
        }


def tool_output_guard(state: AgentState) -> dict:
    # Заглушка под будущую проверку результатов tools/MCP/RAG.
    return {}
