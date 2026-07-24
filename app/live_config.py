from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import os

from admin_panel.settings import SettingsStore


@dataclass(frozen=True, slots=True)
class TelegramRuntimeSettings:
    revision: int
    bot_token: str
    webhook_host: str
    manager_group_id: int | None
    ai_agent_url: str
    enable_escalation: bool

    @property
    def webhook_path(self) -> str:
        token_digest = hashlib.sha256(self.bot_token.encode("utf-8")).hexdigest()
        return f"/webhook/{token_digest}"

    @property
    def webhook_url(self) -> str:
        return f"{self.webhook_host.rstrip('/')}{self.webhook_path}"


class LiveTelegramSettingsProvider:
    """Loads bot identity before startup and refreshes mutable behavior per update."""

    def __init__(self, settings_store: SettingsStore) -> None:
        self._settings_store = settings_store
        self._current: TelegramRuntimeSettings | None = None

    def load_initial(self) -> TelegramRuntimeSettings:
        record = self._settings_store.get_telegram()
        token = record.bot_token or _env_secret("BOT_TOKEN")
        if not token:
            raise RuntimeError("Telegram bot token is not configured")
        settings = record.settings
        webhook_host = settings.webhook_host or os.getenv("WEBHOOK_HOST", "")
        if not webhook_host:
            raise RuntimeError("Telegram webhook host is not configured")
        self._current = TelegramRuntimeSettings(
            revision=record.revision,
            bot_token=token,
            webhook_host=webhook_host,
            manager_group_id=(
                settings.manager_group_id
                if record.revision
                else _optional_int("MANAGER_GROUP_ID")
            ),
            ai_agent_url=(
                settings.ai_agent_url
                if record.revision
                else os.getenv("AI_AGENT_URL", "http://ai-agent:8000")
            ),
            enable_escalation=settings.enable_escalation,
        )
        return self._current

    async def get(self) -> TelegramRuntimeSettings:
        record = await asyncio.to_thread(self._settings_store.get_telegram)
        if self._current is not None and record.revision == self._current.revision:
            return self._current
        previous = self._current or self.load_initial()
        self._current = TelegramRuntimeSettings(
            revision=record.revision,
            bot_token=record.bot_token or previous.bot_token,
            webhook_host=record.settings.webhook_host or previous.webhook_host,
            manager_group_id=record.settings.manager_group_id,
            ai_agent_url=record.settings.ai_agent_url,
            enable_escalation=record.settings.enable_escalation,
        )
        return self._current


def _env_secret(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    file_path = os.getenv(f"{name}_FILE")
    if not file_path:
        return ""
    try:
        return open(file_path, encoding="utf-8").read().strip()
    except OSError as error:
        raise RuntimeError(f"failed to read {name}_FILE") from error


def _optional_int(name: str) -> int | None:
    value = os.getenv(name)
    return int(value) if value else None
