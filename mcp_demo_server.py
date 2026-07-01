from mcp.server.fastmcp import FastMCP

# Создаем сервер
mcp = FastMCP("Demo Booking Server")


@mcp.tool()
def check_room_availability(check_in: str, check_out: str, guests: int) -> str:
    """Проверить наличие свободных номеров на указанные даты.

    Args:
        check_in: дата заезда (ДД-ММ-ГГГГ)
        check_out: дата выезда (ДД-ММ-ГГГГ)
        guests: кол-во гостей
    """
    # Пока запрос-заглушка
    return f"Найден номер 203, гостей: {guests}, даты: {check_in} - {check_out}, 5000 руб/ночь"


if __name__ == "__main__":
    mcp.run()