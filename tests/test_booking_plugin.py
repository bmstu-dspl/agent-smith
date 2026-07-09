import json
import pytest
import booking_plugin as booking


@pytest.fixture(autouse=True)
def init_plugin(monkeypatch):
    """Перед каждым тестом настраиваем обязательную переменную и инициализируем плагин."""
    monkeypatch.setenv("HOTEL_BOOKING_SITE_URL", "https://example-hotel.ru/booking")
    booking.initialize_plugin()


def test_search_available_rooms_returns_list(monkeypatch):
    monkeypatch.setattr(booking.random, "random", lambda: 0.9)  # гарантированно "есть номера"

    result = json.loads(
        booking.search_available_rooms.invoke(
            {"check_in": "20-07-2026", "check_out": "23-07-2026", "guests": 2}
        )
    )
    assert result["ok"] is True
    assert isinstance(result["data"], list)
    assert len(result["data"]) > 0
    assert "room_type" in result["data"][0]


def test_search_available_rooms_no_availability(monkeypatch):
    monkeypatch.setattr(booking.random, "random", lambda: 0.0)  # гарантированно "мест нет"

    result = json.loads(
        booking.search_available_rooms.invoke(
            {"check_in": "20-07-2026", "check_out": "23-07-2026", "guests": 2}
        )
    )
    assert result["ok"] is False
    assert result["error_type"] == "booking_unavailable"


def test_search_available_rooms_checkout_before_checkin():
    result = json.loads(
        booking.search_available_rooms.invoke(
            {"check_in": "23-07-2026", "check_out": "20-07-2026", "guests": 2}
        )
    )
    assert result["ok"] is False
    assert result["error_type"] == "validation_error"


def test_search_available_rooms_invalid_guests():
    result = json.loads(
        booking.search_available_rooms.invoke(
            {"check_in": "20-07-2026", "check_out": "23-07-2026", "guests": 0}
        )
    )
    assert result["ok"] is False
    assert result["error_type"] == "validation_error"


def test_generate_booking_link_success():
    result = json.loads(
        booking.generate_booking_link.invoke(
            {
                "room_type": "1270",
                "offer_id": "439000",
                "check_in": "20-07-2026",
                "check_out": "23-07-2026",
            }
        )
    )
    assert result["ok"] is True
    link = result["data"]
    assert link.startswith("https://example-hotel.ru/booking?")
    assert "be-offer=439000" in link
    assert "room-type=1270" in link
    assert "date=2026-07-20" in link
    assert "nights=3" in link


def test_generate_booking_link_same_day_invalid():
    result = json.loads(
        booking.generate_booking_link.invoke(
            {
                "room_type": "1270",
                "offer_id": "439000",
                "check_in": "20-07-2026",
                "check_out": "20-07-2026",
            }
        )
    )
    assert result["ok"] is False
    assert result["error_type"] == "validation_error"


def test_get_booking_management_info_mentions_access_code():
    result = json.loads(booking.get_booking_management_info.invoke({}))
    assert result["ok"] is True
    assert "код доступа" in result["data"]


def test_initialize_plugin_fails_without_env(monkeypatch):
    monkeypatch.delenv("HOTEL_BOOKING_SITE_URL", raising=False)
    with pytest.raises(RuntimeError):
        booking.initialize_plugin()