from __future__ import annotations

from DB import DatabaseConfig, Migrator, PostgresDatabase
from pathlib import Path

from .checkpointer import Checkpointer
from .messages_store import MessagesStore
from .procedural_store import ProceduralStore


class MemoryManager:
    """Единая точка доступа ко всем видам памяти агента."""

    def __init__(self):
        self.db: PostgresDatabase | None = None
        self.messages: MessagesStore | None = None
        self.settings: ProceduralStore | None = None
        self._checkpointer = Checkpointer()

    @property
    def checkpointer(self):
        return self._checkpointer.saver

    async def init(self) -> None:
        config = DatabaseConfig.from_env()

        # 1. Синхронный пул для messages/system_settings (через to_thread внутри стораджей)
        self.db = PostgresDatabase(config)
        self.db.open()
        migrations_path = Path(__file__).resolve().parent / "migrations"
        self.db.apply_migrations(Migrator(migrations_path=migrations_path).load())

        self.messages = MessagesStore(self.db)
        self.settings = ProceduralStore(self.db)

        # 2. Отдельный async-пул для состояния графа
        await self._checkpointer.init(config)

    async def close(self) -> None:
        await self._checkpointer.close()
        if self.db:
            self.db.close() 
