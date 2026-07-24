import asyncio
import json
from typing import Literal
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from ai_core.graph.prompts import AGENT_SYSTEM_PROMPT, RAG_QUERY_EXTRACTOR_PROMPT
from ai_core.graph.state import AgentState
from RAG import BuildAgentContextQuery
from pydantic import ValidationError
from ai_core.graph.rag_query import RagSearchRequest

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
    def __init__(
        self,
        llm,
        *,
        system_prompt: str = AGENT_SYSTEM_PROMPT,
        rag_instructions: str = "",
    ) -> None:
        self.llm = llm
        self.system_prompt = system_prompt
        self.rag_instructions = rag_instructions

    async def __call__(self, state: AgentState) -> dict:
        messages = [SystemMessage(content=self.system_prompt)]
        rag_context = state.get("rag_context") or ""
        if rag_context:
            additional = (
                f"\n\nДополнительные правила использования базы знаний:\n{self.rag_instructions}"
                if self.rag_instructions
                else ""
            )
            messages.append(SystemMessage(
                content=("Контекст базы знаний для текущего ответа. "
                         "Используй его только если он релевантен вопросу пользователя. "
                         "Если в контексте нет ответа, не выдумывай.\n\n"
                         f"{rag_context}{additional}")
            ))
        messages.extend(state.get("messages", []))
        response = await self.llm.ainvoke(messages)
        return {"messages": [response], "answer": getattr(response, "content", "")}


class RagRetrievalNode:
    def __init__(
        self,
        memory,
        *,
        limit: int = 8,
        max_context_chars: int = 12_000,
        retrieval_mode: str = "hybrid",
    ) -> None:
        self.memory = memory
        self.limit = limit
        self.max_context_chars = max_context_chars
        self.retrieval_mode = retrieval_mode

    async def __call__(self, state: AgentState) -> dict:
        rag_query = state.get("rag_query", "").strip()
        metadata = state.get("metadata", {})
        tenant_id = str(metadata.get("tenant_id") or metadata.get("user_id") or "default")
        if not rag_query:
            return {"rag_context": ""}
        query = BuildAgentContextQuery(
            tenant_id=tenant_id,
            query=rag_query,
            limit=self.limit,
            max_context_chars=self.max_context_chars,
            retrieval_mode=self.retrieval_mode,
        )
        context = await asyncio.to_thread(self.memory.build_agent_context, query)
        return {"rag_context": context.context_text}


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
    # ToolNode can execute several tool calls from one AIMessage. Only the
    # contiguous ToolMessage suffix belongs to the current tools invocation;
    # older ToolMessages in the conversation must not affect this decision.
    tool_messages: list[ToolMessage] = []
    for message in reversed(state.get("messages", [])):
        if not isinstance(message, ToolMessage):
            break
        tool_messages.append(message)
    tool_messages.reverse()

    if not tool_messages:
        return {}

    payloads = [_parse_tool_payload(message.content) for message in tool_messages]
    statuses = {str(payload.get("status") or "").strip() for payload in payloads}
    serialized_result: object = payloads[0] if len(payloads) == 1 else {"results": payloads}
    tool_result = json.dumps(serialized_result, ensure_ascii=False)

    if "waiting_user" in statuses:
        return {
            "blocked": True,
            "block_reason": "waiting_user",
            "tool_result": tool_result,
        }

    if "invalid_tool_output" in statuses:
        return {
            "intent": "tool_error",
            "tool_result": tool_result,
        }

    if "handoff_requested" in statuses:
        return {
            "intent": "handoff_to_operator",
            "tool_result": tool_result,
        }

    if "completed" in statuses:
        return {
            "intent": "task_completed",
            "tool_result": tool_result,
        }

    return {"tool_result": tool_result}


def route_after_tool_output_guard(state: AgentState) -> Literal["agent", "end"]:
    if state.get("blocked") and state.get("block_reason") == "waiting_user":
        return "end"
    return "agent"


def _extract_json_object(text: str) -> dict:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").removeprefix("json").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(raw[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("RAG query extractor returned non-object JSON")
    return parsed


class RagQueryExtractorNode:
    def __init__(self, llm) -> None:
        self.llm = llm

    async def __call__(self, state: AgentState) -> dict:
        user_message = state.get("user_message", "").strip()
        if not user_message:
            return {"rag_query": "", "rag_topic": ""}
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content=RAG_QUERY_EXTRACTOR_PROMPT),
                HumanMessage(content=user_message),
            ])
        except Exception:
            return {"rag_query": "", "rag_topic": ""}

        content = getattr(response, "content", "")
        if not isinstance(content, str):
            content = str(content)
        try:
            payload = _extract_json_object(content)
            request = RagSearchRequest.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, ValueError):
            return {"rag_query": "", "rag_topic": ""}
        return {"rag_query": request.to_query(), "rag_topic": request.topic}
