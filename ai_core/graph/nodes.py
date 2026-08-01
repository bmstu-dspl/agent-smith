import asyncio
from datetime import date, datetime
import json
import re
from typing import Literal
from zoneinfo import ZoneInfo
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from ai_core.graph.prompts import (
    CORE_SYSTEM_PROMPT,
    DEFAULT_PERSONA_PROMPT,
    RAG_QUERY_EXTRACTOR_PROMPT,
)
from ai_core.graph.state import AgentState
from RAG import BuildAgentContextQuery
from pydantic import ValidationError
from ai_core.graph.rag_query import RagSearchRequest


_DATE_PATTERNS = (
    re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?$"),
    re.compile(r"^(\d{2})[-./](\d{2})[-./](\d{4})$"),
)


def _parsed_dates(value: object) -> list[date]:
    if isinstance(value, dict):
        return [parsed for item in value.values() for parsed in _parsed_dates(item)]
    if isinstance(value, list):
        return [parsed for item in value for parsed in _parsed_dates(item)]
    if not isinstance(value, str):
        return []

    candidate = value.strip()
    for index, pattern in enumerate(_DATE_PATTERNS):
        match = pattern.match(candidate)
        if not match:
            continue
        parts = [int(part) for part in match.groups()]
        try:
            if index == 0:
                return [date(parts[0], parts[1], parts[2])]
            return [date(parts[2], parts[1], parts[0])]
        except ValueError:
            return []
    return []


def _latest_tool_calls(state: AgentState) -> list[dict]:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, AIMessage):
            return list(message.tool_calls or [])
    return []


def _has_current_datetime_context(state: AgentState) -> bool:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return False
        if not isinstance(message, ToolMessage):
            continue
        if message.name == "get_current_datetime":
            return True
        if message.additional_kwargs.get("date_guard_checked") is True:
            return True
    return False


def route_after_agent_with_date_guard(
    state: AgentState,
    *,
    primary_timezone: str,
) -> Literal["tools", "date_guard", "__end__"]:
    calls = _latest_tool_calls(state)
    if not calls:
        return "__end__"

    dates = [
        parsed
        for call in calls
        for parsed in _parsed_dates(call.get("args", {}))
    ]
    if not dates:
        return "tools"

    today = datetime.now(ZoneInfo(primary_timezone)).date()
    if any(candidate < today for candidate in dates):
        return "date_guard"
    if not _has_current_datetime_context(state):
        return "date_guard"
    return "tools"


class DateToolGuardNode:
    def __init__(self, current_datetime_tool) -> None:
        self.current_datetime_tool = current_datetime_tool

    async def __call__(self, state: AgentState) -> dict:
        current = await self.current_datetime_tool.ainvoke({})
        today = date.fromisoformat(current["primary_date"])
        calls = _latest_tool_calls(state)
        messages = []
        for call in calls:
            parsed_dates = _parsed_dates(call.get("args", {}))
            past_dates = sorted(
                candidate.isoformat() for candidate in parsed_dates if candidate < today
            )
            messages.append(
                ToolMessage(
                    content=json.dumps(
                        {
                            "status": "blocked_for_date_validation",
                            "reason": (
                                "date_is_in_the_past"
                                if past_dates
                                else "current_datetime_required"
                            ),
                            "past_dates": past_dates,
                            "current_datetime": current,
                            "instruction": (
                                "Reconstruct all dates from the user's request using the "
                                "current datetime, then retry the external tool call."
                            ),
                        }
                    ),
                    tool_call_id=call["id"],
                    name=call["name"],
                    additional_kwargs={"date_guard_checked": True},
                )
            )
        return {"messages": messages}


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
        persona_prompt: str = DEFAULT_PERSONA_PROMPT,
        core_prompt: str = CORE_SYSTEM_PROMPT,
        rag_instructions: str = "",
    ) -> None:
        self.llm = llm
        self.persona_prompt = persona_prompt
        self.core_prompt = core_prompt
        self.rag_instructions = rag_instructions

    async def __call__(self, state: AgentState) -> dict:
        messages = [
            SystemMessage(content=self.core_prompt),
            SystemMessage(content=self.persona_prompt),
        ]
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
