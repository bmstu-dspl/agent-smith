from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.handlers import UserStates, cmd_new, cmd_start
from app.middleware.session_middleware import SessionMiddleware


class FakeRedis:
    def __init__(self) -> None:
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def setex(self, key, _ttl, value):
        self.values[key] = value.encode() if isinstance(value, str) else value

    async def expire(self, _key, _ttl):
        return True


@pytest.mark.asyncio
async def test_rotating_an_in_memory_session_changes_the_agent_thread() -> None:
    middleware = SessionMiddleware()

    first = await middleware.rotate_session(42)
    second = await middleware.rotate_session(42)

    assert first != second
    assert await middleware.get_user_session(42) == second


@pytest.mark.asyncio
async def test_rotating_a_redis_session_preserves_old_session_record() -> None:
    redis = FakeRedis()
    middleware = SessionMiddleware(redis)

    first = await middleware._get_or_create_session(42)
    second = await middleware.rotate_session(42)

    assert first != second
    assert await middleware.get_user_session(42) == second
    assert f"session:{first}" in redis.values
    assert f"session:{second}" in redis.values


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "expected_message"),
    [
        (cmd_start, "Привет! Я ИИ-помощник."),
        (cmd_new, "Новый диалог начат. Чем я могу помочь?"),
    ],
)
async def test_start_and_new_rotate_context_before_greeting(
    handler,
    expected_message: str,
) -> None:
    middleware = SimpleNamespace(rotate_session=AsyncMock(return_value="new-thread"))
    state = SimpleNamespace(set_state=AsyncMock())
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        answer=AsyncMock(),
    )

    await handler(message, state, middleware)

    middleware.rotate_session.assert_awaited_once_with(42)
    state.set_state.assert_awaited_once_with(UserStates.default)
    assert expected_message in message.answer.await_args.args[0]
