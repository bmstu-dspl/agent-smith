import json

import pytest
from fastapi.testclient import TestClient

from ai_core.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:  # запускает lifespan -> реальную инициализацию MemoryManager против тестовой БД
        yield c


def _parse_ndjson(raw: bytes) -> list[dict]:
    return [json.loads(line) for line in raw.decode().strip().split("\n") if line]


def test_plain_text_message_flow(client: TestClient):
    """Обычное сообщение: должны прийти buttons -> text_chunk* -> end."""
    with client.stream("POST", "/agent/process", json={
        "session_id": "route-test-text",
        "user_message": "Привет",
    }) as response:
        events = _parse_ndjson(response.read())

    assert events[0]["type"] == "buttons"
    assert events[-1]["type"] == "end"
    assert any(e["type"] == "text_chunk" for e in events)


def test_callback_with_unknown_data_returns_fallback(client: TestClient):
    """Имитация нажатия на кнопку, которой никогда не существовало — должен прийти fallback,
    без обращения к графу."""
    with client.stream("POST", "/agent/process", json={
        "session_id": "route-test-unknown-callback",
        "user_message": "some_never_generated_callback",
        "message_type": "callback",
    }) as response:
        events = _parse_ndjson(response.read())

    full_text = "".join(e["content"] for e in events if e["type"] == "text_chunk")
    assert "напишите ваш вопрос текстом" in full_text


def test_callback_resolves_to_button_label(client: TestClient):
    """Полный сценарий: сначала сообщение, генерирующее кнопки (StubGraph реагирует на слово 'номер'),
    затем имитация нажатия одной из этих кнопок — без реального Telegram."""
    session_id = "route-test-callback-flow"

    with client.stream("POST", "/agent/process", json={
        "session_id": session_id,
        "user_message": "Есть свободные номера?",
    }) as response:
        first_events = _parse_ndjson(response.read())

    buttons = first_events[0]["buttons"]
    assert any(b["callback_data"] == "book_room" for b in buttons)

    with client.stream("POST", "/agent/process", json={
        "session_id": session_id,
        "user_message": "book_room",
        "message_type": "callback",
    }) as response:
        second_events = _parse_ndjson(response.read())

    full_text = "".join(e["content"] for e in second_events if e["type"] == "text_chunk")
    # StubGraph — заглушка-эхо, реагирует на content сообщения пользователя;
    # раз callback резолвится в текст кнопки, ожидаем увидеть текст кнопки в эхе, а не сырой callback_data.
    assert "book_room" not in full_text