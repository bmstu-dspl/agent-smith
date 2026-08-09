"""Safe Telegram streaming and Rich Message rendering for agent replies."""

from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import (
    BufferedInputFile,
    InputMediaPhoto,
    InputRichMessage,
    InputRichMessageMedia,
    LinkPreviewOptions,
)

from shared.redis_client import get_redis_client


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
_EMPTY_RICH_MEDIA_BLOCK = re.compile(
    r"<tg-(?P<kind>slideshow|collage)\b[^>]*>\s*</tg-(?P=kind)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_UNCLOSED_RICH_MEDIA_BLOCK = re.compile(
    r"<tg-(?:slideshow|collage)\b[^>]*>.*\Z",
    re.IGNORECASE | re.DOTALL,
)
_RICH_MEDIA_TAG = re.compile(r"</?tg-[^>]*>?", re.IGNORECASE)
_MARKDOWN_LINK = re.compile(r"\[([^\]\n]+)\]\(https?://[^\s)]+\)")
_MARKDOWN_HTTP_DESTINATION = re.compile(r"(?<=\]\()https?://[^\s)]+")
_MAX_DRAFT_TEXT_LENGTH = 4096
_MAX_PHOTO_BYTES = 10 * 1024 * 1024
_MAX_TOTAL_MEDIA_BYTES = 50 * 1024 * 1024
_MEDIA_CACHE_PREFIX = "telegram:rich-media:file-id:"
_DEFAULT_ALLOWED_MEDIA_HOSTS = {"partner-static.tlintegration.com"}


@dataclass(slots=True)
class PreparedRichMessage:
    rich_message: InputRichMessage
    source_urls: list[str]


