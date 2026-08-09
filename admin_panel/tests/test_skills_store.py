from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pytest

from DB import OrmBase
from admin_panel.auth_store import AdminAuthStore
from admin_panel.db_models import AdminUserModel
from admin_panel.skills import (
    AgentSkillCreate,
    AgentSkillModel,
    AgentSkillUpdate,
    SkillCatalogModel,
    SkillCatalogConflictError,
    SkillCatalogLimitError,
    SkillStore,
)


def _stores() -> tuple[AdminAuthStore, SkillStore]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    OrmBase.metadata.create_all(
        engine,
        tables=[
            AdminUserModel.__table__,
            SkillCatalogModel.__table__,
            AgentSkillModel.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    return AdminAuthStore(session_factory), SkillStore(session_factory)


def test_created_skill_is_returned_from_the_catalog() -> None:
    auth_store, skill_store = _stores()
    admin_id = auth_store.create_admin(
        "owner",
        "correct horse battery staple",
        role="admin",
    )

    created = skill_store.create_skill(
        AgentSkillCreate(
            name="room-availability",
            description="Use when a guest asks to find available rooms.",
            instructions="Collect dates and guest counts before searching.",
        ),
        expected_revision=0,
        updated_by=admin_id,
    )

    assert created.revision == 1
    assert len(created.skills) == 1
    assert created.skills[0].name == "room-availability"
    assert created.skills[0].enabled is True
    assert created.skills[0].version == 1
    assert skill_store.get_catalog() == created


def test_editing_a_skill_increments_skill_and_catalog_versions() -> None:
    auth_store, skill_store = _stores()
    admin_id = auth_store.create_admin(
        "owner",
        "correct horse battery staple",
        role="admin",
    )
    created = skill_store.create_skill(
        AgentSkillCreate(
            name="room-availability",
            description="Use when a guest asks to find available rooms.",
            instructions="Collect dates before searching.",
        ),
        expected_revision=0,
        updated_by=admin_id,
    )

    updated = skill_store.update_skill(
        created.skills[0].skill_id,
        AgentSkillUpdate(
            name="room-availability",
            description="Use for every request about available hotel rooms.",
            instructions="Collect dates and guest counts before searching.",
        ),
        expected_revision=1,
        updated_by=admin_id,
    )

    assert updated.revision == 2
    assert updated.skills[0].version == 2
    assert updated.skills[0].description == (
        "Use for every request about available hotel rooms."
    )


def test_skill_can_be_disabled_and_deleted_permanently() -> None:
    auth_store, skill_store = _stores()
    admin_id = auth_store.create_admin(
        "owner",
        "correct horse battery staple",
        role="admin",
    )
    created = skill_store.create_skill(
        AgentSkillCreate(
            name="room-availability",
            description="Use when a guest asks to find available rooms.",
            instructions="Collect dates before searching.",
        ),
        expected_revision=0,
        updated_by=admin_id,
    )
    skill_id = created.skills[0].skill_id

    disabled = skill_store.set_enabled(
        skill_id,
        False,
        expected_revision=1,
        updated_by=admin_id,
    )
    assert disabled.revision == 2
    assert disabled.skills[0].enabled is False
    assert disabled.skills[0].version == 2

    deleted = skill_store.delete_skill(
        skill_id,
        expected_revision=2,
        updated_by=admin_id,
    )
    assert deleted.revision == 3
    assert deleted.skills == ()


def test_stale_catalog_revision_does_not_overwrite_a_newer_change() -> None:
    auth_store, skill_store = _stores()
    admin_id = auth_store.create_admin(
        "owner",
        "correct horse battery staple",
        role="admin",
    )
    skill_store.create_skill(
        AgentSkillCreate(
            name="room-availability",
            description="Use when a guest asks to find available rooms.",
            instructions="Collect dates before searching.",
        ),
        expected_revision=0,
        updated_by=admin_id,
    )

    with pytest.raises(SkillCatalogConflictError, match="expected 0, actual 1"):
        skill_store.create_skill(
            AgentSkillCreate(
                name="booking",
                description="Use when a guest wants to book a selected room.",
                instructions="Confirm the selected offer before booking.",
            ),
            expected_revision=0,
            updated_by=admin_id,
        )

    assert skill_store.get_catalog().revision == 1
    assert [skill.name for skill in skill_store.get_catalog().skills] == [
        "room-availability"
    ]


def test_enabled_skill_metadata_cannot_exceed_the_discovery_budget() -> None:
    auth_store, skill_store = _stores()
    admin_id = auth_store.create_admin(
        "owner",
        "correct horse battery staple",
        role="admin",
    )
    description = "x" * 1000
    revision = 0
    for index in range(31):
        catalog = skill_store.create_skill(
            AgentSkillCreate(
                name=f"skill-{index}",
                description=description,
                instructions="Follow this workflow.",
            ),
            expected_revision=revision,
            updated_by=admin_id,
        )
        revision = catalog.revision

    with pytest.raises(SkillCatalogLimitError, match="32000"):
        skill_store.create_skill(
            AgentSkillCreate(
                name="skill-overflow",
                description=description,
                instructions="Follow this workflow.",
            ),
            expected_revision=revision,
            updated_by=admin_id,
        )

    assert skill_store.get_catalog().revision == 31
