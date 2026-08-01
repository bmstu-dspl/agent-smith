from __future__ import annotations

from cryptography.fernet import Fernet
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from DB import OrmBase
from admin_panel.db_models import AdminUserModel, ServiceSettingsModel
from admin_panel.settings import (
    AgentSettingsUpdate,
    RagSettingsUpdate,
    SettingsStore,
)
from ai_core.runtime_config import LiveGraphProvider


@pytest.mark.asyncio
async def test_committed_agent_settings_rebuild_graph_before_next_request() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    OrmBase.metadata.create_all(
        engine,
        tables=[AdminUserModel.__table__, ServiceSettingsModel.__table__],
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    store = SettingsStore(session_factory, Fernet.generate_key().decode())
    built_with: list[tuple[str, str, str, str, str]] = []

    async def build_graph(agent, rag):
        fingerprint = (
            agent.model,
            agent.system_prompt,
            agent.vertex_location,
            agent.primary_timezone,
            rag.additional_instructions,
        )
        built_with.append(fingerprint)
        return fingerprint

    provider = LiveGraphProvider(store, build_graph)
    first = await provider.get_graph()
    assert first[0] == "gemini-2.5-flash"

    store.save_agent(
        AgentSettingsUpdate(
            revision=0,
            provider="openai",
            model="gpt-5-mini",
            temperature=0.3,
            system_prompt="New live prompt",
            vertex_location="eu",
            primary_timezone="America/New_York",
        ),
        updated_by="test-admin",
    )
    store.save_rag(
        RagSettingsUpdate(
            revision=0,
            enabled=True,
            additional_instructions="Use only published hotel policies.",
            max_chunk_chars=1200,
            chunk_overlap_chars=150,
            retrieval_mode="hybrid",
            limit=8,
            max_context_chars=12000,
        ),
        updated_by="test-admin",
    )

    second = await provider.get_graph()
    assert second == (
        "gpt-5-mini",
        "New live prompt",
        "eu",
        "America/New_York",
        "Use only published hotel policies.",
    )
    assert second is await provider.get_graph()
    assert len(built_with) == 2

    provider.invalidate()
    assert await provider.get_graph() == second
    assert len(built_with) == 3