class RichMediaResolver:
    """Resolve TravelLine URLs to Telegram uploads or cached Telegram file IDs."""

    def __init__(
        self,
        *,
        redis: Any = None,
        http_client_factory: Callable[..., Any] = httpx.AsyncClient,
        allowed_hosts: set[str] | None = None,
    ) -> None:
        self._redis = redis
        self._redis_resolved = redis is not None
        self._http_client_factory = http_client_factory
        configured_hosts = {
            host.strip().lower()
            for host in os.getenv("RICH_MEDIA_ALLOWED_HOSTS", "").split(",")
            if host.strip()
        }
        self._allowed_hosts = allowed_hosts or configured_hosts or _DEFAULT_ALLOWED_MEDIA_HOSTS

    @staticmethod
    def cache_key(url: str) -> str:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return f"{_MEDIA_CACHE_PREFIX}{digest}"

    async def prepare(self, markdown: str) -> PreparedRichMessage:
        markdown = normalize_markdown_http_urls(markdown)
        matches = list(_MARKDOWN_IMAGE.finditer(markdown))
        if not matches:
            return PreparedRichMessage(
                rich_message=InputRichMessage(markdown=markdown),
                source_urls=[],
            )

        urls = list(
            dict.fromkeys(
                match.group("url")
                for match in matches
                if self._is_allowed_url(match.group("url"))
            )
        )
        resolved = await self._resolve_all(urls)
        media: list[InputRichMessageMedia] = []
        source_urls: list[str] = []

        def replace_image(match: re.Match[str]) -> str:
            url = match.group("url")
            payload = resolved.get(url)
            if payload is None:
                return ""
            media_id = f"photo_{len(media) + 1}"
            media.append(
                InputRichMessageMedia(
                    id=media_id,
                    media=InputMediaPhoto(media=payload),
                )
            )
            source_urls.append(url)
            return f"![](tg://photo?id={media_id})"

        rendered = _MARKDOWN_IMAGE.sub(replace_image, markdown)
        rendered = _EMPTY_RICH_MEDIA_BLOCK.sub("", rendered)
        rendered = re.sub(r"\n{3,}", "\n\n", rendered).strip()
        return PreparedRichMessage(
            rich_message=InputRichMessage(markdown=rendered, media=media or None),
            source_urls=source_urls,
        )

    def _is_allowed_url(self, url: str) -> bool:
        parsed = urlparse(url)
        allowed = parsed.scheme == "https" and parsed.hostname in self._allowed_hosts
        if not allowed:
            logger.warning("blocked untrusted rich media URL host=%s", parsed.hostname)
        return allowed

    async def remember(self, prepared: PreparedRichMessage, sent_message: Any) -> None:
        if not prepared.source_urls:
            return
        file_ids = list(_iter_photo_file_ids(sent_message))
        if not file_ids:
            logger.warning("rich response contained no reusable Telegram photo file IDs")
            return

        redis = await self._get_redis()
        if redis is None:
            return
        for url, file_id in zip(prepared.source_urls, file_ids, strict=False):
            try:
                await redis.set(self.cache_key(url), file_id)
            except Exception:
                logger.warning("failed to cache Telegram photo file ID", exc_info=True)

    async def _resolve_all(self, urls: list[str]) -> dict[str, Any]:
        redis = await self._get_redis()
        cached: dict[str, Any] = {}
        missing: list[str] = []
        for url in urls:
            file_id = await self._get_cached_file_id(redis, url)
            if file_id:
                cached[url] = file_id
            else:
                missing.append(url)

        if not missing:
            return cached

        total_bytes = 0
        total_lock = asyncio.Lock()
        semaphore = asyncio.Semaphore(4)
        async with self._http_client_factory(
            follow_redirects=True,
            timeout=httpx.Timeout(20.0),
        ) as client:

            async def download(url: str) -> tuple[str, Any | None]:
                nonlocal total_bytes
                try:
                    async with semaphore:
                        response = await client.get(url)
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if not content_type.startswith("image/"):
                        raise ValueError(f"unexpected content type {content_type!r}")
                    content = response.content
                    if not content or len(content) > _MAX_PHOTO_BYTES:
                        raise ValueError(f"invalid photo size: {len(content)} bytes")
                    async with total_lock:
                        if total_bytes + len(content) > _MAX_TOTAL_MEDIA_BYTES:
                            raise ValueError("rich media exceeds total download limit")
                        total_bytes += len(content)
                    extension = _extension_for_content_type(content_type)
                    filename = hashlib.sha256(url.encode("utf-8")).hexdigest() + extension
                    return url, BufferedInputFile(content, filename=filename)
                except Exception as exc:
                    logger.warning("failed to download rich media url=%s: %s", url, exc)
                    return url, None

            downloaded = await asyncio.gather(*(download(url) for url in missing))

        cached.update({url: payload for url, payload in downloaded if payload is not None})
        return cached

    async def _get_redis(self) -> Any:
        if self._redis_resolved:
            return self._redis
        self._redis_resolved = True
        try:
            self._redis = await get_redis_client()
        except Exception:
            logger.warning("Telegram media cache is unavailable", exc_info=True)
            self._redis = None
        return self._redis

    async def _get_cached_file_id(self, redis: Any, url: str) -> str | None:
        if redis is None:
            return None
        try:
            value = await redis.get(self.cache_key(url))
        except Exception:
            logger.warning("failed to read Telegram media cache", exc_info=True)
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value) if value else None


