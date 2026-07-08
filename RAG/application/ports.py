from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from RAG._repository import DocumentStore


class Clock(Protocol):
    def __call__(self) -> datetime: ...


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


__all__ = ["Clock", "DocumentStore", "utcnow"]
