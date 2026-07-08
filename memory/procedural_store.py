from __future__ import annotations

import asyncio
import json

from DB import PostgresDatabase

DEFAULT_CALLBACK_LABELS: dict[str, str] = {
    "book_room": "Забронировать номер",
    "show_prices": "Посмотреть цены",
}


class ProceduralStore:
    """Процедурная память: системные настройки агента, URL внешних интеграций (MCP-плагины и т.д.)."""

    def __init__(self, database: PostgresDatabase):
        self._db = database

    async def get_setting(self, key: str) -> dict | None:
        row = await asyncio.to_thread(
            self._db.fetch_one,
            "SELECT setting_value FROM system_settings WHERE setting_key = %s;",
            (key,),
        )
        return row["setting_value"] if row else None

    async def set_setting(self, key: str, value: dict) -> None:
        await asyncio.to_thread(
            self._db.execute,
            """
            INSERT INTO system_settings (setting_key, setting_value, updated_at)
            VALUES (%s, %s::jsonb, NOW())
            ON CONFLICT (setting_key)
            DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = NOW();
            """,
            (key, json.dumps(value)),
        )

    async def get_all_settings(self) -> dict[str, dict]:
        rows = await asyncio.to_thread(
            self._db.fetch_all,
            "SELECT setting_key, setting_value FROM system_settings;",
        )
        return {row["setting_key"]: row["setting_value"] for row in rows}

    async def get_callback_labels(self) -> dict[str, str]:
        """Словарь callback_data -> человекочитаемый текст выбора.
        Если в БД ещё не заведён — используется дефолт из кода как fallback."""
        stored = await self.get_setting("callback_labels")
        return stored if stored else DEFAULT_CALLBACK_LABELS

    async def seed_default_callback_labels(self) -> None:
        """Разово кладёт дефолтные метки в БД, если их там ещё нет.
        Вызывается один раз при старте приложения (см. MemoryManager.init)."""
        existing = await self.get_setting("callback_labels")
        if existing is None:
            await self.set_setting("callback_labels", DEFAULT_CALLBACK_LABELS)