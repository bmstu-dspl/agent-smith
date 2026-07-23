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
    Работает через отдельное, независимое от основного SQLAlchemy-пула соединение"""

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
        self._connection = await psycopg.AsyncConnection.connect(
            self._dsn,
            autocommit=True,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=3,
        )
        async with self._connection:
            await self._connection.execute(f"LISTEN {NOTIFY_CHANNEL};")
            logger.info("listening for mcp_servers changes on channel %s", NOTIFY_CHANNEL)
            async for notify in self._connection.notifies():
                logger.info("received mcp_servers_changed notify: %s", notify)
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
            logger.info("rebuilding graph after mcp_servers change")
            await self._on_change()
            logger.info("graph rebuilt successfully after mcp_servers change")
        except Exception:
            logger.exception("mcp server change callback (graph rebuild) failed")
