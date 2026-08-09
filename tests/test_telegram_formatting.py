from unittest.mock import AsyncMock

import pytest

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

from app.telegram_formatting import (
    AgentResponseStream,
    markdown_to_rich_message,
    markdown_to_stream_text,
    markdown_to_telegram_html,
    send_agent_response,
)


def test_markdown_to_telegram_html_supports_room_result_format() -> None:
    markdown = (
        "**Стандартный номер**\n"
        "*12 500 ₽ без завтрака; 14 000 ₽ с завтраком*\n"
        "Подходит для пары: двуспальная кровать и бесплатная отмена.\n"
        "[Забронировать](https://hotel.example/booking?room=42&rate=7)"
    )

    assert markdown_to_telegram_html(markdown) == (
        "<b>Стандартный номер</b>\n"
        "<i>12 500 ₽ без завтрака; 14 000 ₽ с завтраком</i>\n"
        "Подходит для пары: двуспальная кровать и бесплатная отмена.\n"
        '<a href="https://hotel.example/booking?room=42&amp;rate=7">'
        "Забронировать</a>"
    )


def test_markdown_to_telegram_html_escapes_untrusted_text_and_unsafe_links() -> None:
    markdown = "<script>alert(1)</script> [Открыть](javascript:alert(1))"

    assert markdown_to_telegram_html(markdown) == (
        "&lt;script&gt;alert(1)&lt;/script&gt; "
        "[Открыть](javascript:alert(1))"
    )


@pytest.mark.asyncio
async def test_agent_response_stream_edits_plain_placeholder_without_rich_media() -> None:
    placeholder = AsyncMock()
    placeholder.message_id = 73
    bot = AsyncMock()
    stream = AgentResponseStream(
        placeholder,
        bot=bot,
        chat_id=42,
        min_update_interval_seconds=0,
    )

    await stream.update(
        "На период есть номера:\n\n"
        "<tg-slideshow>\n\n![](https://hotel.example/room.jpg)"
    )

    placeholder.edit_text.assert_awaited_once_with(
        "На период есть номера:▌",
        parse_mode=None,
    )
    bot.send_rich_message_draft.assert_not_awaited()
    placeholder.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_response_stream_promotes_placeholder_to_rich_message_with_typed_media() -> None:
    placeholder = AsyncMock()
    placeholder.message_id = 73
    bot = AsyncMock()
    stream = AgentResponseStream(
        placeholder,
        bot=bot,
        chat_id=42,
        min_update_interval_seconds=0,
    )
    reply_markup = object()

    markdown = (
        "<tg-slideshow>\n\n"
        "![](https://hotel.example/room-1.jpg)\n"
        "![](https://hotel.example/room-2.jpg)\n\n"
        "</tg-slideshow>\n\n"
        "**Номер**"
    )
    await stream.update(markdown)
    await stream.finalize(markdown, reply_markup=reply_markup)

    final = placeholder.edit_text.await_args_list[-1]
    rich_message = final.kwargs["rich_message"]
    assert rich_message.markdown == (
        "<tg-slideshow>\n\n"
        "![](tg://photo?id=photo_1)\n"
        "![](tg://photo?id=photo_2)\n\n"
        "</tg-slideshow>\n\n"
        "**Номер**"
    )
    assert [item.id for item in rich_message.media] == ["photo_1", "photo_2"]
    assert [item.media.media for item in rich_message.media] == [
        "https://hotel.example/room-1.jpg",
        "https://hotel.example/room-2.jpg",
    ]
    assert final.kwargs["reply_markup"] is reply_markup
    bot.send_rich_message.assert_not_awaited()
    placeholder.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_rich_final_falls_back_to_clean_html_without_media_markup() -> None:
    placeholder = AsyncMock()
    placeholder.message_id = 73
    bot = AsyncMock()
    placeholder.edit_text.side_effect = [
        TelegramBadRequest(method=AsyncMock(), message="rich final unsupported"),
        None,
    ]
    stream = AgentResponseStream(
        placeholder,
        bot=bot,
        chat_id=42,
        min_update_interval_seconds=0,
    )

    await stream.finalize(
        "<tg-slideshow>\n![](https://hotel.example/room.jpg)\n</tg-slideshow>\n"
        "**Номер** — *10 000 ₽*"
    )

    fallback = placeholder.edit_text.await_args_list[1]
    assert fallback.args == ("<b>Номер</b> — <i>10 000 ₽</i>",)
    assert fallback.kwargs == {"parse_mode": "HTML", "reply_markup": None}


