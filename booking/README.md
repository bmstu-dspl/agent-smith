# Booking Plugin (TravelLine)

Плагин бронирования отеля через TravelLine Search API для ИИ-агента.

## Инструменты

- `search_available_rooms` - поиск доступных номеров
- `get_booking_management_info` - инструкция по самостоятельному управлению бронью

## Подключение к агенту

```python
from booking.provider import BookingToolProvider

tools = BookingToolProvider().get_tools()
```

## Переменные окружения

- `TRAVELLINE_CLIENT_ID`
- `TRAVELLINE_CLIENT_SECRET`
- `TRAVELLINE_PROPERTY_ID`