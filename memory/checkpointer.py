from __future__ import annotations

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from DB import DatabaseConfig

'''
Эпизодическая память графа — состояние LangGraph. Отдельный async-пул, не пересекается с PostgresDatabase
'''
class Checkpointer:
    def __init__(self):
        self._cm = None
        self._saver: AsyncPostgresSaver | None = None

    async def init(self, config: DatabaseConfig) -> AsyncPostgresSaver:
        self._cm = AsyncPostgresSaver.from_conn_string(config.dsn)
        self._saver = await self._cm.__aenter__()
        await self._saver.setup()  # идемпотентно создаёт checkpoints/checkpoint_writes
        return self._saver

    async def close(self) -> None:
        if self._cm:
            await self._cm.__aexit__(None, None, None)

    @property
    def saver(self) -> AsyncPostgresSaver:
        if self._saver is None:
            raise RuntimeError("Checkpointer не инициализирован — вызови init() в lifespan")
        return self._saver