from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.fsm.storage.redis import RedisEventIsolation, RedisStorage
from aiogram.types import User

import app.handlers as handlers
from app.escalation_service import EscalationService
from app.handlers import UserStates, _handle_handoff_event, handle_user_default, router
from run import FSM_TTL_SECONDS, build_dispatcher, build_fsm_storage


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    async def get(self, key):
        return self.values.get(self._key(key))

    async def set(self, key, value):
        self.values[self._key(key)] = value.encode() if isinstance(value, str) else value
        return True

    async def delete(self, *keys):
        for key in keys:
            self.values.pop(self._key(key), None)
        return len(keys)

    async def scan_iter(self, match: str):
        prefix = match.removesuffix("*")
        for key in list(self.values):
            if key.startswith(prefix):
                yield key.encode()

    @staticmethod
    def _key(value) -> str:
        return value.decode() if isinstance(value, bytes) else str(value)


@pytest.mark.asyncio
async def test_dispatcher_fsm_storage_is_redis_backed_with_ttl() -> None:
    storage = build_fsm_storage("redis://localhost:6379/15")
    try:
        assert isinstance(storage, RedisStorage)
        assert storage.state_ttl == FSM_TTL_SECONDS
        assert storage.data_ttl == FSM_TTL_SECONDS
        assert storage.key_builder.prefix == "agent-smith:fsm"
    finally:
        await storage.close()


@pytest.mark.asyncio
async def test_dispatcher_uses_redis_event_isolation() -> None:
    dispatcher = build_dispatcher("redis://localhost:6379/15")
    try:
        assert isinstance(dispatcher.storage, RedisStorage)
        assert isinstance(dispatcher.fsm.events_isolation, RedisEventIsolation)
    finally:
        await dispatcher.storage.close()


def test_redis_eviction_preserves_persistent_escalations() -> None:
    compose = (PROJECT_ROOT / "docker-compose.yaml").read_text()
    assert "--maxmemory-policy volatile-lru" in compose


@pytest.mark.asyncio
async def test_default_text_route_accepts_missing_legacy_fsm_state() -> None:
    handler = next(item for item in router.message.handlers if item.callback is handle_user_default)
    state_filter = handler.filters[0].callback

    assert await state_filter(SimpleNamespace(), raw_state=None) is True
    assert await state_filter(SimpleNamespace(), raw_state=UserStates.default.state) is True


@pytest.mark.asyncio
async def test_escalation_and_thread_mapping_survive_service_restarts() -> None:
    redis = FakeRedis()
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=700)),
        create_forum_topic=AsyncMock(return_value=SimpleNamespace(message_thread_id=900)),
    )
    user = User(id=42, is_bot=False, first_name="Test", username="guest")
    message = SimpleNamespace(
        from_user=user,
        chat=SimpleNamespace(id=42),
        message_id=100,
        date=datetime.now(timezone.utc),
        text="Позови оператора",
        answer=AsyncMock(),
    )

    first = EscalationService(bot, -100123, redis=redis)
    await first.initialize()
    assert await first.escalate_to_managers(
        message,
        summary="Гость выбирает номер.",
        history=[{"role": "user", "content": "Нужен оператор"}],
        notify_user=False,
    )

    second = EscalationService(bot, -100123, redis=redis)
    await second.initialize()
    assert second.active_escalations[42]["status"] == "pending"

    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=7, full_name="Manager"),
        message=SimpleNamespace(text="Ticket", edit_text=AsyncMock()),
        answer=AsyncMock(),
    )
    assert await second.take_ticket(callback, 42)

    third = EscalationService(bot, -100123, redis=redis)
    await third.initialize()
    assert third.active_escalations[42]["status"] == "active"
    assert third.user_threads == {42: 900}
    assert third.thread_users == {900: 42}

    assert await third.close_escalation(42)
    fourth = EscalationService(bot, -100123, redis=redis)
    await fourth.initialize()
    assert fourth.active_escalations == {}
    assert fourth.thread_users == {}


@pytest.mark.asyncio
async def test_handoff_event_creates_ticket_and_switches_user_state(monkeypatch) -> None:
    service = SimpleNamespace(
        update_manager_group_id=Mock(),
        escalate_to_managers=AsyncMock(return_value=True),
    )
    settings_provider = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                enable_escalation=True,
                manager_group_id=-100123,
            )
        )
    )
    monkeypatch.setattr(handlers, "_esc_service", service)
    monkeypatch.setattr(handlers, "_settings_provider", settings_provider)

    user = User(id=42, is_bot=False, first_name="Test")
    message = SimpleNamespace(from_user=user)
    state = SimpleNamespace(set_state=AsyncMock())
    event = {
        "type": "handoff",
        "reason": "Гость попросил сотрудника",
        "summary": "Нужна помощь с выбором номера",
        "history": [{"role": "user", "content": "Позови оператора"}],
    }

    assert await _handle_handoff_event(message, state, event)
    service.escalate_to_managers.assert_awaited_once()
    state.set_state.assert_awaited_once_with(UserStates.with_manager)
