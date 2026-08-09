from unittest.mock import AsyncMock

import pytest

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

from app.telegram_formatting import (
    AgentResponseStream,
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
async def test_agent_response_stream_uses_native_rich_draft_and_removes_placeholder() -> None:
    placeholder = AsyncMock()
    placeholder.message_id = 73
    bot = AsyncMock()
    stream = AgentResponseStream(
        placeholder,
        bot=bot,
        chat_id=42,
        min_update_interval_seconds=0,
    )

    await stream.update("**Номер**")

    call = bot.send_rich_message_draft.await_args
    assert call.kwargs["chat_id"] == 42
    assert call.kwargs["draft_id"] == 73
    assert call.kwargs["rich_message"].markdown == "**Номер**"
    placeholder.delete.assert_awaited_once_with()
    placeholder.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_response_stream_persists_completed_rich_draft() -> None:
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

    await stream.update("**Но")
    await stream.finalize("**Номер**", reply_markup=reply_markup)

    call = bot.send_rich_message.await_args
    assert call.kwargs["chat_id"] == 42
    assert call.kwargs["rich_message"].markdown == "**Номер**"
    assert call.kwargs["reply_markup"] is reply_markup
    placeholder.delete.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_completed_draft_falls_back_to_regular_html_message() -> None:
    placeholder = AsyncMock()
    placeholder.message_id = 73
    bot = AsyncMock()
    bot.send_rich_message.side_effect = TelegramBadRequest(
        method=AsyncMock(),
        message="rich final unsupported",
    )
    stream = AgentResponseStream(
        placeholder,
        bot=bot,
        chat_id=42,
        min_update_interval_seconds=0,
    )

    await stream.update("**Но")
    await stream.finalize("**Номер** — *10 000 ₽*")

    bot.send_message.assert_awaited_once_with(
        chat_id=42,
        text="<b>Номер</b> — <i>10 000 ₽</i>",
        parse_mode="HTML",
        reply_markup=None,
    )


@pytest.mark.asyncio
async def test_agent_response_stream_falls_back_to_editing_placeholder() -> None:
    placeholder = AsyncMock()
    placeholder.message_id = 73
    bot = AsyncMock()
    bot.send_rich_message_draft.side_effect = TelegramBadRequest(
        method=AsyncMock(),
        message="draft unsupported",
    )
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
    bot.send_rich_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_rejected_plain_streaming_edit_does_not_abort_final_response() -> None:
    placeholder = AsyncMock()
    placeholder.message_id = 73
    placeholder.edit_text.side_effect = [
        TelegramBadRequest(method=AsyncMock(), message="invalid partial text"),
        None,
    ]
    bot = AsyncMock()
    bot.send_rich_message_draft.side_effect = TelegramBadRequest(
        method=AsyncMock(),
        message="invalid partial rich markdown",
    )
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
async def test_temporary_draft_failure_does_not_abort_or_disable_rich_stream() -> None:
    placeholder = AsyncMock()
    placeholder.message_id = 73
    bot = AsyncMock()
    bot.send_rich_message_draft.side_effect = [
        TelegramRetryAfter(method=AsyncMock(), message="retry later", retry_after=1),
        None,
    ]
    stream = AgentResponseStream(
        placeholder,
        bot=bot,
        chat_id=42,
        min_update_interval_seconds=0,
    )

    await stream.update("Черновик")
    await stream.update("**Номер**")

    assert bot.send_rich_message_draft.await_count == 2
    placeholder.delete.assert_awaited_once_with()
    placeholder.edit_text.assert_not_awaited()


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
