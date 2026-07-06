<<<<<<< HEAD
import asyncio
from collections.abc import AsyncIterator

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


def build_graph(checkpointer=None) -> StubGraph:
    # позже: StateGraph(...).compile(checkpointer=checkpointer)
=======
import asyncio
from collections.abc import AsyncIterator

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


def build_graph(checkpointer=None) -> StubGraph:
    # позже: StateGraph(...).compile(checkpointer=checkpointer)
>>>>>>> 7bf389080b460c37f68fd262b476e2a5d6a03dec
    return StubGraph()