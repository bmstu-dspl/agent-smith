'''
Эпизодическая память — обёртка над синхронным PostgresDatabase, 
каждый вызов уходит в отдельный поток через asyncio.to_thread, 
чтобы не блокировать event loop FastAPI
'''
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

from DB import PostgresDatabase


class MessagesStore:
    """Эпизодическая память: полная история диалогов по сессиям."""

    def __init__(self, database: PostgresDatabase):
        self._db = database

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict | None = None,
        is_final: bool = True,
    ) -> str:
        message_id = str(uuid.uuid4())
        await asyncio.to_thread(
            self._db.execute,
            """
            INSERT INTO messages (message_id, session_id, role, content, metadata, is_final, created_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s);
            """,
            (
                message_id,
                session_id,
                role,
                content,
                json.dumps(metadata or {}),
                is_final,
                datetime.now(timezone.utc),
            ),
        )
        return message_id

    async def get_recent_messages(self, session_id: str, limit: int = 20) -> list[dict]:
        """Последние N активных и финальных сообщений — контекст для LLM.
        Черновики (is_final = FALSE) и отфильтрованные guardrails (is_active = FALSE)
        сюда никогда не попадают."""
        rows = await asyncio.to_thread(
            self._db.fetch_all,
            """
            SELECT message_id, role, content, created_at
            FROM messages
            WHERE session_id = %s AND is_active = TRUE AND is_final = TRUE
            ORDER BY created_at DESC
            LIMIT %s;
            """,
            (session_id, limit),
        )
        return list(reversed(rows))

    async def get_full_history(self, session_id: str, include_drafts: bool = False) -> list[dict]:
        """Полная история для отладки/аудита — по умолчанию без черновиков,
        но с флагом можно включить и промежуточные reasoning-шаги."""
        query = """
            SELECT message_id, role, content, is_active, is_final, metadata, created_at
            FROM messages
            WHERE session_id = %s
        """
        if not include_drafts:
            query += " AND is_final = TRUE"
        query += " ORDER BY created_at ASC;"

        return await asyncio.to_thread(self._db.fetch_all, query, (session_id,))

    async def deactivate_messages(self, message_ids: list[str]) -> None:
        """Мягкое исключение сообщений из активного окна без физического удаления —
        нужно для guardrails-аудита."""
        if not message_ids:
            return
        await asyncio.to_thread(
            self._db.execute,
            "UPDATE messages SET is_active = FALSE WHERE message_id = ANY(%s);",
            (message_ids,),
        )
