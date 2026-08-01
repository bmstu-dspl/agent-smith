from datetime import datetime, timezone

import pytest

from ai_core.tools import ToolRegistry, create_current_datetime_tool


@pytest.mark.asyncio
async def test_current_datetime_reports_utc_and_configured_primary_timezone() -> None:
    fixed_now = datetime(2026, 12, 31, 21, 30, tzinfo=timezone.utc)
    current_datetime = create_current_datetime_tool(
        "Europe/Moscow",
        clock=lambda: fixed_now,
    )

    result = await current_datetime.ainvoke({})

    assert result == {
        "utc_datetime": "2026-12-31T21:30:00+00:00",
        "primary_datetime": "2027-01-01T00:30:00+03:00",
        "primary_date": "2027-01-01",
        "primary_time": "00:30:00",
        "primary_timezone": "Europe/Moscow",
    }


def test_core_registry_exposes_current_datetime_with_primary_timezone() -> None:
    registry = ToolRegistry(primary_timezone="America/New_York")

    tools = {registered.name: registered for registered in registry.get_tools()}

    assert "get_current_datetime" in tools
    assert "configured primary timezone" in tools["get_current_datetime"].description
