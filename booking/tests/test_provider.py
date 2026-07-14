from langchain_core.tools import BaseTool

from provider import BookingToolProvider


def test_get_tools_returns_list_of_base_tools():
    provider = BookingToolProvider()
    tools = provider.get_tools()

    assert isinstance(tools, list)
    assert len(tools) == 2
    for tool in tools:
        assert isinstance(tool, BaseTool)


def test_get_tools_contains_expected_names():
    provider = BookingToolProvider()
    names = {tool.name for tool in provider.get_tools()}

    assert names == {"search_available_rooms", "get_booking_management_info"}
    