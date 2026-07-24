from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from admin_panel.settings import AgentSettings, RagSettings, SettingsStore


GraphFactory = Callable[[AgentSettings, RagSettings], Awaitable[Any]]


class LiveGraphProvider:
    """Publishes an immutable graph snapshot for the latest committed settings.

    Revision checks happen at the request boundary. Graph construction is serialized,
    and the previous graph remains available until a complete replacement is ready.
    """

    def __init__(self, settings_store: SettingsStore, graph_factory: GraphFactory) -> None:
        self._settings_store = settings_store
        self._graph_factory = graph_factory
        self._graph: Any = None
        self._revisions: tuple[int, int] | None = None
        self._reload_lock = asyncio.Lock()

    async def get_graph(self) -> Any:
        agent_record, rag_record = await asyncio.gather(
            asyncio.to_thread(self._settings_store.get_agent),
            asyncio.to_thread(self._settings_store.get_rag),
        )
        revisions = (agent_record.revision, rag_record.revision)
        if self._graph is not None and revisions == self._revisions:
            return self._graph

        async with self._reload_lock:
            agent_record, rag_record = await asyncio.gather(
                asyncio.to_thread(self._settings_store.get_agent),
                asyncio.to_thread(self._settings_store.get_rag),
            )
            revisions = (agent_record.revision, rag_record.revision)
            if self._graph is not None and revisions == self._revisions:
                return self._graph

            replacement = await self._graph_factory(
                agent_record.settings,
                rag_record.settings,
            )
            self._graph = replacement
            self._revisions = revisions
            return replacement
