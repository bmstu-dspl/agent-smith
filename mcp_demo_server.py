import random
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from errors import BookingUnavailableError, ValidationError, safe_tool

mcp = FastMCP("Demo Booking Server")

# uv run python mcp_registry_client.py - запуск

def _parse_date(value: str, field_name: str) -> datetime:
    try:
        return datetime.strptime(value, "%d-%m-%Y")
    except ValueError:
        raise ValidationError(
            f"Некорректный формат даты в поле '{field_name}': {value}. Ожидается ДД-ММ-ГГГГ"
        )


def _validate_dates(check_in: str, check_out: str) -> None:
    d_in = _parse_date(check_in, "check_in")
    d_out = _parse_date(check_out, "check_out")
    if d_out <= d_in:
        raise ValidationError("Дата выезда должна быть позже даты заезда")
    if d_in.date() < datetime.now().date():
        raise ValidationError("Дата заезда не может быть в прошлом")


@mcp.tool()
@safe_tool
def check_room_availability(check_in: str, check_out: str, guests: int) -> str:
    """Проверить наличие свободных номеров на указанные даты.

    Args:
        check_in: дата заезда в формате ДД-ММ-ГГГГ
        check_out: дата выезда в формате ДД-ММ-ГГГГ
        guests: количество гостей
    """
    _validate_dates(check_in, check_out)
    if guests <= 0:
        raise ValidationError("Количество гостей должно быть больше 0")

    # Заглушка: имитируем, что иногда номеров действительно нет
    if random.random() < 0.2:
        raise BookingUnavailableError("На выбранные даты свободных номеров нет")

    return f"Найден номер 203, {guests} гостей, {check_in} - {check_out}, 5000 ₽/ночь"


@mcp.tool()
@safe_tool
def create_booking(check_in: str, check_out: str, guests: int, room_number: int) -> str:
    """Создать бронирование на указанный номер и даты.

    Args:
        check_in: дата заезда в формате ДД-ММ-ГГГГ
        check_out: дата выезда в формате ДД-ММ-ГГГГ
        guests: количество гостей
        room_number: номер комнаты (взять из check_room_availability)
    """
    _validate_dates(check_in, check_out)
    if guests <= 0:
        raise ValidationError("Количество гостей должно быть более 0")

    booking_id = f"BK-{random.randint(1000, 9999)}"
    return f"Бронирование создано: {booking_id}, номер {room_number}, {check_in} - {check_out}, {guests} гостей"


@mcp.tool()
@safe_tool
def cancel_booking(booking_id: str) -> str:
    """Отменить существующее бронирование по его идентификатору.

    Args:
        booking_id: идентификатор брони (например, BK-1234)
    """
    if not booking_id.startswith("BK-"):
        raise ValidationError("Некорректный формат идентификатора брони, ожидается вид BK-1234")

    return f"Бронирование {booking_id} отменено"


if __name__ == "__main__":
    mcp.run()