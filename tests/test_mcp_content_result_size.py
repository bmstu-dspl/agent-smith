from types import SimpleNamespace

from mcp_registry.client import _extract_result_text


def test_mcp_adapter_preserves_rich_room_details_larger_than_legacy_limit() -> None:
    content = '{"image_urls":[' + ",".join(
        f'"https://cdn.example/rooms/{index}/large-photo.jpg"'
        for index in range(180)
    ) + "]}"
    result = SimpleNamespace(content=[SimpleNamespace(text=content)])

    extracted = _extract_result_text(result)

    assert content in extracted
    assert not extracted.endswith("…")
