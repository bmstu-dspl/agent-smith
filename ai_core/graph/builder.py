import asyncio
import os
from collections.abc import AsyncIterator

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from ai_core.contracts.schemas import Button, IncomingMessage


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
    model = os.getenv("LLM_MODEL", "gemini-2.0-flash")

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


class LLMGraph(StubGraph):
    def __init__(self, llm) -> None:
        self.llm = llm

    async def astream_response(self, payload: IncomingMessage) -> AsyncIterator[str]:
        prompt = ("""Ты — помощник гостиницы в Telegram. Отвечай на русском языке, кратко, дружелюбно и по делу.

Помогай гостям узнавать информацию об отеле, номерах, услугах, заселении, выезде, питании, парковке и правилах проживания. Для вопросов о бронировании уточняй даты проживания, количество гостей и предпочтения по номеру.

Не выдумывай наличие номеров, цены, условия бронирования или правила отеля. Если точных данных нет — честно сообщи об этом и предложи передать вопрос сотруднику.

Перед созданием, изменением или отменой бронирования обязательно получи явное подтверждение гостя. После действия кратко сообщи результат и важные детали.

Если вопрос сложный, возникла ошибка или пользователь просит человека — передай обращение оператору вместе с контекстом диалога. Не используй технические термины и не рассказывай о внутренних системах.
"""
            f"Сообщение пользователя: {payload.user_message}"
        )
        async for chunk in self.llm.astream(prompt):
            text = _chunk_to_text(chunk)
            if text:
                yield text


def build_graph(checkpointer=None) -> StubGraph:
    # позже: StateGraph(...).compile(checkpointer=checkpointer)
    llm = build_llm()
    if llm is not None:
        return LLMGraph(llm=llm)
    return StubGraph()