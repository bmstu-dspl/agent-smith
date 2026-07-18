import json
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from ai_core.graph.prompts import AGENT_SYSTEM_PROMPT
from ai_core.graph.state import AgentState

from RAG import BuildAgentContextQuery


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
        rag_context = state.get("rag_context") or ""
        system_prompt = AGENT_SYSTEM_PROMPT
        if rag_context:
            system_prompt += (
                "\n\nКонтекст из базы знаний:\n"
                f"{rag_context}\n\n"
                "Используй этот контекст, если он релевантен вопросу пользователя. "
                "Если ответа в контексте нет, не выдумывай и скажи, что данных недостаточно."
            )

        messages = [
              SystemMessage(content=system_prompt),
              *state.get("messages", []),
        ]

        response = await self.llm.ainvoke(messages)

        return {
              "messages": [response],
              "answer": getattr(response, "content", ""),
        }


class RagRetrievalNode:
    def __init__(self, memory) -> None:
        self.memory = memory

    async def __call__(self, state: AgentState) -> dict:
        query = state.get("user_message", "").strip()
        metadata = state.get("metadata", {})
        tenant_id = str(
            metadata.get("tenant_id")
            or metadata.get("user_id")
            or "default"
        )
        if not query:
            return {"rag_context": ""}
        context = self.memory.build_agent_context(
            BuildAgentContextQuery(
                tenant_id=tenant_id,
                query=query,
                limit=8,
                max_context_chars=12_000,
            )
        )
        return {
            "rag_context": context.context_text,
        }


def _parse_tool_payload(content: object) -> dict:
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        return {"status": "invalid_tool_output", "raw": str(content)}

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {"status": "invalid_tool_output", "raw": content}

    if isinstance(parsed, dict):
        return parsed
    return {"status": "invalid_tool_output", "raw": parsed}


def tool_output_guard(state: AgentState) -> dict:
    tool_messages = [
        message
        for message in state.get("messages", [])
        if isinstance(message, ToolMessage)
    ]
    if not tool_messages:
        return {}

    payload = _parse_tool_payload(tool_messages[-1].content)
    status = str(payload.get("status") or "").strip()
    tool_result = json.dumps(payload, ensure_ascii=False)

    if status == "waiting_user":
        return {
            "blocked": True,
            "block_reason": "waiting_user",
            "tool_result": tool_result,
        }

    if status == "handoff_requested":
        return {
            "intent": "handoff_to_operator",
            "tool_result": tool_result,
        }

    if status == "completed":
        return {
            "intent": "task_completed",
            "tool_result": tool_result,
        }

    if status == "invalid_tool_output":
        return {
            "intent": "tool_error",
            "tool_result": tool_result,
        }

    return {"tool_result": tool_result}


def route_after_tool_output_guard(state: AgentState) -> Literal["agent", "end"]:
    if state.get("blocked") and state.get("block_reason") == "waiting_user":
        return "end"
    return "agent"
