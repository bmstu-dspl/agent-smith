import pytest

from memory.procedural_store import ProceduralStore

pytestmark = pytest.mark.asyncio


async def test_set_and_get_setting(procedural_store: ProceduralStore):
    await procedural_store.set_setting("some_config", {"key": "value"})
    result = await procedural_store.get_setting("some_config")
    assert result == {"key": "value"}


async def test_get_setting_returns_none_when_missing(procedural_store: ProceduralStore):
    result = await procedural_store.get_setting("does_not_exist")
    assert result is None


async def test_set_setting_overwrites_existing(procedural_store: ProceduralStore):
    """ON CONFLICT DO UPDATE — повторная запись должна заменять значение, не создавать дубль."""
    await procedural_store.set_setting("mcp_url", {"url": "http://old"})
    await procedural_store.set_setting("mcp_url", {"url": "http://new"})

    result = await procedural_store.get_setting("mcp_url")
    all_settings = await procedural_store.get_all_settings()

    assert result == {"url": "http://new"}
    assert len(all_settings) == 1