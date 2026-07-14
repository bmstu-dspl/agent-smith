from langchain_core.tools import BaseTool

from booking_plugin import get_booking_management_info, search_available_rooms


class BookingToolProvider:
    """Реализация ToolProvider для плагина бронирования TravelLine.

    Соответствует контракту:
        class ToolProvider(Protocol):
            def get_tools(self) -> list[BaseTool]: ...
    """

    def get_tools(self) -> list[BaseTool]:
        return [search_available_rooms, get_booking_management_info]