from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import BufferedInputFile

from app.telegram_formatting import (
    AgentResponseStream,
    RichMediaResolver,
    markdown_to_rich_html,
    markdown_to_stream_text,
    markdown_to_telegram_html,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str) -> None:
        self.values[key] = value.encode()


class FakeResponse:
    def __init__(self, content: bytes = b"jpeg-data") -> None:
        self.content = content
        self.headers = {
            "content-type": "image/jpeg",
            "content-length": str(len(content)),
        }

    def raise_for_status(self) -> None:
        return None


class FakeHttpClient:
    def __init__(self) -> None:
        self.urls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, url: str) -> FakeResponse:
        self.urls.append(url)
        return FakeResponse()


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


def test_markdown_to_rich_html_preserves_generated_media_and_escapes_links() -> None:
    markdown = (
        '<tg-slideshow>\n<img src="tg://photo?id=photo_1"/>\n</tg-slideshow>\n'
        "**Стандартный номер**\n"
        "[Забронировать](https://hotel.example/booking?room=42&rate=7)"
    )

    assert markdown_to_rich_html(markdown) == (
        '<tg-slideshow>\n<img src="tg://photo?id=photo_1"/>\n</tg-slideshow>\n'
        "<b>Стандартный номер</b>\n"
        '<a href="https://hotel.example/booking?room=42&amp;rate=7">'
        "Забронировать</a>"
    )


@pytest.mark.asyncio
async def test_agent_response_stream_uses_native_plain_draft() -> None:
    bot = AsyncMock()
    stream = AgentResponseStream(
        bot=bot,
        chat_id=42,
        draft_id=73,
        min_update_interval_seconds=0,
    )

    await stream.start()
    await stream.update(
        "На период есть номера:\n\n"
        "<tg-slideshow>\n\n![](https://hotel.example/room.jpg)"
    )

    assert bot.send_message_draft.await_args_list[0].kwargs == {
        "chat_id": 42,
        "draft_id": 73,
        "message_thread_id": None,
        "text": "",
        "parse_mode": None,
    }
    assert bot.send_message_draft.await_args_list[1].kwargs == {
        "chat_id": 42,
        "draft_id": 73,
        "message_thread_id": None,
        "text": "На период есть номера:",
        "parse_mode": None,
    }


@pytest.mark.asyncio
async def test_rich_media_resolver_downloads_http_images_for_multipart_upload() -> None:
    redis = FakeRedis()
    http = FakeHttpClient()
    resolver = RichMediaResolver(
        redis=redis,
        http_client_factory=lambda **_kwargs: http,
    )
    url = "https://partner-static.tlintegration.com/image-id"

    prepared = await resolver.prepare(f"![]({url})\n**Номер**")

    assert prepared.rich_message.markdown is None
    assert prepared.rich_message.html == '<img src="tg://photo?id=photo_1"/>\n<b>Номер</b>'
    media = prepared.rich_message.media[0].media.media
    assert isinstance(media, BufferedInputFile)
    assert media.data == b"jpeg-data"
    assert prepared.source_urls == [url]
    assert http.urls == [url]


@pytest.mark.asyncio
async def test_rich_message_decodes_html_entities_inside_booking_url() -> None:
    resolver = RichMediaResolver(redis=FakeRedis())
    prepared = await resolver.prepare(
        "[Забронировать](https://hotel.example/booking?room=42&amp;rate=7)"
    )

    assert prepared.rich_message.markdown is None
    assert prepared.rich_message.html == (
        '<a href="https://hotel.example/booking?room=42&amp;rate=7">'
        "Забронировать</a>"
    )


def test_html_fallback_does_not_double_escape_booking_url_entities() -> None:
    rendered = markdown_to_telegram_html(
        "[Забронировать](https://hotel.example/booking?room=42&amp;rate=7)"
    )

    assert rendered == (
        '<a href="https://hotel.example/booking?room=42&amp;rate=7">'
        "Забронировать</a>"
    )


@pytest.mark.asyncio
async def test_rich_media_resolver_reuses_and_records_telegram_file_ids() -> None:
    redis = FakeRedis()
    http = FakeHttpClient()
    resolver = RichMediaResolver(
        redis=redis,
        http_client_factory=lambda **_kwargs: http,
    )
    url = "https://partner-static.tlintegration.com/image-id"
    redis.values[resolver.cache_key(url)] = b"telegram-file-id"

    prepared = await resolver.prepare(f"![]({url})")

    assert prepared.rich_message.media[0].media.media == "telegram-file-id"
    assert http.urls == []

    sent = SimpleNamespace(
        rich_message=SimpleNamespace(
            blocks=[
                SimpleNamespace(
                    type="slideshow",
                    blocks=[
                        SimpleNamespace(
                            type="photo",
                            photo=[SimpleNamespace(file_id="new-file-id")],
                        )
                    ],
                )
            ]
        )
    )
    await resolver.remember(prepared, sent)

    assert redis.values[resolver.cache_key(url)] == b"new-file-id"


