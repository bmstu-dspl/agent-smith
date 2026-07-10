import asyncio
import os
from collections.abc import AsyncIterator

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from ai_core.contracts.schemas import Button, IncomingMessage
from ai_core.graph.nodes import AgentNode, input_guard, route_after_input_guard, tool_output_guard
from ai_core.graph.state import AgentState
from ai_core.tools import ToolRegistry
from ai_core.ui import ButtonDecider


class StubGraph:
    """Fallback-граф без LLM и внешних tools для локального запуска без ключей."""

    async def adecide_buttons(self, payload: IncomingMessage) -> list[Button]:
        if "номер" in payload.user_message.lower():
            return [
                Button(text="Забронировать номер", callback_data="book_room"),
                Button(text="Посмотреть цены", callback_data="show_prices"),
            ]
        return []

    async def astream_response(self, payload: IncomingMessage, on_tool_call=None) -> AsyncIterator[str]:
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


def build_llm():
    provider = os.getenv("LLM_PROVIDER", "google_vertex").strip().lower()
    model = os.getenv("LLM_MODEL", "gemini-2.5-flash")

    if provider in {"google_vertex", "vertex"}:
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

        if not project or not credentials_path:
            return None

        return ChatGoogleGenerativeAI(
            model=model,
            vertexai=True,
            project=project,
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
            temperature=0.2,
        )

    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            return None

        return ChatOpenAI(
            model=model,
            temperature=0.2,
        )

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")


def build_langgraph(llm, tool_registry: ToolRegistry, checkpointer=None):
    tools = tool_registry.get_tools()
    agent_llm = llm.bind_tools(tools) if tools else llm

    workflow = StateGraph(AgentState)

    workflow.add_node("input_guard", input_guard)
    workflow.add_node("agent", AgentNode(agent_llm))
    workflow.add_edge(START, "input_guard")

    workflow.add_conditional_edges(
        "input_guard",
        route_after_input_guard,
        {
            "agent": "agent",
            "end": END,
        },
    )

    if tools:
        workflow.add_node("tools", ToolNode(tools))
        workflow.add_node("tool_output_guard", tool_output_guard)
        workflow.add_conditional_edges(
            "agent",
            tools_condition,
            {
                "tools": "tools",
                "__end__": END,
            },
        )
        workflow.add_edge("tools", "tool_output_guard")
        workflow.add_edge("tool_output_guard", "agent")
    else:
        workflow.add_edge("agent", END)

    if checkpointer is not None:
        return workflow.compile(checkpointer=checkpointer)

    return workflow.compile()


class AgentGraph(StubGraph):
    def __init__(self, graph, llm, tool_registry: ToolRegistry) -> None:
        self.graph = graph
        self.tool_registry = tool_registry
        self.button_decider = ButtonDecider(llm)

    async def adecide_buttons(self, payload: IncomingMessage) -> list[Button]:
        try:
            return await self.button_decider.decide(
                payload=payload,
                available_actions=self.tool_registry.describe_button_actions(),
            )
        except Exception:
            return []

    async def astream_response(self, payload: IncomingMessage, on_tool_call=None) -> AsyncIterator[str]:
        yielded_text = False
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

            if node in {"agent", "input_guard"}:
                text = _chunk_to_text(chunk)
                if text:
                    yielded_text = True
                    yield text

                # AIMessage с tool_calls — запоминаем намерение, ждём результат
                tool_calls = getattr(chunk, "tool_calls", None)
                if tool_calls:
                    for call in tool_calls:
                        pending_calls[call["id"]] = {"name": call["name"], "args": call.get("args", {})}

            elif node == "tools":
                # ToolMessage — результат. Как только пришёл — сразу пишем одну запись
                # с args (из pending_calls) и result вместе.
                call_id = getattr(chunk, "tool_call_id", None)
                if call_id in pending_calls and on_tool_call is not None:
                    info = pending_calls.pop(call_id)
                    await on_tool_call(info["name"], info["args"], _chunk_to_text(chunk))

        if not yielded_text:
            yield "Не удалось сформировать ответ. Передаю обращение оператору."


def build_graph(checkpointer=None, tool_registry: ToolRegistry | None = None) -> StubGraph:
    llm = build_llm()
    if llm is None:
        return StubGraph()

    registry = tool_registry or ToolRegistry()
    graph = build_langgraph(llm, registry, checkpointer=checkpointer)
    return AgentGraph(graph, llm, registry)
