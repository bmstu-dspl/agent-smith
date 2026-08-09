from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from .db_models import AgentSkillModel, SkillCatalogModel


CATALOG_ID = "global"
SKILL_NAME_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
DISCOVERY_CATALOG_MAX_CHARS = 32_000
DISCOVERY_ENTRY_OVERHEAD = 16


class AgentSkillCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64, pattern=SKILL_NAME_PATTERN)
    description: str = Field(min_length=1, max_length=1024)
    instructions: str = Field(min_length=1, max_length=100_000)
    enabled: bool = True

    @field_validator("name", "description", "instructions")
    @classmethod
    def text_must_not_be_surrounded_by_whitespace(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class AgentSkillUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64, pattern=SKILL_NAME_PATTERN)
    description: str = Field(min_length=1, max_length=1024)
    instructions: str = Field(min_length=1, max_length=100_000)

    @field_validator("name", "description", "instructions")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class AgentSkill(BaseModel):
    model_config = ConfigDict(frozen=True)

    skill_id: str
    name: str
    description: str
    instructions: str
    enabled: bool
    version: int
    created_by: str | None
    updated_by: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SkillCatalogRecord:
    revision: int
    skills: tuple[AgentSkill, ...]


class SkillCatalogConflictError(RuntimeError):
    pass


class SkillNameConflictError(RuntimeError):
    pass


class SkillCatalogLimitError(RuntimeError):
    pass


class SkillStore:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def get_catalog(self) -> SkillCatalogRecord:
        with self._session_factory() as session:
            catalog = session.get(SkillCatalogModel, CATALOG_ID)
            skills = session.scalars(
                select(AgentSkillModel).order_by(AgentSkillModel.name)
            ).all()
            return SkillCatalogRecord(
                revision=catalog.revision if catalog is not None else 0,
                skills=tuple(_to_domain(skill) for skill in skills),
            )

    def get_revision(self) -> int:
        with self._session_factory() as session:
            revision = session.scalar(
                select(SkillCatalogModel.revision).where(
                    SkillCatalogModel.catalog_id == CATALOG_ID
                )
            )
            return revision if revision is not None else 0

    def create_skill(
        self,
        payload: AgentSkillCreate,
        *,
        expected_revision: int,
        updated_by: str | None,
    ) -> SkillCatalogRecord:
        with self._session_factory() as session, session.begin():
            catalog = session.scalar(
                select(SkillCatalogModel)
                .where(SkillCatalogModel.catalog_id == CATALOG_ID)
                .with_for_update()
            )
            actual_revision = catalog.revision if catalog is not None else 0
            if expected_revision != actual_revision:
                raise SkillCatalogConflictError(
                    "skill catalog revision changed: "
                    f"expected {expected_revision}, actual {actual_revision}"
                )
            if catalog is None:
                catalog = SkillCatalogModel(catalog_id=CATALOG_ID, revision=0)
                session.add(catalog)
            if session.scalar(
                select(AgentSkillModel.skill_id).where(
                    AgentSkillModel.name == payload.name
                )
            ) is not None:
                raise SkillNameConflictError(
                    f"skill name already exists: {payload.name}"
                )
            if payload.enabled:
                _ensure_discovery_budget(
                    session,
                    name=payload.name,
                    description=payload.description,
                )

            skill_id = str(uuid.uuid4())
            session.add(
                AgentSkillModel(
                    skill_id=skill_id,
                    name=payload.name,
                    description=payload.description,
                    instructions=payload.instructions,
                    enabled=payload.enabled,
                    version=1,
                    created_by=updated_by,
                    updated_by=updated_by,
                )
            )
            catalog.revision = actual_revision + 1
            catalog.updated_by = updated_by

        return self.get_catalog()

    def update_skill(
        self,
        skill_id: str,
        payload: AgentSkillUpdate,
        *,
        expected_revision: int,
        updated_by: str | None,
    ) -> SkillCatalogRecord:
        with self._session_factory() as session, session.begin():
            catalog = session.scalar(
                select(SkillCatalogModel)
                .where(SkillCatalogModel.catalog_id == CATALOG_ID)
                .with_for_update()
            )
            actual_revision = catalog.revision if catalog is not None else 0
            if expected_revision != actual_revision:
                raise SkillCatalogConflictError(
                    "skill catalog revision changed: "
                    f"expected {expected_revision}, actual {actual_revision}"
                )
            skill = session.get(AgentSkillModel, skill_id)
            if skill is None:
                raise KeyError(skill_id)
            duplicate_id = session.scalar(
                select(AgentSkillModel.skill_id).where(
                    AgentSkillModel.name == payload.name,
                    AgentSkillModel.skill_id != skill_id,
                )
            )
            if duplicate_id is not None:
                raise SkillNameConflictError(
                    f"skill name already exists: {payload.name}"
                )
            if skill.enabled:
                _ensure_discovery_budget(
                    session,
                    name=payload.name,
                    description=payload.description,
                    exclude_skill_id=skill_id,
                )

            skill.name = payload.name
            skill.description = payload.description
            skill.instructions = payload.instructions
            skill.version += 1
            skill.updated_by = updated_by
            catalog.revision += 1
            catalog.updated_by = updated_by

        return self.get_catalog()

    def set_enabled(
        self,
        skill_id: str,
        enabled: bool,
        *,
        expected_revision: int,
        updated_by: str | None,
    ) -> SkillCatalogRecord:
        with self._session_factory() as session, session.begin():
            catalog = session.scalar(
                select(SkillCatalogModel)
                .where(SkillCatalogModel.catalog_id == CATALOG_ID)
                .with_for_update()
            )
            actual_revision = catalog.revision if catalog is not None else 0
            if expected_revision != actual_revision:
                raise SkillCatalogConflictError(
                    "skill catalog revision changed: "
                    f"expected {expected_revision}, actual {actual_revision}"
                )
            skill = session.get(AgentSkillModel, skill_id)
            if skill is None:
                raise KeyError(skill_id)
            if enabled and not skill.enabled:
                _ensure_discovery_budget(
                    session,
                    name=skill.name,
                    description=skill.description,
                    exclude_skill_id=skill_id,
                )

            skill.enabled = enabled
            skill.version += 1
            skill.updated_by = updated_by
            catalog.revision += 1
            catalog.updated_by = updated_by

        return self.get_catalog()

    def delete_skill(
        self,
        skill_id: str,
        *,
        expected_revision: int,
        updated_by: str | None,
    ) -> SkillCatalogRecord:
        with self._session_factory() as session, session.begin():
            catalog = session.scalar(
                select(SkillCatalogModel)
                .where(SkillCatalogModel.catalog_id == CATALOG_ID)
                .with_for_update()
            )
            actual_revision = catalog.revision if catalog is not None else 0
            if expected_revision != actual_revision:
                raise SkillCatalogConflictError(
                    "skill catalog revision changed: "
                    f"expected {expected_revision}, actual {actual_revision}"
                )
            skill = session.get(AgentSkillModel, skill_id)
            if skill is None:
                raise KeyError(skill_id)

            session.delete(skill)
            catalog.revision += 1
            catalog.updated_by = updated_by

        return self.get_catalog()


