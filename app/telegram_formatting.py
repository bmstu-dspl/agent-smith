"""Safe rendering of the small Markdown subset used in agent replies."""

from __future__ import annotations

import html
import logging
import re
import time
from typing import Any

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import InputMediaPhoto, InputRichMessage, InputRichMessageMedia


logger = logging.getLogger(__name__)

_INLINE_MARKDOWN = re.compile(
    r"\[(?P<label>[^\]\n]+)\]\((?P<url>https?://[^\s)]+)\)"
    r"|\*\*(?P<bold>[^*\n]+)\*\*"
    r"|\*(?P<italic>[^*\n]+)\*"
)
_MARKDOWN_IMAGE = re.compile(
    r"!\[[^\]\n]*\]\((?P<url>https?://[^\s)]+)(?:\s+\"[^\"\n]*\")?\)"
)
_RICH_MEDIA_BLOCK = re.compile(
    r"<tg-(?P<kind>slideshow|collage)\b[^>]*>.*?</tg-(?P=kind)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_UNCLOSED_RICH_MEDIA_BLOCK = re.compile(
    r"<tg-(?:slideshow|collage)\b[^>]*>.*\Z",
    re.IGNORECASE | re.DOTALL,
)
_RICH_MEDIA_TAG = re.compile(r"</?tg-[^>]*>?", re.IGNORECASE)
_MARKDOWN_LINK = re.compile(r"\[([^\]\n]+)\]\(https?://[^\s)]+\)")


class AgentResponseStream:
    """Streams plain text and atomically promotes it to a final Rich Message."""

    def __init__(
        self,
        placeholder: Any,
        *,
        bot: Any,
        chat_id: int,
        min_update_interval_seconds: float = 0.4,
    ) -> None:
        self.placeholder = placeholder
        self.bot = bot
        self.chat_id = chat_id
        self.min_update_interval_seconds = min_update_interval_seconds
        self._last_update_at = 0.0
        self._last_streamed_text = ""

    async def update(self, markdown: str) -> None:
        now = time.monotonic()
        if now - self._last_update_at < self.min_update_interval_seconds:
            return
        self._last_update_at = now

        plain_text = markdown_to_stream_text(markdown)
        if not plain_text or plain_text == self._last_streamed_text:
            return

        try:
            await self.placeholder.edit_text(plain_text + "▌", parse_mode=None)
            self._last_streamed_text = plain_text
        except TelegramBadRequest as exc:
            logger.warning(
                "plain streaming edit rejected; skipping stream update: %s",
                exc,
            )
        except (TelegramNetworkError, TelegramRetryAfter, TelegramServerError):
            logger.warning("temporary placeholder edit failure; skipping stream update")

    async def finalize(self, markdown: str, *, reply_markup: Any = None) -> None:
        rich_message = markdown_to_rich_message(markdown)
        try:
            await self.placeholder.edit_text(
                text=None,
                rich_message=rich_message,
                reply_markup=reply_markup,
            )
        except TelegramBadRequest:
            logger.warning("rich edit failed; falling back to regular Telegram HTML")
            await self.placeholder.edit_text(
                markdown_to_telegram_html(markdown),
                parse_mode="HTML",
                reply_markup=reply_markup,
            )


def markdown_to_rich_message(markdown: str) -> InputRichMessage:
    """Build Rich Markdown with explicitly typed external photo media.

    The ``tg://photo?id=`` identifier only links markup to the accompanying
    InputRichMessageMedia item. The nested InputMediaPhoto may still point at
    a public HTTP(S) URL, so no prior Telegram upload is required.
    """
    media: list[InputRichMessageMedia] = []

    def replace_image(match: re.Match[str]) -> str:
        media_id = f"photo_{len(media) + 1}"
        media.append(
            InputRichMessageMedia(
                id=media_id,
                media=InputMediaPhoto(media=match.group("url")),
            )
        )
        return f"![](tg://photo?id={media_id})"

    rendered = _MARKDOWN_IMAGE.sub(replace_image, markdown)
    return InputRichMessage(markdown=rendered, media=media or None)


def _without_rich_media(markdown: str) -> str:
    text = _RICH_MEDIA_BLOCK.sub("", markdown)
    text = _UNCLOSED_RICH_MEDIA_BLOCK.sub("", text)
    text = _MARKDOWN_IMAGE.sub("", text)
    return _RICH_MEDIA_TAG.sub("", text)


def markdown_to_stream_text(markdown: str) -> str:
    """Return stable presentation-neutral text for ordinary message edits."""
    text = _without_rich_media(markdown)
    text = _MARKDOWN_LINK.sub(r"\1", text)
    text = text.replace("**", "")
    text = re.sub(r"(?<!\*)\*(?!\*)", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def markdown_to_telegram_html(markdown: str) -> str:
    """Convert the supported agent Markdown subset to safe Telegram HTML.

    Everything outside bold, italic and HTTP(S) links is HTML-escaped. This
    keeps model-generated text from creating unsupported Telegram tags while
    preserving the formatting used by accommodation result cards.
    """
    markdown = _without_rich_media(markdown).strip()
    rendered: list[str] = []
    cursor = 0

    for match in _INLINE_MARKDOWN.finditer(markdown):
        rendered.append(html.escape(markdown[cursor:match.start()]))
        if match.group("url") is not None:
            label = html.escape(match.group("label"))
            url = html.escape(match.group("url"), quote=True)
            rendered.append(f'<a href="{url}">{label}</a>')
        elif match.group("bold") is not None:
            rendered.append(f'<b>{html.escape(match.group("bold"))}</b>')
        else:
            rendered.append(f'<i>{html.escape(match.group("italic"))}</i>')
        cursor = match.end()

    rendered.append(html.escape(markdown[cursor:]))
    return "".join(rendered)


async def send_agent_response(
    placeholder: Any,
    markdown: str,
    *,
    bot: Any,
    chat_id: int | str,
    reply_markup: Any = None,
) -> None:
    """Send native Rich Markdown, retaining safe HTML as a compatibility path."""
    try:
        await bot.send_rich_message(
            chat_id=chat_id,
            rich_message=markdown_to_rich_message(markdown),
            reply_markup=reply_markup,
        )
    except TelegramBadRequest:
        logger.warning("sendRichMessage failed; falling back to regular Telegram HTML")
        await placeholder.edit_text(
            markdown_to_telegram_html(markdown),
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
        return

    try:
        await placeholder.delete()
    except TelegramBadRequest:
        logger.warning("rich response sent, but streaming placeholder could not be deleted")
