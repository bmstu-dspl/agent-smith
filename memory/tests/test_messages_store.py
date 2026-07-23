import pytest

from memory.messages_store import MessagesStore
from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from memory._models import MessageModel

pytestmark = pytest.mark.asyncio


async def test_append_and_get_recent_messages(messages_store: MessagesStore):
    """Базовый round-trip: записали — прочитали, порядок хронологический."""
    session_id = "session-basic"
    await messages_store.append_message(session_id, "user", "Привет")
    await messages_store.append_message(session_id, "assistant", "Здравствуйте!")

    history = await messages_store.get_recent_messages(session_id)

    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[0]["content"] == "Привет"


async def test_get_recent_messages_excludes_deactivated(messages_store: MessagesStore):
    """Guardrails-сценарий: сообщение, помеченное is_active=False, не должно попадать в контекст для LLM."""
    session_id = "session-guardrails"
    msg_id = await messages_store.append_message(session_id, "user", "Запрещённый контент")
    await messages_store.append_message(session_id, "assistant", "Обычный ответ")

    await messages_store.deactivate_messages([msg_id])
    history = await messages_store.get_recent_messages(session_id)

    assert len(history) == 1
    assert history[0]["content"] == "Обычный ответ"


async def test_get_recent_messages_excludes_drafts(messages_store: MessagesStore):
    """Промежуточные reasoning-шаги (is_final=False) не должны попадать в контекст."""
    session_id = "session-drafts"
    await messages_store.append_message(session_id, "assistant", "Черновик мысли", is_final=False)
    await messages_store.append_message(session_id, "assistant", "Финальный ответ", is_final=True)

    history = await messages_store.get_recent_messages(session_id)

    assert len(history) == 1
    assert history[0]["content"] == "Финальный ответ"


async def test_get_full_history_can_include_drafts(messages_store: MessagesStore):
    """Для guardrails-аудита должна быть возможность увидеть черновики, если явно запросить."""
    session_id = "session-audit"
    await messages_store.append_message(session_id, "assistant", "Черновик мысли", is_final=False)
    await messages_store.append_message(session_id, "assistant", "Финальный ответ", is_final=True)

    without_drafts = await messages_store.get_full_history(session_id, include_drafts=False)
    with_drafts = await messages_store.get_full_history(session_id, include_drafts=True)

    assert len(without_drafts) == 1
    assert len(with_drafts) == 2


async def test_find_buttons_context_finds_in_latest_message(messages_store: MessagesStore):
    """Сценарий 1: пользователь нажимает на кнопку из самого последнего сообщения ассистента."""
    session_id = "session-buttons-latest"
    await messages_store.append_message(
        session_id, "assistant", "Хотите забронировать номер?",
        metadata={"buttons": {"book_room": "Забронировать номер"}},
    )

    label = await messages_store.find_buttons_context(session_id, "book_room")

    assert label == "Забронировать номер"


async def test_find_buttons_context_finds_older_message_within_lookback(messages_store: MessagesStore):
    """Сценарий 2: между показом кнопки и нажатием прошло несколько обычных сообщений —
    кнопка должна находиться, если она в пределах lookback."""
    session_id = "session-buttons-older"
    await messages_store.append_message(
        session_id, "assistant", "Есть номера, показать цены?",
        metadata={"buttons": {"show_prices": "Посмотреть цены"}},
    )
    # несколько сообщений без кнопок между показом кнопки и нажатием
    await messages_store.append_message(session_id, "user", "А какая у вас парковка?")
    await messages_store.append_message(session_id, "assistant", "Парковка бесплатная")

    label = await messages_store.find_buttons_context(session_id, "show_prices")

    assert label == "Посмотреть цены"


async def test_find_buttons_context_returns_none_when_never_existed(messages_store: MessagesStore):
    """Сценарий 3: callback_data вообще никогда не генерировался в этой сессии — должно вернуться None,
    а не мусорное значение, попадающее потом в LLM."""
    session_id = "session-buttons-missing"
    await messages_store.append_message(
        session_id, "assistant", "Хотите номер?",
        metadata={"buttons": {"book_room": "Забронировать номер"}},
    )

    label = await messages_store.find_buttons_context(session_id, "totally_unknown_callback")

    assert label is None


async def test_find_buttons_context_respects_lookback_window(messages_store: MessagesStore):
    """lookback ограничивает количество ПОСЛЕДНИХ СООБЩЕНИЙ С КНОПКАМИ, которые просматриваются —
    если старая кнопка вышла за пределы этого окна (появилось много новых сообщений с кнопками после неё),
    она не должна находиться."""
    session_id = "session-buttons-too-old"
    await messages_store.append_message(
        session_id, "assistant", "Старое предложение",
        metadata={"buttons": {"old_offer": "Старая кнопка"}},
    )
    # добавляем несколько НОВЫХ сообщений С КНОПКАМИ, чтобы старое вышло за пределы lookback
    for i in range(5):
        await messages_store.append_message(
            session_id, "assistant", f"Новое предложение {i}",
            metadata={"buttons": {f"offer_{i}": f"Кнопка {i}"}},
        )

    label = await messages_store.find_buttons_context(session_id, "old_offer", lookback=3)

    assert label is None




async def test_get_handoff_history_uses_time_window_when_enough_messages(messages_store: MessagesStore):
    """Если сообщений за окно достаточно (>= fallback_count) — время само по себе не режет диалог."""
    session_id = "session-handoff-window"
    for i in range(3):
        await messages_store.append_message(session_id, "user", f"Сообщение {i}")

    history = await messages_store.get_handoff_history(session_id, hours=24, fallback_count=2)

    assert len(history) == 3
    assert [m["content"] for m in history] == ["Сообщение 0", "Сообщение 1", "Сообщение 2"]


async def test_get_handoff_history_falls_back_when_window_too_small(messages_store: MessagesStore):
    """Сообщения старше окна, но их мало в окне — должен сработать fallback по количеству."""
    session_id = "session-handoff-fallback"
    old_id = await messages_store.append_message(session_id, "user", "Старое сообщение")
    await messages_store.append_message(session_id, "user", "Новое сообщение")

    # искусственно состариваем первое сообщение, чтобы оно выпало из временного окна
    with messages_store._db.session() as db_session:
        db_session.execute(
            update(MessageModel)
            .where(MessageModel.message_id == old_id)
            .values(created_at=datetime.now(timezone.utc) - timedelta(hours=48))
        )

    history = await messages_store.get_handoff_history(session_id, hours=24, fallback_count=2)

    assert len(history) == 2
    assert [m["content"] for m in history] == ["Старое сообщение", "Новое сообщение"]


async def test_get_handoff_history_excludes_deactivated_messages(messages_store: MessagesStore):
    """Guardrails: отфильтрованные (is_active=False) сообщения не должны попадать оператору."""
    session_id = "session-handoff-guardrails"
    bad_id = await messages_store.append_message(session_id, "user", "Запрещённый контент")
    await messages_store.append_message(session_id, "assistant", "Обычный ответ")
    await messages_store.deactivate_messages([bad_id])

    history = await messages_store.get_handoff_history(session_id, hours=24, fallback_count=1)

    assert len(history) == 1
    assert history[0]["content"] == "Обычный ответ"
