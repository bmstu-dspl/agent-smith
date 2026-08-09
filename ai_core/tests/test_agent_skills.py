from __future__ import annotations

from datetime import datetime, timezone

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from DB import OrmBase
from admin_panel.auth_store import AdminAuthStore
from admin_panel.db_models import (
    AdminUserModel,
    AgentSkillModel,
    ServiceSettingsModel,
    SkillCatalogModel,
)
from admin_panel.settings import SettingsStore
from admin_panel.skills import AgentSkill, AgentSkillCreate, SkillStore
from ai_core.graph.nodes import AgentNode
from ai_core.graph.builder import build_langgraph
from ai_core.runtime_config import LiveGraphProvider
from ai_core.skills import create_load_skill_tool
from ai_core.tools.registry import ToolRegistry


def _skill(*, enabled: bool = True, version: int = 1) -> AgentSkill:
    now = datetime.now(timezone.utc)
    return AgentSkill(
        skill_id="skill-1",
        name="room-availability",
        description="Use when a guest asks to find available hotel rooms.",
        instructions="Never request personal data. Collect dates before searching.",
        enabled=enabled,
        version=version,
        created_by=None,
        updated_by=None,
        created_at=now,
        updated_at=now,
    )


class RecordingLlm:
    def __init__(self) -> None:
        self.messages = []

    async def ainvoke(self, messages):
        self.messages = messages
        return AIMessage(content="ok")


@pytest.mark.asyncio
async def test_discovery_prompt_contains_metadata_but_not_skill_instructions() -> None:
    llm = RecordingLlm()
    node = AgentNode(llm, skills=(_skill(),))

    await node({"messages": [HumanMessage(content="Find me a room")]})

    system_messages = [
        message.content
        for message in llm.messages
        if isinstance(message, SystemMessage)
    ]
    assert len(system_messages) == 3
    discovery = system_messages[2]
    assert "room-availability" in discovery
    assert "Use when a guest asks to find available hotel rooms." in discovery
    assert "version: 1" in discovery
    assert "load_skill" in discovery
    assert "Never request personal data" not in discovery


@pytest.mark.asyncio
async def test_load_skill_returns_full_instructions_only_for_active_catalog_entries() -> None:
    tool = create_load_skill_tool((_skill(version=3),))

    loaded = await tool.ainvoke({"name": "room-availability"})
    missing = await tool.ainvoke({"name": "booking"})

    assert loaded == {
        "status": "loaded",
        "skill_id": "skill-1",
        "name": "room-availability",
        "version": 3,
        "instructions": "Never request personal data. Collect dates before searching.",
    }
    assert missing == {"status": "not_found", "name": "booking"}


@pytest.mark.asyncio
async def test_agent_does_not_receive_stale_loaded_skill_messages() -> None:
    llm = RecordingLlm()
    node = AgentNode(llm, skills=(_skill(version=2),))
    stale_call = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "load-old",
                "name": "load_skill",
                "args": {"name": "room-availability"},
            }
        ],
    )
    stale_result = ToolMessage(
        content='{"status":"loaded","name":"room-availability","version":1,"instructions":"old"}',
        name="load_skill",
        tool_call_id="load-old",
    )

    await node(
        {
            "messages": [
                HumanMessage(content="Find me a room"),
                stale_call,
                stale_result,
                HumanMessage(content="For two adults"),
            ]
        }
    )

    assert not any(
        isinstance(message, ToolMessage) and message.name == "load_skill"
        for message in llm.messages
    )
    assert not any(
        isinstance(message, AIMessage) and message.tool_calls
        for message in llm.messages
    )


def test_tool_registry_exposes_loader_only_when_active_skills_exist() -> None:
    active_tools = ToolRegistry(skills=(_skill(),)).describe_tools()
    disabled_tools = ToolRegistry(skills=(_skill(enabled=False),)).describe_tools()

    assert "load_skill" in [item["name"] for item in active_tools]
    assert "load_skill" not in [item["name"] for item in disabled_tools]


