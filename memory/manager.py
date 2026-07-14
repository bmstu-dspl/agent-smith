from __future__ import annotations

from DB import DatabaseConfig, PostgresDatabase

from .checkpointer import Checkpointer
from .messages_store import MessagesStore
from .procedural_store import ProceduralStore


class MemoryManager:
    """Единая точка доступа ко всем видам памяти агента."""

    def __init__(self) -> None:
        self.db: PostgresDatabase | None = None
        self.messages: MessagesStore | None = None
        self.settings: ProceduralStore | None = None
        self._checkpointer = Checkpointer()

    @property
    def checkpointer(self):
        return self._checkpointer.saver

    async def init(self) -> None:
        config = DatabaseConfig.from_env()
        self.db = PostgresDatabase(config)
        self.db.open()
        self.db.migrate()

        self.messages = MessagesStore(self.db)
        self.settings = ProceduralStore(self.db)

        await self._checkpointer.init(config)

    async def close(self) -> None:
        await self._checkpointer.close()
        if self.db:
            self.db.close()
