from __future__ import annotations

import asyncio
import json

from DB import PostgresDatabase


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