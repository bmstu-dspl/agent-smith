from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .db_models import ServiceSettingsModel
from .default_prompts import AGENT_SYSTEM_PROMPT_DEFAULT


class TelegramSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    webhook_host: str = ""
    manager_group_id: int | None = None
    ai_agent_url: str = Field(default="http://ai-agent:8000", min_length=1)
    enable_escalation: bool = True

    @field_validator("manager_group_id")
    @classmethod
    def manager_group_must_be_negative(cls, value: int | None) -> int | None:
        if value is not None and value >= 0:
            raise ValueError("manager_group_id must be negative")
        return value


class TelegramSettingsUpdate(TelegramSettings):
    revision: int = Field(ge=0)
    bot_token: str | None = Field(default=None, min_length=1)


@dataclass(frozen=True, slots=True)
class TelegramSettingsRecord:
    settings: TelegramSettings
    revision: int
    bot_token: str | None


class AgentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["google_vertex", "openai"] = "google_vertex"
    model: str = Field(default="gemini-2.5-flash", min_length=1, max_length=200)
    temperature: float = Field(default=0.2, ge=0, le=2)
    primary_timezone: str = Field(default="UTC", min_length=1, max_length=200)
    system_prompt: str = Field(
        default=AGENT_SYSTEM_PROMPT_DEFAULT,
        min_length=1,
        max_length=100_000,
    )

    @field_validator("primary_timezone")
    @classmethod
    def primary_timezone_must_be_iana_name(cls, value: str) -> str:
        normalized = value.strip()
        try:
            ZoneInfo(normalized)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise ValueError("primary_timezone must be a valid IANA timezone") from error
        return normalized


class AgentSettingsUpdate(AgentSettings):
    revision: int = Field(ge=0)


class RagSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    additional_instructions: str = Field(default="", max_length=50_000)
    max_chunk_chars: int = Field(default=1200, ge=100, le=50_000)
    chunk_overlap_chars: int = Field(default=150, ge=0, le=10_000)
    retrieval_mode: Literal["semantic", "lexical", "hybrid"] = "hybrid"
    limit: int = Field(default=8, ge=1, le=100)
    max_context_chars: int = Field(default=12_000, ge=100, le=1_000_000)

    @model_validator(mode="after")
    def overlap_must_be_smaller_than_chunk(self) -> "RagSettings":
        if self.chunk_overlap_chars >= self.max_chunk_chars:
            raise ValueError("chunk_overlap_chars must be smaller than max_chunk_chars")
        return self


class RagSettingsUpdate(RagSettings):
    revision: int = Field(ge=0)


@dataclass(frozen=True, slots=True)
class SettingsRecord:
    settings: BaseModel
    revision: int


class SettingsConflictError(RuntimeError):
    pass


class SettingsStore:
    def __init__(self, session_factory, encryption_key: str) -> None:
        self._session_factory = session_factory
        try:
            self._fernet = Fernet(encryption_key.encode())
        except (TypeError, ValueError) as error:
            raise ValueError("CONFIG_SECRETS_ENCRYPTION_KEY must be a Fernet key") from error

    def get_telegram(self) -> TelegramSettingsRecord:
        with self._session_factory() as session:
            row = session.get(ServiceSettingsModel, "telegram")
            if row is None:
                return TelegramSettingsRecord(
                    settings=TelegramSettings(webhook_host=""),
                    revision=0,
                    bot_token=None,
                )
            secrets = self._decrypt(row.secrets_encrypted)
            return TelegramSettingsRecord(
                settings=TelegramSettings.model_validate(row.payload),
                revision=row.revision,
                bot_token=secrets.get("bot_token"),
            )

    def save_telegram(
        self,
        update: TelegramSettingsUpdate,
        *,
        updated_by: str | None,
    ) -> TelegramSettingsRecord:
        with self._session_factory() as session, session.begin():
            row = session.get(ServiceSettingsModel, "telegram")
            actual_revision = row.revision if row else 0
            if update.revision != actual_revision:
                raise SettingsConflictError(
                    f"settings revision changed: expected {update.revision}, actual {actual_revision}"
                )

            existing_secrets = self._decrypt(row.secrets_encrypted) if row else {}
            if update.bot_token is not None:
                existing_secrets["bot_token"] = update.bot_token
            settings = TelegramSettings.model_validate(
                update.model_dump(exclude={"revision", "bot_token"})
            )
            next_revision = actual_revision + 1
            if row is None:
                row = ServiceSettingsModel(area="telegram")
                session.add(row)
            row.revision = next_revision
            row.payload = settings.model_dump(mode="json")
            row.secrets_encrypted = self._encrypt(existing_secrets)
            row.updated_by = updated_by

        return TelegramSettingsRecord(
            settings=settings,
            revision=next_revision,
            bot_token=existing_secrets.get("bot_token"),
        )

    def get_agent(self) -> SettingsRecord:
        return self._get_area("agent", AgentSettings, AgentSettings())

    def save_agent(
        self, update: AgentSettingsUpdate, *, updated_by: str | None
    ) -> SettingsRecord:
        settings = AgentSettings.model_validate(update.model_dump(exclude={"revision"}))
        return self._save_area(
            "agent",
            settings,
            expected_revision=update.revision,
            updated_by=updated_by,
        )

    def get_rag(self) -> SettingsRecord:
        return self._get_area("rag", RagSettings, RagSettings())

    def save_rag(
        self, update: RagSettingsUpdate, *, updated_by: str | None
    ) -> SettingsRecord:
        settings = RagSettings.model_validate(update.model_dump(exclude={"revision"}))
        return self._save_area(
            "rag",
            settings,
            expected_revision=update.revision,
            updated_by=updated_by,
        )

    def _get_area(self, area: str, model_type, default: BaseModel) -> SettingsRecord:
        with self._session_factory() as session:
            row = session.get(ServiceSettingsModel, area)
            if row is None:
                return SettingsRecord(default, 0)
            return SettingsRecord(model_type.model_validate(row.payload), row.revision)

    def _save_area(
        self,
        area: str,
        settings: BaseModel,
        *,
        expected_revision: int,
        updated_by: str | None,
    ) -> SettingsRecord:
        with self._session_factory() as session, session.begin():
            row = session.get(ServiceSettingsModel, area)
            actual_revision = row.revision if row else 0
            if expected_revision != actual_revision:
                raise SettingsConflictError(
                    f"settings revision changed: expected {expected_revision}, actual {actual_revision}"
                )
            next_revision = actual_revision + 1
            if row is None:
                row = ServiceSettingsModel(area=area, secrets_encrypted="")
                session.add(row)
            row.revision = next_revision
            row.payload = settings.model_dump(mode="json")
            row.updated_by = updated_by
        return SettingsRecord(settings, next_revision)

    def _encrypt(self, value: dict[str, str]) -> str:
        return self._fernet.encrypt(json.dumps(value).encode()).decode()

    def _decrypt(self, value: str) -> dict[str, str]:
        if not value:
            return {}
        try:
            decoded = json.loads(self._fernet.decrypt(value.encode()))
        except (InvalidToken, ValueError, TypeError, json.JSONDecodeError) as error:
            raise RuntimeError("unable to decrypt service settings") from error
        return decoded if isinstance(decoded, dict) else {}
