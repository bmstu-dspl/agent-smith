import asyncio
import json
import os
from collections.abc import AsyncIterator

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from mcp_registry import McpServerStore
from mcp_registry.client import McpToolProvider

from ai_core.contracts.schemas import Button, IncomingMessage
from ai_core.graph.nodes import (
    AgentNode,
    DateToolGuardNode,
    RagRetrievalNode,
    RagQueryExtractorNode,
    input_guard,
    route_after_input_guard,
    route_after_agent_with_date_guard,
    route_after_tool_output_guard,
    tool_output_guard,
)
from ai_core.graph.state import AgentState
from ai_core.graph.prompts import DEFAULT_PERSONA_PROMPT
from ai_core.tools import ToolRegistry, create_current_datetime_tool
from admin_panel.settings import AgentSettings, RagSettings
from admin_panel.skills import AgentSkill


class StubGraph:
    """Fallback-граф без LLM и внешних tools для локального запуска без ключей."""

    async def adecide_buttons(self, payload: IncomingMessage) -> list[Button]:
        return []

    async def astream_response(
        self,
        payload: IncomingMessage,
        on_tool_call=None,
        on_ask_user=None,
    ) -> AsyncIterator[str]:
        fake_answer = (
            f"Вы написали: «{payload.user_message}». "
            f"Это потоковый ответ-заглушка, скоро здесь будет настоящий LLM."
        )
        words = fake_answer.split(" ")
        for word in words:
            await asyncio.sleep(0.05)
            yield word + " "


def _chunk_to_text(chunk: object) -> str:
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def build_llm(settings: AgentSettings | None = None):
    provider = (
        settings.provider
        if settings is not None
        else os.getenv("LLM_PROVIDER", "google_vertex").strip().lower()
    )
    model = settings.model if settings is not None else os.getenv("LLM_MODEL", "gemini-2.5-flash")
    temperature = settings.temperature if settings is not None else 0.2

    if provider in {"google_vertex", "vertex"}:
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

        if not project or not credentials_path:
            return None

        return ChatGoogleGenerativeAI(
            model=model,
            vertexai=True,
            project=project,
            location=(
                settings.vertex_location
                if settings is not None
                else os.getenv("GOOGLE_CLOUD_LOCATION", "global")
            ),
            temperature=temperature,
        )

    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            return None

        return ChatOpenAI(
            model=model,
            temperature=temperature,
        )

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")


def build_rag_extractor_llm(default_llm, *, vertex_location: str = "global"):
    provider = os.getenv("RAG_EXTRACTOR_LLM_PROVIDER", "google_vertex").strip().lower()
    if provider in {"", "same", "default"}:
        return default_llm

    model = os.getenv("RAG_EXTRACTOR_LLM_MODEL", "gemini-2.5-flash-lite").strip()

    if provider in {"google_vertex", "vertex"}:
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

        if not project or not credentials_path:
            return default_llm

        return ChatGoogleGenerativeAI(
            model=model,
            vertexai=True,
            project=project,
            location=vertex_location,
            temperature=0,
        )

    raise ValueError(f"Unsupported RAG_EXTRACTOR_LLM_PROVIDER: {provider}")


def build_langgraph(
    llm,
    tool_registry: ToolRegistry,
    checkpointer=None,
    rag_memory=None,
    rag_extractor_llm=None,
    *,
    agent_settings: AgentSettings | None = None,
    rag_settings: RagSettings | None = None,
    skills: tuple[AgentSkill, ...] = (),
):
    tools = tool_registry.get_tools()
    agent_llm = llm.bind_tools(tools) if tools else llm
    primary_timezone = (
        agent_settings.primary_timezone if agent_settings is not None else "UTC"
    )

    workflow = StateGraph(AgentState)

    workflow.add_node("input_guard", input_guard)
    workflow.add_node(
        "agent",
        AgentNode(
            agent_llm,
            persona_prompt=(
                agent_settings.system_prompt
                if agent_settings
                else DEFAULT_PERSONA_PROMPT
            ),
            rag_instructions=rag_settings.additional_instructions if rag_settings else "",
            skills=skills,
        ),
    )
    if rag_memory is not None:
        workflow.add_node("rag_query_extractor", RagQueryExtractorNode(rag_extractor_llm or llm))
        workflow.add_node(
            "rag_retrieval",
            RagRetrievalNode(
                rag_memory,
                limit=rag_settings.limit if rag_settings else 8,
                max_context_chars=rag_settings.max_context_chars if rag_settings else 12_000,
                retrieval_mode=rag_settings.retrieval_mode if rag_settings else "hybrid",
            ),
        )
        next_node_after_guard = "rag_query_extractor"
        workflow.add_edge("rag_query_extractor", "rag_retrieval")
        workflow.add_edge("rag_retrieval", "agent")
    else:
        next_node_after_guard = "agent"

    workflow.add_edge(START, "input_guard")

    workflow.add_conditional_edges(
        "input_guard",
        route_after_input_guard,
        {
            "agent": next_node_after_guard,
            "end": END,
        },
    )

    if tools:
        workflow.add_node("tools", ToolNode(tools))
        workflow.add_node(
            "date_guard",
            DateToolGuardNode(create_current_datetime_tool(primary_timezone)),
        )
        workflow.add_node("tool_output_guard", tool_output_guard)
        workflow.add_conditional_edges(
            "agent",
            lambda state: route_after_agent_with_date_guard(
                state,
                primary_timezone=primary_timezone,
            ),
            {
                "tools": "tools",
                "date_guard": "date_guard",
                "__end__": END,
            },
        )
        workflow.add_edge("date_guard", "agent")
        workflow.add_edge("tools", "tool_output_guard")
        workflow.add_conditional_edges(
            "tool_output_guard",
            route_after_tool_output_guard,
            {
                "agent": "agent",
                "end": END,
            },
        )
    else:
        workflow.add_edge("agent", END)

    if checkpointer is not None:
        return workflow.compile(checkpointer=checkpointer)

    return workflow.compile()


