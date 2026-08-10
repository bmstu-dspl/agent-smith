from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiohttp import web
import pytest

from app.live_config import TelegramRuntimeSettings
from app.telegram_runtime import LiveTelegramBotRuntime, LiveTelegramWebhookHandler


def _settings(*, revision: int, token: str, host: str = "https://bot.example.test"):
    return TelegramRuntimeSettings(
        revision=revision,
        bot_token=token,
        webhook_host=host,
        manager_group_id=-1001,
        ai_agent_url="http://ai-agent:8000",
        enable_escalation=True,
    )


class FakeBot:
    def __init__(self, token: str, *, bot_id: int, username: str) -> None:
        self.token = token
        self.get_me = AsyncMock(
            return_value=SimpleNamespace(id=bot_id, username=username)
        )
        self.set_webhook = AsyncMock()
        self.delete_webhook = AsyncMock()
        self.session = SimpleNamespace(close=AsyncMock())


def _dispatcher():
    return SimpleNamespace(
        workflow_data={},
        resolve_used_update_types=Mock(return_value=["message", "callback_query"]),
    )


@pytest.mark.asyncio
async def test_token_change_switches_bot_only_after_new_webhook_is_ready() -> None:
    old_settings = _settings(revision=1, token="old-token")
    new_settings = _settings(revision=2, token="new-token")
    old_bot = FakeBot("old-token", bot_id=1, username="old_bot")
    new_bot = FakeBot("new-token", bot_id=2, username="new_bot")
    dispatcher = _dispatcher()
    provider = SimpleNamespace(get=AsyncMock(return_value=new_settings))
    prepare_bot = AsyncMock()
    bot_switched = AsyncMock()
    runtime = LiveTelegramBotRuntime(
        dispatcher=dispatcher,
        settings_provider=provider,
        initial_settings=old_settings,
        initial_bot=old_bot,
        bot_factory=Mock(return_value=new_bot),
        prepare_bot=prepare_bot,
        bot_switched=bot_switched,
        retired_bot_grace_seconds=30,
    )

    assert await runtime.refresh()

    assert runtime.bot is new_bot
    assert runtime.settings == new_settings
    assert runtime.resolve_bot(new_settings.webhook_path) is new_bot
    assert runtime.resolve_bot(old_settings.webhook_path) is old_bot
    assert dispatcher.workflow_data["bot"] is new_bot
    prepare_bot.assert_awaited_once_with(new_bot, new_settings)
    new_bot.set_webhook.assert_awaited_once_with(
        url=new_settings.webhook_url,
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=False,
    )
    bot_switched.assert_awaited_once_with(new_bot, new_settings)
    old_bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=False)
    await runtime.close()


@pytest.mark.asyncio
async def test_failed_new_webhook_keeps_current_bot_and_can_be_retried() -> None:
    old_settings = _settings(revision=1, token="old-token")
    new_settings = _settings(revision=2, token="new-token")
    old_bot = FakeBot("old-token", bot_id=1, username="old_bot")
    failed_bot = FakeBot("new-token", bot_id=2, username="new_bot")
    failed_bot.set_webhook.side_effect = RuntimeError("Telegram unavailable")
    dispatcher = _dispatcher()
    provider = SimpleNamespace(get=AsyncMock(return_value=new_settings))
    runtime = LiveTelegramBotRuntime(
        dispatcher=dispatcher,
        settings_provider=provider,
        initial_settings=old_settings,
        initial_bot=old_bot,
        bot_factory=Mock(return_value=failed_bot),
    )

    assert not await runtime.refresh()

    assert runtime.bot is old_bot
    assert runtime.settings == old_settings
    assert runtime.resolve_bot(old_settings.webhook_path) is old_bot
    assert runtime.resolve_bot(new_settings.webhook_path) is None
    old_bot.delete_webhook.assert_not_awaited()
    failed_bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=False)
    failed_bot.session.close.assert_awaited_once()
    await runtime.close()


@pytest.mark.asyncio
async def test_webhook_host_change_reuses_identity_and_updates_webhook() -> None:
    old_settings = _settings(revision=1, token="same-token")
    new_settings = _settings(
        revision=2,
        token="same-token",
        host="https://new.example.test",
    )
    bot = FakeBot("same-token", bot_id=1, username="same_bot")
    factory = Mock()
    runtime = LiveTelegramBotRuntime(
        dispatcher=_dispatcher(),
        settings_provider=SimpleNamespace(get=AsyncMock(return_value=new_settings)),
        initial_settings=old_settings,
        initial_bot=bot,
        bot_factory=factory,
    )

    assert await runtime.refresh()

    factory.assert_not_called()
    assert runtime.bot is bot
    assert runtime.settings == new_settings
    bot.set_webhook.assert_awaited_once_with(
        url=new_settings.webhook_url,
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=False,
    )
    await runtime.close()


@pytest.mark.asyncio
async def test_webhook_handler_rejects_unknown_hashed_path() -> None:
    settings = _settings(revision=1, token="token")
    bot = FakeBot("token", bot_id=1, username="bot")
    dispatcher = _dispatcher()
    runtime = LiveTelegramBotRuntime(
        dispatcher=dispatcher,
        settings_provider=SimpleNamespace(get=AsyncMock(return_value=settings)),
        initial_settings=settings,
        initial_bot=bot,
        bot_factory=Mock(),
    )
    handler = LiveTelegramWebhookHandler(dispatcher=dispatcher, runtime=runtime)

    resolved = await handler.resolve_bot(
        SimpleNamespace(match_info={"token_digest": settings.webhook_path.rsplit("/", 1)[1]})
    )
    assert resolved is bot
    with pytest.raises(web.HTTPNotFound):
        await handler.resolve_bot(
            SimpleNamespace(match_info={"token_digest": "0" * 64})
        )
    await runtime.close()


@pytest.mark.asyncio
async def test_watcher_applies_new_revision_without_an_incoming_update() -> None:
    old_settings = _settings(revision=1, token="old-token")
    new_settings = _settings(revision=2, token="new-token")
    old_bot = FakeBot("old-token", bot_id=1, username="old_bot")
    new_bot = FakeBot("new-token", bot_id=2, username="new_bot")
    switched = asyncio.Event()

    async def bot_switched(_bot, _settings):
        switched.set()

    runtime = LiveTelegramBotRuntime(
        dispatcher=_dispatcher(),
        settings_provider=SimpleNamespace(get=AsyncMock(return_value=new_settings)),
        initial_settings=old_settings,
        initial_bot=old_bot,
        bot_factory=Mock(return_value=new_bot),
        bot_switched=bot_switched,
        poll_interval_seconds=0.01,
    )

    runtime.start()
    await asyncio.wait_for(switched.wait(), timeout=0.5)

    assert runtime.bot is new_bot
    assert runtime.settings.revision == 2
    await runtime.close()