class AgentResponseStream:
    """Stream an ephemeral plain draft, then persist one final Rich Message."""

    def __init__(
        self,
        *,
        bot: Any,
        chat_id: int,
        draft_id: int | None = None,
        message_thread_id: int | None = None,
        media_resolver: RichMediaResolver | Any | None = None,
        min_update_interval_seconds: float = 0.4,
    ) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self.draft_id = draft_id or secrets.randbelow(2_147_483_647) + 1
        self.message_thread_id = message_thread_id
        self.media_resolver = media_resolver or RichMediaResolver()
        self.min_update_interval_seconds = min_update_interval_seconds
        self._last_update_at = 0.0
        self._last_streamed_text = ""
        self._draft_supported = True

    async def start(self) -> None:
        await self._send_draft("")

    async def update(self, markdown: str) -> None:
        now = time.monotonic()
        if now - self._last_update_at < self.min_update_interval_seconds:
            return
        self._last_update_at = now

        plain_text = markdown_to_stream_text(markdown)[:_MAX_DRAFT_TEXT_LENGTH]
        if not plain_text or plain_text == self._last_streamed_text:
            return
        if await self._send_draft(plain_text):
            self._last_streamed_text = plain_text

    async def finalize(self, markdown: str, *, reply_markup: Any = None) -> None:
        prepared = await self.media_resolver.prepare(markdown)
        try:
            sent_message = await self.bot.send_rich_message(
                chat_id=self.chat_id,
                message_thread_id=self.message_thread_id,
                rich_message=prepared.rich_message,
                reply_markup=reply_markup,
            )
        except TelegramBadRequest as exc:
            logger.warning(
                "sendRichMessage failed; falling back to regular Telegram HTML: %s",
                exc,
            )
            await self.bot.send_message(
                chat_id=self.chat_id,
                message_thread_id=self.message_thread_id,
                text=markdown_to_telegram_html(markdown),
                parse_mode="HTML",
                link_preview_options=LinkPreviewOptions(is_disabled=True),
                reply_markup=reply_markup,
            )
            return

        await self.media_resolver.remember(prepared, sent_message)

    async def _send_draft(self, text: str) -> bool:
        if not self._draft_supported:
            return False
        try:
            await self.bot.send_message_draft(
                chat_id=self.chat_id,
                draft_id=self.draft_id,
                message_thread_id=self.message_thread_id,
                text=text,
                parse_mode=None,
            )
            return True
        except TelegramBadRequest as exc:
            self._draft_supported = False
            logger.warning("sendMessageDraft rejected; disabling draft stream: %s", exc)
        except (TelegramNetworkError, TelegramRetryAfter, TelegramServerError) as exc:
            logger.warning("temporary sendMessageDraft failure; skipping update: %s", exc)
        return False


def _extension_for_content_type(content_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(content_type, ".img")


def _iter_photo_file_ids(message: Any):
    rich_message = getattr(message, "rich_message", None)
    blocks = getattr(rich_message, "blocks", None) or []

    def walk(items: list[Any]):
        for block in items:
            block_type = getattr(block, "type", None)
            block_type = getattr(block_type, "value", block_type)
            if block_type == "photo":
                photos = getattr(block, "photo", None) or []
                if photos:
                    file_id = getattr(photos[-1], "file_id", None)
                    if file_id:
                        yield file_id
            nested = getattr(block, "blocks", None) or []
            yield from walk(nested)

    yield from walk(blocks)


def _without_rich_media(markdown: str) -> str:
    text = _RICH_MEDIA_BLOCK.sub("", markdown)
    text = _UNCLOSED_RICH_MEDIA_BLOCK.sub("", text)
    text = _MARKDOWN_IMAGE.sub("", text)
    return _RICH_MEDIA_TAG.sub("", text)


def markdown_to_stream_text(markdown: str) -> str:
    """Return stable presentation-neutral text for an ephemeral draft."""
    text = _without_rich_media(markdown)
    text = _MARKDOWN_LINK.sub(r"\1", text)
    text = text.replace("**", "")
    text = re.sub(r"(?<!\*)\*(?!\*)", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def normalize_markdown_http_urls(markdown: str) -> str:
    """Decode accidental HTML entities inside Rich Markdown URL targets once."""
    return _MARKDOWN_HTTP_DESTINATION.sub(
        lambda match: html.unescape(match.group(0)),
        markdown,
    )


def markdown_to_telegram_html(markdown: str) -> str:
    """Convert the supported agent Markdown subset to safe Telegram HTML."""
    markdown = normalize_markdown_http_urls(_without_rich_media(markdown)).strip()
    return _markdown_inline_to_html(markdown)


def _markdown_inline_to_html(markdown: str) -> str:
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
    """Compatibility helper for call sites that still own a placeholder."""
    stream = AgentResponseStream(bot=bot, chat_id=int(chat_id))
    await stream.finalize(markdown, reply_markup=reply_markup)
    try:
        await placeholder.delete()
    except TelegramBadRequest:
        logger.warning("response sent, but compatibility placeholder could not be deleted")
