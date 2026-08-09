from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from admin_panel.settings import AgentSettings, RagSettings, SettingsStore
from admin_panel.skills import AgentSkill, SkillStore


GraphFactory = Callable[[AgentSettings, RagSettings], Awaitable[Any]]
SkillGraphFactory = Callable[
    [AgentSettings, RagSettings, tuple[AgentSkill, ...]],
    Awaitable[Any],
]


class LiveGraphProvider:
    """Publishes an immutable graph snapshot for the latest committed settings.

    Revision checks happen at the request boundary. Graph construction is serialized,
    and the previous graph remains available until a complete replacement is ready.
    """

    def __init__(
        self,
        settings_store: SettingsStore,
        graph_factory: GraphFactory | SkillGraphFactory,
        *,
        skill_store: SkillStore | None = None,
    ) -> None:
        self._settings_store = settings_store
        self._graph_factory = graph_factory
        self._skill_store = skill_store
        self._graph: Any = None
        self._revisions: tuple[int, ...] | None = None
        self._reload_lock = asyncio.Lock()

    def invalidate(self) -> None:
        """Force the next request to rebuild for non-settings dependencies."""
        self._revisions = None

    async def get_graph(self) -> Any:
        records = await asyncio.gather(
            asyncio.to_thread(self._settings_store.get_agent),
            asyncio.to_thread(self._settings_store.get_rag),
            *(
                [asyncio.to_thread(self._skill_store.get_revision)]
                if self._skill_store is not None
                else []
            ),
        )
        agent_record, rag_record = records[:2]
        revisions = (
            agent_record.revision,
            rag_record.revision,
            *records[2:],
        )
        if self._graph is not None and revisions == self._revisions:
            return self._graph

        async with self._reload_lock:
            records = await asyncio.gather(
                asyncio.to_thread(self._settings_store.get_agent),
                asyncio.to_thread(self._settings_store.get_rag),
                *(
                    [asyncio.to_thread(self._skill_store.get_catalog)]
                    if self._skill_store is not None
                    else []
                ),
            )
            agent_record, rag_record = records[:2]
            skill_record = records[2] if len(records) == 3 else None
            revisions = (
                agent_record.revision,
                rag_record.revision,
                *([skill_record.revision] if skill_record is not None else []),
            )
            if self._graph is not None and revisions == self._revisions:
                return self._graph

            if skill_record is None:
                replacement = await self._graph_factory(
                    agent_record.settings,
                    rag_record.settings,
                )
            else:
                active_skills = tuple(
                    skill for skill in skill_record.skills if skill.enabled
                )
                replacement = await self._graph_factory(
                    agent_record.settings,
                    rag_record.settings,
                    active_skills,
                )
            self._graph = replacement
            self._revisions = revisions
            return replacement
