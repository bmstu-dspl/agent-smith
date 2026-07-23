from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

import psycopg

logger = logging.getLogger(__name__)

NOTIFY_CHANNEL = "mcp_servers_changed"
DEBOUNCE_SECONDS = 1.0
RECONNECT_DELAY_SECONDS = 5.0


class McpServerChangeListener:
    """Слушает уведомления Postgres (LISTEN/NOTIFY) об изменениях в таблице mcp_servers
    и вызывает переданный callback (пересборка графа).

    Работает через отдельное, независимое от основного SQLAlchemy-пула соединение —
    по той же логике, что и Checkpointer: LISTEN/NOTIFY требует постоянно открытое
    соединение, которое слушает канал, это другая модель работы, чем обычные
    короткие запросы через session().

    Уведомления дебаунсятся: если несколько изменений приходят быстро подряд
    (например, админка добавляет сразу несколько серверов), граф пересобирается
    один раз после того, как поток изменений утихнет, а не при каждом уведомлении."""

    def __init__(
        self,
        dsn: str,
        on_change: Callable[[], Awaitable[None]],
        debounce_seconds: float = DEBOUNCE_SECONDS,
    ) -> None:
        self._dsn = dsn
        self._on_change = on_change
        self._debounce_seconds = debounce_seconds
        self._task: asyncio.Task | None = None
        self._debounce_task: asyncio.Task | None = None
        self._connection: psycopg.AsyncConnection | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="mcp-server-change-listener")

    async def stop(self) -> None:
        if self._debounce_task is not None:
            self._debounce_task.cancel()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._connection is not None:
            await self._connection.close()

    async def _run(self) -> None:
        """Внешний цикл — переподключается, если соединение LISTEN оборвалось
        (например, база на секунду недоступна). Не должен падать насовсем."""
        while True:
            try:
                await self._listen_forever()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "mcp server change listener lost connection, retrying in %ss",
                    RECONNECT_DELAY_SECONDS,
                )
                await asyncio.sleep(RECONNECT_DELAY_SECONDS)

    async def _listen_forever(self) -> None:
        self._connection = await psycopg.AsyncConnection.connect(self._dsn, autocommit=True)
        async with self._connection:
            await self._connection.execute(f"LISTEN {NOTIFY_CHANNEL};")
            logger.info("listening for mcp_servers changes on channel %s", NOTIFY_CHANNEL)
            async for _ in self._connection.notifies():
                self._schedule_rebuild()

    def _schedule_rebuild(self) -> None:
        if self._debounce_task is not None and not self._debounce_task.done():
            self._debounce_task.cancel()
        self._debounce_task = asyncio.create_task(self._debounced_rebuild())

    async def _debounced_rebuild(self) -> None:
        try:
            await asyncio.sleep(self._debounce_seconds)
        except asyncio.CancelledError:
            return
        try:
            await self._on_change()
        except Exception:
            logger.exception("mcp server change callback (graph rebuild) failed")
