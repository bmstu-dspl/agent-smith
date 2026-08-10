from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import BaseRequestHandler
from aiohttp import web

from app.live_config import LiveTelegramSettingsProvider, TelegramRuntimeSettings


logger = logging.getLogger(__name__)

BotFactory = Callable[[str], Bot]
BotHook = Callable[[Bot, TelegramRuntimeSettings], Awaitable[None]]


async def _noop_hook(_bot: Bot, _settings: TelegramRuntimeSettings) -> None:
    return None


class LiveTelegramBotRuntime:
    """Owns the active Telegram identity and switches it without process restarts."""

    def __init__(
        self,
        *,
        dispatcher: Dispatcher,
        settings_provider: LiveTelegramSettingsProvider,
        initial_settings: TelegramRuntimeSettings,
        initial_bot: Bot,
        bot_factory: BotFactory,
        prepare_bot: BotHook = _noop_hook,
        bot_switched: BotHook = _noop_hook,
        poll_interval_seconds: float = 1.0,
        retired_bot_grace_seconds: float = 30.0,
        drop_pending_updates: bool = False,
        delete_webhook_on_shutdown: bool = False,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if retired_bot_grace_seconds < 0:
            raise ValueError("retired_bot_grace_seconds must not be negative")
        self.dispatcher = dispatcher
        self.settings_provider = settings_provider
        self._settings = initial_settings
        self._bot = initial_bot
        self._bot_factory = bot_factory
        self._prepare_bot = prepare_bot
        self._bot_switched = bot_switched
        self._poll_interval_seconds = poll_interval_seconds
        self._retired_bot_grace_seconds = retired_bot_grace_seconds
        self._drop_pending_updates = drop_pending_updates
        self._delete_webhook_on_shutdown = delete_webhook_on_shutdown
        self._bots_by_path = {initial_settings.webhook_path: initial_bot}
        self._refresh_lock = asyncio.Lock()
        self._watch_task: asyncio.Task[None] | None = None
        self._retirement_tasks: set[asyncio.Task[None]] = set()
        self._closed = False

    @property
    def bot(self) -> Bot:
        return self._bot

    @property
    def settings(self) -> TelegramRuntimeSettings:
        return self._settings

    def resolve_bot(self, webhook_path: str) -> Bot | None:
        return self._bots_by_path.get(webhook_path)

    def start(self) -> None:
        if self._closed:
            raise RuntimeError("Telegram bot runtime is closed")
        if self._watch_task is None:
            self._watch_task = asyncio.create_task(
                self._watch_settings(),
                name="telegram-settings-watcher",
            )

    async def refresh(self) -> bool:
        """Apply a newer settings revision, preserving the old bot on failure."""
        async with self._refresh_lock:
            updated = await self.settings_provider.get()
            if updated.revision == self._settings.revision:
                return False
            if updated.bot_token == self._settings.bot_token:
                await self._prepare_bot(self._bot, updated)
                await self._bot.set_webhook(
                    url=updated.webhook_url,
                    allowed_updates=self.dispatcher.resolve_used_update_types(),
                    drop_pending_updates=self._drop_pending_updates,
                )
                self._settings = updated
                logger.info(
                    "Telegram runtime settings reloaded revision=%s identity_unchanged=true",
                    updated.revision,
                )
                return True

            candidate = self._bot_factory(updated.bot_token)
            try:
                identity = await candidate.get_me()
                await self._prepare_bot(candidate, updated)
                await candidate.set_webhook(
                    url=updated.webhook_url,
                    allowed_updates=self.dispatcher.resolve_used_update_types(),
                    drop_pending_updates=self._drop_pending_updates,
                )
                await self._bot_switched(candidate, updated)
            except asyncio.CancelledError:
                try:
                    await candidate.delete_webhook(drop_pending_updates=False)
                except Exception:
                    logger.warning(
                        "Failed to clean up canceled Telegram webhook revision=%s",
                        updated.revision,
                    )
                await candidate.session.close()
                raise
            except Exception:
                try:
                    await candidate.delete_webhook(drop_pending_updates=False)
                except Exception:
                    logger.warning(
                        "Failed to clean up candidate Telegram webhook revision=%s",
                        updated.revision,
                    )
                await candidate.session.close()
                logger.exception(
                    "Telegram token hot reload failed revision=%s; keeping current bot",
                    updated.revision,
                )
                return False

            previous_bot = self._bot
            previous_settings = self._settings
            self._bots_by_path[updated.webhook_path] = candidate
            self._bot = candidate
            self._settings = updated
            self.dispatcher.workflow_data["bot"] = candidate
            logger.info(
                "Telegram bot hot reloaded revision=%s bot_id=%s username=%s",
                updated.revision,
                identity.id,
                identity.username,
            )

            try:
                await previous_bot.delete_webhook(drop_pending_updates=False)
            except Exception:
                logger.exception(
                    "Failed to delete webhook for retired Telegram bot revision=%s",
                    previous_settings.revision,
                )
            self._schedule_retirement(previous_settings.webhook_path, previous_bot)
            return True

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._watch_task is not None:
            self._watch_task.cancel()
            await asyncio.gather(self._watch_task, return_exceptions=True)
            self._watch_task = None
        for task in self._retirement_tasks:
            task.cancel()
        if self._retirement_tasks:
            await asyncio.gather(*self._retirement_tasks, return_exceptions=True)
        self._retirement_tasks.clear()
        if self._delete_webhook_on_shutdown:
            try:
                await self._bot.delete_webhook()
                logger.info("Webhook deleted")
            except Exception:
                logger.exception("Error deleting webhook during shutdown")
        unique_bots = {id(bot): bot for bot in self._bots_by_path.values()}
        self._bots_by_path.clear()
        for bot in unique_bots.values():
            await bot.session.close()

    async def _watch_settings(self) -> None:
        while True:
            await asyncio.sleep(self._poll_interval_seconds)
            try:
                await self.refresh()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Telegram settings watcher failed; will retry")

    def _schedule_retirement(self, webhook_path: str, bot: Bot) -> None:
        task = asyncio.create_task(
            self._retire_bot(webhook_path, bot),
            name="retire-telegram-bot",
        )
        self._retirement_tasks.add(task)
        task.add_done_callback(self._retirement_tasks.discard)

    async def _retire_bot(self, webhook_path: str, bot: Bot) -> None:
        await asyncio.sleep(self._retired_bot_grace_seconds)
        if self._bots_by_path.get(webhook_path) is bot:
            self._bots_by_path.pop(webhook_path, None)
        await bot.session.close()


class LiveTelegramWebhookHandler(BaseRequestHandler):
    """Routes a hashed webhook path to the matching live or retiring bot."""

    def __init__(self, dispatcher: Dispatcher, runtime: LiveTelegramBotRuntime) -> None:
        super().__init__(dispatcher=dispatcher, handle_in_background=True)
        self.runtime = runtime

    async def resolve_bot(self, request: web.Request) -> Bot:
        webhook_path = "/webhook/" + request.match_info["token_digest"]
        bot = self.runtime.resolve_bot(webhook_path)
        if bot is None:
            raise web.HTTPNotFound()
        return bot

    def verify_secret(self, telegram_secret_token: str, bot: Bot) -> bool:
        del telegram_secret_token, bot
        return True

    async def close(self) -> None:
        await self.runtime.close()