class AgentGraph(StubGraph):
    def __init__(self, graph, tool_registry: ToolRegistry) -> None:
        self.graph = graph
        self.tool_registry = tool_registry

    async def adecide_buttons(self, payload: IncomingMessage) -> list[Button]:
        return []

    async def astream_response(
        self,
        payload: IncomingMessage,
        on_tool_call=None,
        on_ask_user=None,
    ) -> AsyncIterator[str]:
        yielded_text = False
        waiting_for_user = False
        pending_calls: dict[str, dict] = {}  # tool_call_id -> {"name": ..., "args": ...}

        async for chunk, metadata in self.graph.astream(
            {
                "session_id": payload.session_id,
                "user_message": payload.user_message,
                "message_type": payload.message_type,
                "metadata": payload.metadata,
                "messages": [],
            },
            config={"configurable": {"thread_id": payload.session_id}},
            stream_mode="messages",
        ):
            node = metadata.get("langgraph_node")

            if node == "agent":
                text = _chunk_to_text(chunk)
                if text:
                    yielded_text = True
                    yield text

                # AIMessage с tool_calls — запоминаем намерение, ждём результат
                tool_calls = getattr(chunk, "tool_calls", None)
                if tool_calls:
                    for call in tool_calls:
                        pending_calls[call["id"]] = {"name": call["name"], "args": call.get("args", {})}

            elif node in {"tools", "date_guard"}:
                # ToolMessage — результат. Как только пришёл — сразу пишем одну запись
                # с args (из pending_calls) и result вместе.
                call_id = getattr(chunk, "tool_call_id", None)
                if call_id in pending_calls:
                    info = pending_calls.pop(call_id)
                    tool_name = info["name"]
                    tool_args = info["args"]
                    tool_result = _chunk_to_text(chunk)

                    if tool_name in {"ask_user", "request_clarification"} and on_ask_user is not None:
                        try:
                            parsed_tool_result = json.loads(tool_result)
                        except (TypeError, json.JSONDecodeError):
                            parsed_tool_result = None
                        if (
                            isinstance(parsed_tool_result, dict)
                            and parsed_tool_result.get("status") == "waiting_user"
                        ):
                            waiting_for_user = True
                            await on_ask_user(tool_args, tool_result)

                    if on_tool_call is not None:
                        await on_tool_call(tool_name, tool_args, tool_result)

        if not yielded_text and not waiting_for_user:
            yield "Не удалось сформировать ответ. Передаю обращение оператору."


def build_graph(
    checkpointer=None,
    tool_registry: ToolRegistry | None = None,
    rag_memory=None,
    mcp_tools: list | None = None,
    *,
    agent_settings: AgentSettings | None = None,
    rag_settings: RagSettings | None = None,
    skills: tuple[AgentSkill, ...] = (),
) -> StubGraph:
    llm = build_llm(agent_settings)
    if llm is None:
        return StubGraph()

    registry = tool_registry or ToolRegistry(
        primary_timezone=(
            agent_settings.primary_timezone if agent_settings is not None else "UTC"
        ),
        skills=skills,
    )
    if mcp_tools:
        registry.register_many(mcp_tools)
    effective_rag_memory = (
        rag_memory if rag_settings is None or rag_settings.enabled else None
    )
    rag_extractor_llm = (
        build_rag_extractor_llm(
            llm,
            vertex_location=(
                agent_settings.vertex_location
                if agent_settings is not None
                else os.getenv("GOOGLE_CLOUD_LOCATION", "global")
            ),
        )
        if effective_rag_memory is not None
        else None
    )
    graph = build_langgraph(
        llm,
        registry,
        checkpointer=checkpointer,
        rag_memory=effective_rag_memory,
        rag_extractor_llm=rag_extractor_llm,
        agent_settings=agent_settings,
        rag_settings=rag_settings,
        skills=skills,
    )
    return AgentGraph(graph, registry)

async def rebuild_graph(
    mcp_store: McpServerStore,
    checkpointer=None,
    rag_memory=None,
    *,
    agent_settings: AgentSettings | None = None,
    rag_settings: RagSettings | None = None,
    skills: tuple[AgentSkill, ...] = (),
) -> StubGraph:
    mcp_tools = await McpToolProvider(mcp_store).get_all_tools()
    return build_graph(
        checkpointer=checkpointer,
        rag_memory=rag_memory,
        mcp_tools=mcp_tools,
        agent_settings=agent_settings,
        rag_settings=rag_settings,
        skills=skills,
    )