@pytest.mark.asyncio
async def test_agent_response_stream_uses_plain_edits_before_rich_final() -> None:
    placeholder = AsyncMock()
    placeholder.message_id = 73
    bot = AsyncMock()
    stream = AgentResponseStream(
        placeholder,
        bot=bot,
        chat_id=42,
        min_update_interval_seconds=0,
    )

    await stream.update("Черновик")
    await stream.finalize("**Номер**")

    draft = placeholder.edit_text.await_args_list[0]
    assert draft.args == ("Черновик▌",)
    assert draft.kwargs["parse_mode"] is None
    final = placeholder.edit_text.await_args_list[1]
    assert final.kwargs["text"] is None
    assert final.kwargs["rich_message"].markdown == "**Номер**"
    bot.send_rich_message_draft.assert_not_awaited()


@pytest.mark.asyncio
async def test_rejected_plain_streaming_edit_does_not_abort_final_response() -> None:
    placeholder = AsyncMock()
    placeholder.message_id = 73
    placeholder.edit_text.side_effect = [
        TelegramBadRequest(method=AsyncMock(), message="invalid partial text"),
        None,
    ]
    bot = AsyncMock()
    stream = AgentResponseStream(
        placeholder,
        bot=bot,
        chat_id=42,
        min_update_interval_seconds=0,
    )

    await stream.update("<")
    await stream.finalize("Готовый ответ")

    assert placeholder.edit_text.await_count == 2


@pytest.mark.asyncio
async def test_temporary_plain_edit_failure_does_not_abort_stream() -> None:
    placeholder = AsyncMock()
    placeholder.message_id = 73
    placeholder.edit_text.side_effect = [
        TelegramRetryAfter(method=AsyncMock(), message="retry later", retry_after=1),
        None,
    ]
    bot = AsyncMock()
    stream = AgentResponseStream(
        placeholder,
        bot=bot,
        chat_id=42,
        min_update_interval_seconds=0,
    )

    await stream.update("Черновик")
    await stream.update("**Номер**")

    assert placeholder.edit_text.await_count == 2
    bot.send_rich_message_draft.assert_not_awaited()
    placeholder.delete.assert_not_awaited()


def test_markdown_to_rich_message_maps_http_images_to_typed_tg_media() -> None:
    rich_message = markdown_to_rich_message(
        "![](https://partner-static.example/image-id)\n**Номер**"
    )

    assert rich_message.markdown == "![](tg://photo?id=photo_1)\n**Номер**"
    assert rich_message.media[0].id == "photo_1"
    assert rich_message.media[0].media.media == (
        "https://partner-static.example/image-id"
    )


def test_markdown_to_stream_text_hides_media_and_formatting() -> None:
    assert markdown_to_stream_text(
        "Варианты:\n<tg-slideshow>\n![](https://hotel.example/1.jpg)\n"
        "</tg-slideshow>\n**Стандарт**\n*10 000 ₽*\n"
        "[Забронировать](https://hotel.example/book)"
    ) == "Варианты:\n\nСтандарт\n10 000 ₽\nЗабронировать"


@pytest.mark.asyncio
async def test_send_agent_response_uses_native_rich_markdown() -> None:
    placeholder = AsyncMock()
    bot = AsyncMock()
    reply_markup = object()

    await send_agent_response(
        placeholder,
        bot=bot,
        chat_id=42,
        markdown=(markdown := "**Номер** — *10 000 ₽*"),
        reply_markup=reply_markup,
    )

    call = bot.send_rich_message.await_args
    assert call.kwargs["chat_id"] == 42
    assert call.kwargs["rich_message"].markdown == markdown
    assert call.kwargs["reply_markup"] is reply_markup
    placeholder.delete.assert_awaited_once_with()
    placeholder.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_agent_response_falls_back_to_safe_telegram_html() -> None:
    placeholder = AsyncMock()
    bot = AsyncMock()
    bot.send_rich_message.side_effect = TelegramBadRequest(
        method=AsyncMock(),
        message="rich messages unsupported",
    )

    await send_agent_response(
        placeholder,
        bot=bot,
        chat_id=42,
        markdown="**Номер** — *10 000 ₽*",
    )

    placeholder.edit_text.assert_awaited_once_with(
        "<b>Номер</b> — <i>10 000 ₽</i>",
        parse_mode="HTML",
        reply_markup=None,
    )
    placeholder.delete.assert_not_awaited()
