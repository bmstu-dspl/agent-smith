from datetime import datetime, timezone
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field


class IncomingMessage(BaseModel):
    """Контракт bot -> core. Поля синхронизированы с app/models.py в tg-bot-v1."""
    session_id: str = Field(..., description="Уникальный ID сессии пользователя")
    user_message: str = Field(..., description="Текст сообщения от пользователя")
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Button(BaseModel):
    """Одна кнопка инлайн-клавиатуры Telegram."""
    text: str = Field(..., description="Текст на кнопке")
    callback_data: str = Field(..., max_length=64, description="Данные, которые вернутся боту при нажатии (лимит Telegram — 64 байта)")


class ButtonsMessage(BaseModel):
    """Первая часть потока: core -> bot. Валидируется через Pydantic, т.к. это структурированные данные."""
    type: Literal["buttons"] = "buttons"
    session_id: str
    buttons: list[Button] = Field(default_factory=list, description="Пустой список = LLM решила, что кнопки не нужны")


# Ниже — НЕ Pydantic-модели, а TypedDict,
# но типы описаны для читаемости кода и подсказок в IDE.
class TextChunkPayload(TypedDict):
    type: Literal["text_chunk"]
    session_id: str
    content: str


class StreamEndPayload(TypedDict):
    type: Literal["end"]
    session_id: str


def make_text_chunk(session_id: str, content: str) -> TextChunkPayload:
    return {"type": "text_chunk", "session_id": session_id, "content": content}


def make_stream_end(session_id: str) -> StreamEndPayload:
    return {"type": "end", "session_id": session_id}