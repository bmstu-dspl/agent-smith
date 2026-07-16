from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from RAG._repository import DocumentStore, PublishedMemorySearchStore


class Clock(Protocol):
    def __call__(self) -> datetime: ...


class EmbeddingProvider(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...

    def embed_query(self, text: str) -> tuple[float, ...]: ...


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


__all__ = ["Clock", "DocumentStore", "EmbeddingProvider", "PublishedMemorySearchStore", "utcnow"]
