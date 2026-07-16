from __future__ import annotations

import asyncio

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from DB import PostgresDatabase

from ._models import SystemSettingModel


class ProceduralStore:
    """Процедурная память: системные настройки агента, URL внешних интеграций (MCP-плагины и т.д.)."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

    async def get_setting(self, key: str) -> dict | None:
        return await asyncio.to_thread(self._get_setting, key)

    def _get_setting(self, key: str) -> dict | None:
        with self._db.session() as session:
            model = session.get(SystemSettingModel, key)
            return model.setting_value if model else None

    async def set_setting(self, key: str, value: dict) -> None:
        await asyncio.to_thread(self._set_setting, key, value)

    def _set_setting(self, key: str, value: dict) -> None:
        statement = insert(SystemSettingModel).values(setting_key=key, setting_value=value)
        statement = statement.on_conflict_do_update(
            index_elements=[SystemSettingModel.setting_key],
            set_={"setting_value": statement.excluded.setting_value, "updated_at": func.now()},
        )
        with self._db.session() as session:
            session.execute(statement)

    async def get_all_settings(self) -> dict[str, dict]:
        return await asyncio.to_thread(self._get_all_settings)

    def _get_all_settings(self) -> dict[str, dict]:
        statement = select(SystemSettingModel.setting_key, SystemSettingModel.setting_value)
        with self._db.session() as session:
            return dict(session.execute(statement).all())
