import json

import pytest

import booking_plugin as booking

# uv run pytest -v

FAKE_ROOM_STAY = {
    "roomType": {"id": "386695"},
    "ratePlan": {"id": "899279"},
    "fullPlacementsName": "2 взрослых на основных местах.",
    "mealPlanCode": "RoomOnly",
    "total": {"priceBeforeTax": 20070.0, "taxAmount": 0},
    "currencyCode": "RUB",
    "cancellationPolicy": {
        "freeCancellationDeadlineLocal": "2026-10-09T13:59",
        "penaltyAmount": 7290,
    },
    "availableDiscounts": [{"reason": "LoyaltyDiscount", "amount": 603.0}],
    "availability": 3,
    "guarantees": [{"paymentMethodCode": "BankCard"}],
    "bookingFormLink": "https://example-hotel.ru/booking?tl-room=386695&tl-offer=899279",
}


@pytest.fixture(autouse=True)
def init_plugin(monkeypatch):
    """Перед каждым тестом настраиваем обязательные переменные и инициализируем плагин."""
    monkeypatch.setenv("TRAVELLINE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("TRAVELLINE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("TRAVELLINE_PROPERTY_ID", "0000")
    booking.initialize_plugin()


async def test_search_available_rooms_returns_formatted_list(monkeypatch):
    async def fake_search(check_in, check_out, adults, child_ages=None):
        return [FAKE_ROOM_STAY]

    monkeypatch.setattr(booking.travelline_client, "search_room_stays", fake_search)

    result = json.loads(
        await booking.search_available_rooms.ainvoke(
            {"check_in": "20-07-2026", "check_out": "23-07-2026", "adults": 2}
        )
    )
    assert result["ok"] is True
    room = result["data"][0]
    assert room["room_id"] == "386695"
    assert room["rate_plan_id"] == "899279"
    assert room["price"] == 20070.0
    assert room["booking_link"].startswith("https://example-hotel.ru/booking?")
    assert room["penalty_amount"] == 7290
    assert room["price_with_loyalty_discount"] == 20070.0 - 603.0
    assert room["rooms_left"] == 3
    assert room["payment_method"] == "BankCard"
    assert room["tax_amount"] == 0


async def test_search_available_rooms_no_availability(monkeypatch):
    async def fake_search(check_in, check_out, adults, child_ages=None):
        return []

    monkeypatch.setattr(booking.travelline_client, "search_room_stays", fake_search)

    result = json.loads(
        await booking.search_available_rooms.ainvoke(
            {"check_in": "20-07-2026", "check_out": "23-07-2026", "adults": 2}
        )
    )
    assert result["ok"] is False
    assert result["error_type"] == "booking_unavailable"


async def test_search_available_rooms_checkout_before_checkin():
    result = json.loads(
        await booking.search_available_rooms.ainvoke(
            {"check_in": "23-07-2026", "check_out": "20-07-2026", "adults": 2}
        )
    )
    assert result["ok"] is False
    assert result["error_type"] == "validation_error"


async def test_search_available_rooms_invalid_adults():
    result = json.loads(
        await booking.search_available_rooms.ainvoke(
            {"check_in": "20-07-2026", "check_out": "23-07-2026", "adults": 0}
        )
    )
    assert result["ok"] is False
    assert result["error_type"] == "validation_error"

async def test_search_available_rooms_invalid_child_age():
    result = json.loads(
        await booking.search_available_rooms.ainvoke(
            {
                "check_in": "20-07-2026",
                "check_out": "23-07-2026",
                "adults": 2,
                "child_ages": [14],
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
    monkeypatch.delenv("TRAVELLINE_CLIENT_ID", raising=False)
    with pytest.raises(RuntimeError):
        booking.initialize_plugin()


async def test_search_available_rooms_no_guarantees(monkeypatch):
    room_stay_no_guarantees = {**FAKE_ROOM_STAY, "guarantees": []}

    async def fake_search(check_in, check_out, adults, child_ages=None):
        return [room_stay_no_guarantees]

    monkeypatch.setattr(booking.travelline_client, "search_room_stays", fake_search)

    result = json.loads(
        await booking.search_available_rooms.ainvoke(
            {"check_in": "20-07-2026", "check_out": "23-07-2026", "adults": 2}
        )
    )
    assert result["data"][0]["payment_method"] is None


async def test_search_available_rooms_no_loyalty_discount(monkeypatch):
    room_stay_no_discount = {**FAKE_ROOM_STAY, "availableDiscounts": []}

    async def fake_search(check_in, check_out, adults, child_ages=None):
        return [room_stay_no_discount]

    monkeypatch.setattr(booking.travelline_client, "search_room_stays", fake_search)

    result = json.loads(
        await booking.search_available_rooms.ainvoke(
            {"check_in": "20-07-2026", "check_out": "23-07-2026", "adults": 2}
        )
    )
    assert result["data"][0]["price_with_loyalty_discount"] is None