@pytest.mark.asyncio
async def test_skill_catalog_revision_rebuilds_the_graph_before_the_next_request() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    OrmBase.metadata.create_all(
        engine,
        tables=[
            AdminUserModel.__table__,
            ServiceSettingsModel.__table__,
            SkillCatalogModel.__table__,
            AgentSkillModel.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    auth_store = AdminAuthStore(session_factory)
    admin_id = auth_store.create_admin(
        "owner", "correct horse battery staple", role="admin"
    )
    settings_store = SettingsStore(session_factory, Fernet.generate_key().decode())
    skill_store = SkillStore(session_factory)
    built_with: list[tuple[str, ...]] = []

    async def build_graph(agent, rag, skills):
        names = tuple(skill.name for skill in skills)
        built_with.append(names)
        return names

    provider = LiveGraphProvider(
        settings_store,
        build_graph,
        skill_store=skill_store,
    )
    assert await provider.get_graph() == ()

    created = skill_store.create_skill(
        AgentSkillCreate(
            name="room-availability",
            description="Use when a guest asks to find available rooms.",
            instructions="Collect dates before searching.",
        ),
        expected_revision=0,
        updated_by=admin_id,
    )
    assert await provider.get_graph() == ("room-availability",)
    assert await provider.get_graph() == ("room-availability",)

    skill_store.set_enabled(
        created.skills[0].skill_id,
        False,
        expected_revision=1,
        updated_by=admin_id,
    )
    assert await provider.get_graph() == ()
    assert built_with == [(), ("room-availability",), ()]


class SkillLoadingLlm:
    def __init__(self) -> None:
        self.invocations = []

    def bind_tools(self, tools):
        self.tool_names = [tool.name for tool in tools]
        return self

    async def ainvoke(self, messages):
        self.invocations.append(messages)
        if not any(
            isinstance(message, ToolMessage) and message.name == "load_skill"
            for message in messages
        ):
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "load-1",
                        "name": "load_skill",
                        "args": {"name": "room-availability"},
                    }
                ],
            )
        return AIMessage(content="Which dates should I search?")


@pytest.mark.asyncio
async def test_langgraph_loads_skill_body_before_continuing_the_agent_loop() -> None:
    skill = _skill()
    llm = SkillLoadingLlm()
    registry = ToolRegistry(skills=(skill,))
    graph = build_langgraph(llm, registry, skills=(skill,))

    result = await graph.ainvoke(
        {
            "session_id": "skill-flow",
            "user_message": "Find me a room",
            "message_type": "text",
            "metadata": {},
            "messages": [],
        }
    )

    assert "load_skill" in llm.tool_names
    loaded_messages = [
        message
        for message in result["messages"]
        if isinstance(message, ToolMessage) and message.name == "load_skill"
    ]
    assert len(loaded_messages) == 1
    assert "Never request personal data" in loaded_messages[0].content
    assert result["messages"][-1].content == "Which dates should I search?"


@pytest.mark.asyncio
async def test_loaded_skill_is_reused_for_a_later_clarification_in_the_same_thread() -> None:
    skill = _skill()
    llm = SkillLoadingLlm()
    graph = build_langgraph(
        llm,
        ToolRegistry(skills=(skill,)),
        checkpointer=InMemorySaver(),
        skills=(skill,),
    )
    config = {"configurable": {"thread_id": "skill-thread"}}
    base = {
        "session_id": "skill-thread",
        "message_type": "text",
        "metadata": {},
        "messages": [],
    }

    await graph.ainvoke(
        {**base, "user_message": "Find me a room"},
        config=config,
    )
    result = await graph.ainvoke(
        {**base, "user_message": "For two adults"},
        config=config,
    )

    loaded_messages = [
        message
        for message in result["messages"]
        if isinstance(message, ToolMessage) and message.name == "load_skill"
    ]
    assert len(loaded_messages) == 1