@pytest.mark.asyncio
async def test_rich_media_resolver_does_not_fetch_untrusted_urls() -> None:
    http = FakeHttpClient()
    resolver = RichMediaResolver(
        redis=FakeRedis(),
        http_client_factory=lambda **_kwargs: http,
    )

    prepared = await resolver.prepare(
        "<tg-slideshow>\n![](http://169.254.169.254/latest/meta-data)\n"
        "</tg-slideshow>\n**Номер**"
    )

    assert prepared.rich_message.markdown is None
    assert prepared.rich_message.html == "<b>Номер</b>"
    assert prepared.rich_message.media is None
    assert http.urls == []


@pytest.mark.asyncio
async def test_agent_response_stream_sends_persistent_rich_message_after_draft() -> None:
    bot = AsyncMock()
    resolver = AsyncMock()
    prepared = SimpleNamespace(
        rich_message=SimpleNamespace(markdown="**Номер**", media=None),
        source_urls=[],
    )
    resolver.prepare.return_value = prepared
    sent = SimpleNamespace(rich_message=SimpleNamespace(blocks=[]))
    bot.send_rich_message.return_value = sent
    stream = AgentResponseStream(
        bot=bot,
        chat_id=42,
        draft_id=73,
        media_resolver=resolver,
        min_update_interval_seconds=0,
    )
    reply_markup = object()

    await stream.update("Черновик")
    await stream.finalize("**Номер**", reply_markup=reply_markup)

    bot.send_message_draft.assert_awaited_once()
    bot.send_rich_message.assert_awaited_once_with(
        chat_id=42,
        message_thread_id=None,
        rich_message=prepared.rich_message,
        reply_markup=reply_markup,
    )
    resolver.remember.assert_awaited_once_with(prepared, sent)


@pytest.mark.asyncio
async def test_rich_final_falls_back_to_html_without_link_preview() -> None:
    bot = AsyncMock()
    bot.send_rich_message.side_effect = TelegramBadRequest(
        method=AsyncMock(),
        message="rich final unsupported",
    )
    resolver = AsyncMock()
    resolver.prepare.return_value = SimpleNamespace(
        rich_message=SimpleNamespace(markdown="**Номер**", media=None),
        source_urls=[],
    )
    stream = AgentResponseStream(
        bot=bot,
        chat_id=42,
        draft_id=73,
        media_resolver=resolver,
        min_update_interval_seconds=0,
    )

    await stream.finalize(
        "<tg-slideshow>\n![](https://hotel.example/room.jpg)\n</tg-slideshow>\n"
        "**Номер** — *10 000 ₽*"
    )

    fallback = bot.send_message.await_args
    assert fallback.kwargs["chat_id"] == 42
    assert fallback.kwargs["text"] == "<b>Номер</b> — <i>10 000 ₽</i>"
    assert fallback.kwargs["parse_mode"] == "HTML"
    assert fallback.kwargs["link_preview_options"].is_disabled is True


@pytest.mark.asyncio
async def test_rejected_native_draft_does_not_abort_final_response() -> None:
    bot = AsyncMock()
    bot.send_message_draft.side_effect = TelegramBadRequest(
        method=AsyncMock(), message="draft unsupported"
    )
    resolver = AsyncMock()
    resolver.prepare.return_value = SimpleNamespace(
        rich_message=SimpleNamespace(markdown="Готовый ответ", media=None),
        source_urls=[],
    )
    bot.send_rich_message.return_value = SimpleNamespace(
        rich_message=SimpleNamespace(blocks=[])
    )
    stream = AgentResponseStream(
        bot=bot,
        chat_id=42,
        draft_id=73,
        media_resolver=resolver,
        min_update_interval_seconds=0,
    )

    await stream.update("Черновик")
    await stream.finalize("Готовый ответ")

    bot.send_rich_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_temporary_native_draft_failure_is_retried() -> None:
    bot = AsyncMock()
    bot.send_message_draft.side_effect = [
        TelegramRetryAfter(method=AsyncMock(), message="retry later", retry_after=1),
        None,
    ]
    stream = AgentResponseStream(
        bot=bot,
        chat_id=42,
        draft_id=73,
        min_update_interval_seconds=0,
    )

    await stream.update("Черновик")
    await stream.update("Обновлённый черновик")

    assert bot.send_message_draft.await_count == 2


def test_markdown_to_stream_text_hides_media_and_formatting() -> None:
    assert markdown_to_stream_text(
        "Варианты:\n<tg-slideshow>\n![](https://hotel.example/1.jpg)\n"
        "</tg-slideshow>\n**Стандарт**\n*10 000 ₽*\n"
        "[Забронировать](https://hotel.example/book)"
    ) == "Варианты:\n\nСтандарт\n10 000 ₽\nЗабронировать"
