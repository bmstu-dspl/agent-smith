from mcp.server.fastmcp import FastMCP
import random

mcp = FastMCP("Demo Booking Server")

# uv run python mcp_registry_client.py - запуск

# Проверить наличие свободных номеров на указанные даты.
@mcp.tool()
def check_room_availability(check_in: str, check_out: str, guests: int) -> str:
    """Проверить наличие свободных номеров на указанные даты.

    Args:
        check_in: дата заезда (ДД-ММ-ГГГГ)
        check_out: дата выезда (ДД-ММ-ГГГГ)
        guests: кол-во гостей
    """
    # запрос-заглушка
    return f"Найден номер 203, гостей: {guests}, даты: {check_in} - {check_out}, 5000 руб/ночь"

# Создать бронирование на указанный номер и даты.
@mcp.tool()
def create_booking(check_in: str, check_out: str, guests: int, room_number: int) -> str:
    """Создать бронирование на указанный номер и даты.

    Args:
        check_in: дата заезда в формате ДД-ММ-ГГГГ
        check_out: дата выезда в формате ДД-ММ-ГГГГ
        guests: количество гостей
        room_number: номер комнаты (взять из результата check_room_availability)
    """
    booking_id = f"BK-{random.randint(1000, 9999)}"
    return f"Бронирование создано: {booking_id}, номер {room_number}, {check_in} — {check_out}, {guests} гостей"

# Отменить существующее бронирование по его идентификатору.
@mcp.tool()
def cancel_booking(booking_id: str) -> str:
    """Отменить существующее бронирование по его идентификатору.

    Args:
        booking_id: идентификатор брони, полученный при создании (например, BK-1234)
    """
    return f"Бронирование {booking_id} отменено"



if __name__ == "__main__":
    mcp.run()