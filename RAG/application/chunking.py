from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from RAG.types import ChunkInput


@dataclass(slots=True, frozen=True)
class ChunkingConfig:
    max_chars: int = 1200
    overlap_chars: int = 150

    def __post_init__(self) -> None:
        if self.max_chars <= 0:
            raise ValueError("max_chars must be positive")
        if self.overlap_chars < 0:
            raise ValueError("overlap_chars must not be negative")
        if self.overlap_chars >= self.max_chars:
            raise ValueError("overlap_chars must be less than max_chars")


@dataclass(slots=True, frozen=True)
class TextChunker:
    config: ChunkingConfig = ChunkingConfig()

    def split(
        self,
        *,
        tenant_id: str,
        document_id: str,
        version_id: str,
        text: str,
        visibility: str,
    ) -> tuple[ChunkInput, ...]:
        content_start = len(text) - len(text.lstrip())
        content_end = len(text.rstrip())
        normalized_text = text[content_start:content_end]
        if not normalized_text:
            return ()

        spans = _semantic_spans(normalized_text)
        chunk_spans = self._merge_spans(spans)

        chunks: list[ChunkInput] = []
        for index, (start, end) in enumerate(chunk_spans):
            chunk_text = normalized_text[start:end].strip()
            if not chunk_text:
                continue
            adjusted_start = start + (len(normalized_text[start:end]) - len(normalized_text[start:end].lstrip()))
            adjusted_end = adjusted_start + len(chunk_text)
            chunk_id = _stable_chunk_id(
                tenant_id=tenant_id,
                document_id=document_id,
                version_id=version_id,
                index=index,
                text=chunk_text,
            )
            chunks.append(
                ChunkInput(
                    chunk_id=chunk_id,
                    index=index,
                    text=chunk_text,
                    start_byte=_byte_offset(text, content_start + adjusted_start),
                    end_byte=_byte_offset(text, content_start + adjusted_end),
                    visibility=visibility,
                )
            )

        return tuple(chunks)

    def _merge_spans(self, spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
        chunks: list[tuple[int, int]] = []
        current_start: int | None = None
        current_end: int | None = None

        for start, end in spans:
            if end - start > self.config.max_chars:
                split_start = start
                if current_start is not None and current_end is not None:
                    chunks.append((current_start, current_end))
                    split_start = max(0, current_end - self.config.overlap_chars)
                elif chunks and self.config.overlap_chars:
                    split_start = max(0, chunks[-1][1] - self.config.overlap_chars)
                chunks.extend(_split_large_span(split_start, end, self.config))
                current_start = None
                current_end = None
                continue

            if current_start is None:
                if chunks and self.config.overlap_chars:
                    current_start = max(
                        chunks[-1][1] - self.config.overlap_chars,
                        end - self.config.max_chars,
                    )
                else:
                    current_start = start
                current_end = end
                continue

            assert current_end is not None
            if end - current_start <= self.config.max_chars:
                current_end = end
                continue

            chunks.append((current_start, current_end))
            current_start = max(
                current_end - self.config.overlap_chars,
                end - self.config.max_chars,
            )
            current_end = end

        if current_start is not None and current_end is not None:
            if current_end - current_start > self.config.max_chars:
                chunks.extend(_split_large_span(current_start, current_end, self.config))
            else:
                chunks.append((current_start, current_end))

        return chunks


def _semantic_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for match in re.finditer(r".+?(?:\n\s*\n|(?<=[.!?])\s+|$)", text, flags=re.DOTALL):
        start, end = match.span()
        if text[start:end].strip():
            spans.append((start, end))
    return spans or [(0, len(text))]


def _split_large_span(start: int, end: int, config: ChunkingConfig) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = start
    while cursor < end:
        next_end = min(cursor + config.max_chars, end)
        spans.append((cursor, next_end))
        if next_end == end:
            break
        cursor = max(next_end - config.overlap_chars, cursor + 1)
    return spans


def _stable_chunk_id(
    *,
    tenant_id: str,
    document_id: str,
    version_id: str,
    index: int,
    text: str,
) -> str:
    digest = hashlib.sha256(
        f"{tenant_id}\0{document_id}\0{version_id}\0{index}\0{text}".encode("utf-8")
    ).hexdigest()[:16]
    return f"{version_id}-chunk-{index}-{digest}"


def _byte_offset(text: str, char_offset: int) -> int:
    return len(text[:char_offset].encode("utf-8"))
