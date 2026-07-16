from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update

from DB import PostgresDatabase

from ._models import MessageModel


class MessagesStore:
    """Эпизодическая память: полная история диалогов по сессиям."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict | None = None,
        is_final: bool = True,
    ) -> str:
        return await asyncio.to_thread(self._append_message, session_id, role, content, metadata, is_final)

    def _append_message(
        self, session_id: str, role: str, content: str, metadata: dict | None, is_final: bool
    ) -> str:
        message_id = str(uuid.uuid4())
        with self._db.session() as session:
            session.add(
                MessageModel(
                    message_id=message_id,
                    session_id=session_id,
                    role=role,
                    content=content,
                    metadata_=metadata or {},
                    is_final=is_final,
                    created_at=datetime.now(timezone.utc),
                )
            )
        return message_id

    async def get_recent_messages(self, session_id: str, limit: int = 20) -> list[dict]:
        """Последние N активных и финальных сообщений — контекст для LLM.
        Черновики (is_final = FALSE) и отфильтрованные guardrails (is_active = FALSE)
        сюда никогда не попадают."""
        return await asyncio.to_thread(self._get_recent_messages, session_id, limit)

    def _get_recent_messages(self, session_id: str, limit: int) -> list[dict]:
        statement = (
            select(MessageModel.message_id, MessageModel.role, MessageModel.content, MessageModel.created_at)
            .where(
                MessageModel.session_id == session_id,
                MessageModel.is_active.is_(True),
                MessageModel.is_final.is_(True),
            )
            .order_by(MessageModel.created_at.desc())
            .limit(limit)
        )
        with self._db.session() as session:
            rows = [dict(row) for row in session.execute(statement).mappings()]
        return list(reversed(rows))

    async def get_full_history(self, session_id: str, include_drafts: bool = False) -> list[dict]:
        """Полная история для отладки/аудита — по умолчанию без черновиков,
        но с флагом можно включить и промежуточные reasoning-шаги."""
        return await asyncio.to_thread(self._get_full_history, session_id, include_drafts)

    def _get_full_history(self, session_id: str, include_drafts: bool) -> list[dict]:
        statement = (
            select(
                MessageModel.message_id,
                MessageModel.role,
                MessageModel.content,
                MessageModel.is_active,
                MessageModel.is_final,
                MessageModel.metadata_.label("metadata"),
                MessageModel.created_at,
            )
            .where(MessageModel.session_id == session_id)
            .order_by(MessageModel.created_at.asc())
        )
        if not include_drafts:
            statement = statement.where(MessageModel.is_final.is_(True))
        with self._db.session() as session:
            return [dict(row) for row in session.execute(statement).mappings()]

    async def deactivate_messages(self, message_ids: list[str]) -> None:
        """Мягкое исключение сообщений из активного окна без физического удаления —
        нужно для guardrails-аудита."""
        if not message_ids:
            return
        await asyncio.to_thread(self._deactivate_messages, message_ids)

    def _deactivate_messages(self, message_ids: list[str]) -> None:
        statement = update(MessageModel).where(MessageModel.message_id.in_(message_ids)).values(is_active=False)
        with self._db.session() as session:
            session.execute(statement)

    async def find_buttons_context(self, session_id: str, callback_data: str, lookback: int = 20) -> str | None:
        """Ищет текст кнопки по callback_data среди последних N сообщений ассистента с кнопками.
        Не ограничивается только самым последним сообщением — пользователь может нажать
        на кнопку из более раннего сообщения, если Telegram её ещё не убрал."""
        return await asyncio.to_thread(self._find_buttons_context, session_id, callback_data, lookback)

    def _find_buttons_context(self, session_id: str, callback_data: str, lookback: int) -> str | None:
        statement = (
            select(MessageModel.metadata_)
            .where(
                MessageModel.session_id == session_id,
                MessageModel.role == "assistant",
                MessageModel.metadata_.op("?")("buttons"),
            )
            .order_by(MessageModel.created_at.desc())
            .limit(lookback)
        )
        with self._db.session() as session:
            for (metadata,) in session.execute(statement):
                buttons = metadata.get("buttons", {})
                if callback_data in buttons:
                    return buttons[callback_data]
        return None

    async def append_tool_call(
        self,
        session_id: str,
        tool_name: str,
        tool_args: dict,
        tool_result: str,
    ) -> str:
        """Один вызов инструмента = одна запись, аргументы и результат сразу вместе."""
        return await self.append_message(
            session_id,
            role="tool",
            content=tool_result,
            metadata={"tool_name": tool_name, "tool_args": tool_args},
            is_final=False,
        )
    