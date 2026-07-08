import asyncio
from collections.abc import AsyncIterator
<<<<<<< HEAD

=======
from langchain_core.messages import AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from ai_core.graph.nodes import AgentNode, input_guard, route_after_input_guard
from ai_core.graph.state import AgentState
>>>>>>> origin/ai-agent
from ai_core.contracts.schemas import Button, IncomingMessage
from ai_core.graph.prompts import AGENT_SYSTEM_PROMPT


class StubGraph:
    """Временная заглушка вместо LangGraph.CompiledGraph.
    Разделена на два метода вместо одного ainvoke() — под будущий реальный граф:
    - adecide_buttons: аналог отдельного узла графа, который решает нужны ли кнопки
      (в реальном LangGraph это будет узел с LLM-вызовом + structured output на Button).
    - astream_response: аналог graph.astream(..., stream_mode="messages") —
      токены/чанки ответа от LLM по мере генерации.
    """

    async def adecide_buttons(self, payload: IncomingMessage) -> list[Button]:
        # Заглушка-логика: если в сообщении упоминается "номер" — предлагаем кнопки,
        # иначе решаем, что кнопки не нужны. Позже здесь будет LLM с structured output.
        if "номер" in payload.user_message.lower():
            return [
                Button(text="Забронировать номер", callback_data="book_room"),
                Button(text="Посмотреть цены", callback_data="show_prices"),
            ]
        return []

    async def astream_response(self, payload: IncomingMessage) -> AsyncIterator[str]:
        # Заглушка потоковой генерации: режем фиктивный ответ на куски и отдаём
        # с небольшой задержкой, имитируя стриминг токенов от LLM.
        fake_answer = (
            f"Вы написали: «{payload.user_message}». "
            f"Это потоковый ответ-заглушка, скоро здесь будет настоящий LLM."
        )
        words = fake_answer.split(" ")
        for word in words:
            await asyncio.sleep(0.05)  # имитация задержки генерации токена
            yield word + " "


<<<<<<< HEAD
def build_graph(checkpointer=None) -> StubGraph:
    # позже: StateGraph(...).compile(checkpointer=checkpointer)
    return StubGraph()
=======
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

def build_langgraph(llm, checkpointer=None):
    workflow = StateGraph(AgentState)

    workflow.add_node("input_guard", input_guard)
    workflow.add_node("agent", AgentNode(llm))
    workflow.add_edge(START, "input_guard")

    workflow.add_conditional_edges(
        "input_guard",
        route_after_input_guard,
        {
            "agent": "agent",
            "end": END,
        },
    )

    workflow.add_edge("agent", END)

    if checkpointer is not None:
        return workflow.compile(checkpointer=checkpointer)

    return workflow.compile()


class AgentGraph(StubGraph):
    def __init__(self, graph) -> None:
        self.graph = graph

    async def astream_response(self, payload: IncomingMessage) -> AsyncIterator[str]:
        result = await self.graph.ainvoke(
            {
                "session_id": payload.session_id,
                "user_message": payload.user_message,
                "metadata": payload.metadata,
                "messages": [],
            },
            config={"configurable": {"thread_id":payload.session_id}},
        )

        for message in reversed(result.get("messages", [])):
            if isinstance(message, AIMessage):
                text = _chunk_to_text(message)
                if text:
                    yield text
                    return

        yield "Не удалось сформировать ответ. Передаю обращение оператору."

def build_graph(checkpointer=None) -> StubGraph:
    llm = build_llm()
    if llm is None:
        return StubGraph()

    graph = build_langgraph(llm, checkpointer=checkpointer)
    return AgentGraph(graph)
>>>>>>> origin/ai-agent
