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
from aiogram.types import InputRichMessage


logger = logging.getLogger(__name__)

_INLINE_MARKDOWN = re.compile(
    r"\[(?P<label>[^\]\n]+)\]\((?P<url>https?://[^\s)]+)\)"
    r"|\*\*(?P<bold>[^*\n]+)\*\*"
    r"|\*(?P<italic>[^*\n]+)\*"
)


class AgentResponseStream:
    """Streams a native Telegram Rich Message draft with a plain-text fallback."""

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
        self.draft_id = int(placeholder.message_id)
        self.min_update_interval_seconds = min_update_interval_seconds
        self._last_update_at = 0.0
        self._rich_draft_active = False
        self._rich_draft_supported = True
        self._placeholder_active = True

    async def update(self, markdown: str) -> None:
        now = time.monotonic()
        if now - self._last_update_at < self.min_update_interval_seconds:
            return
        self._last_update_at = now

        if self._rich_draft_supported:
            try:
                await self.bot.send_rich_message_draft(
                    chat_id=self.chat_id,
                    draft_id=self.draft_id,
                    rich_message=InputRichMessage(markdown=markdown),
                )
                self._rich_draft_active = True
                if self._placeholder_active:
                    try:
                        await self.placeholder.delete()
                    except TelegramBadRequest:
                        logger.warning("rich draft active, but placeholder could not be deleted")
                    else:
                        self._placeholder_active = False
                return
            except TelegramBadRequest as exc:
                self._rich_draft_supported = False
                logger.warning(
                    "sendRichMessageDraft failed; using plain streaming edits: %s",
                    exc,
                )
            except (TelegramNetworkError, TelegramRetryAfter, TelegramServerError):
                logger.warning(
                    "temporary sendRichMessageDraft failure; skipping stream update"
                )
                return

        if self._placeholder_active:
            try:
                await self.placeholder.edit_text(markdown + "▌", parse_mode=None)
            except TelegramBadRequest as exc:
                logger.warning(
                    "plain streaming edit rejected; skipping stream update: %s",
                    exc,
                )
            except (TelegramNetworkError, TelegramRetryAfter, TelegramServerError):
                logger.warning("temporary placeholder edit failure; skipping stream update")

    async def finalize(self, markdown: str, *, reply_markup: Any = None) -> None:
        rich_message = InputRichMessage(markdown=markdown)
        if self._rich_draft_active:
            try:
                await self.bot.send_rich_message(
                    chat_id=self.chat_id,
                    rich_message=rich_message,
                    reply_markup=reply_markup,
                )
            except TelegramBadRequest:
                logger.warning("rich final failed; sending regular Telegram HTML")
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=markdown_to_telegram_html(markdown),
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            return

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


def markdown_to_telegram_html(markdown: str) -> str:
    """Convert the supported agent Markdown subset to safe Telegram HTML.

    Everything outside bold, italic and HTTP(S) links is HTML-escaped. This
    keeps model-generated text from creating unsupported Telegram tags while
    preserving the formatting used by accommodation result cards.
    """
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
            rich_message=InputRichMessage(markdown=markdown),
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