def _to_domain(model: AgentSkillModel) -> AgentSkill:
    return AgentSkill(
        skill_id=model.skill_id,
        name=model.name,
        description=model.description,
        instructions=model.instructions,
        enabled=model.enabled,
        version=model.version,
        created_by=model.created_by,
        updated_by=model.updated_by,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _ensure_discovery_budget(
    session,
    *,
    name: str,
    description: str,
    exclude_skill_id: str | None = None,
) -> None:
    statement = select(AgentSkillModel).where(AgentSkillModel.enabled.is_(True))
    if exclude_skill_id is not None:
        statement = statement.where(AgentSkillModel.skill_id != exclude_skill_id)
    enabled = session.scalars(statement).all()
    used = sum(
        len(skill.name) + len(skill.description) + DISCOVERY_ENTRY_OVERHEAD
        for skill in enabled
    )
    requested = len(name) + len(description) + DISCOVERY_ENTRY_OVERHEAD
    if used + requested > DISCOVERY_CATALOG_MAX_CHARS:
        raise SkillCatalogLimitError(
            "enabled skill metadata exceeds the discovery catalog limit of "
            f"{DISCOVERY_CATALOG_MAX_CHARS} characters"
        )


__all__ = [
    "AgentSkill",
    "AgentSkillCreate",
    "AgentSkillModel",
    "AgentSkillUpdate",
    "SkillCatalogConflictError",
    "SkillCatalogLimitError",
    "SkillCatalogModel",
    "SkillCatalogRecord",
    "SkillNameConflictError",
    "SkillStore",
]
