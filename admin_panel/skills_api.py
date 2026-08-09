from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from .skills import (
    AgentSkillCreate,
    AgentSkillUpdate,
    SkillCatalogConflictError,
    SkillCatalogLimitError,
    SkillCatalogRecord,
    SkillNameConflictError,
)


class SkillCreateRequest(AgentSkillCreate):
    revision: int = Field(ge=0)


class SkillUpdateRequest(AgentSkillUpdate):
    revision: int = Field(ge=0)


class SkillToggleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=0)
    enabled: bool


class SkillDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=0)


def create_skills_router(require_identity, require_mutation_access) -> APIRouter:
    router = APIRouter(prefix="/admin/api/skills", tags=["admin-skills"])

    @router.get("")
    async def list_skills(request: Request) -> dict:
        require_identity(request)
        record = await asyncio.to_thread(_store(request).get_catalog)
        return _public_catalog(record)

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def create_skill(request: Request, payload: SkillCreateRequest) -> dict:
        identity = require_mutation_access(request, required_role="editor")
        try:
            record = await asyncio.to_thread(
                _store(request).create_skill,
                AgentSkillCreate.model_validate(payload.model_dump(exclude={"revision"})),
                expected_revision=payload.revision,
                updated_by=identity.admin_id,
            )
        except (SkillCatalogConflictError, SkillNameConflictError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except SkillCatalogLimitError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return _public_catalog(record)

    @router.put("/{skill_id}")
    async def update_skill(
        request: Request,
        skill_id: str,
        payload: SkillUpdateRequest,
    ) -> dict:
        identity = require_mutation_access(request, required_role="editor")
        try:
            record = await asyncio.to_thread(
                _store(request).update_skill,
                skill_id,
                AgentSkillUpdate.model_validate(payload.model_dump(exclude={"revision"})),
                expected_revision=payload.revision,
                updated_by=identity.admin_id,
            )
        except (SkillCatalogConflictError, SkillNameConflictError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except SkillCatalogLimitError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Skill not found") from error
        return _public_catalog(record)

    @router.post("/{skill_id}/toggle")
    async def toggle_skill(
        request: Request,
        skill_id: str,
        payload: SkillToggleRequest,
    ) -> dict:
        identity = require_mutation_access(request, required_role="editor")
        try:
            record = await asyncio.to_thread(
                _store(request).set_enabled,
                skill_id,
                payload.enabled,
                expected_revision=payload.revision,
                updated_by=identity.admin_id,
            )
        except SkillCatalogConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except SkillCatalogLimitError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Skill not found") from error
        return _public_catalog(record)

    @router.delete("/{skill_id}")
    async def delete_skill(
        request: Request,
        skill_id: str,
        payload: SkillDeleteRequest,
    ) -> dict:
        identity = require_mutation_access(request, required_role="editor")
        try:
            record = await asyncio.to_thread(
                _store(request).delete_skill,
                skill_id,
                expected_revision=payload.revision,
                updated_by=identity.admin_id,
            )
        except SkillCatalogConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Skill not found") from error
        return _public_catalog(record)

    return router


def _store(request: Request):
    store = getattr(request.app.state, "skill_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Skill catalog unavailable")
    return store


def _public_catalog(record: SkillCatalogRecord) -> dict:
    return {
        "revision": record.revision,
        "skills": [skill.model_dump(mode="json") for skill in record.skills],
    }
