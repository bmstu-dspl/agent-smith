from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class CreateDocumentCommand:
    document_id: str
    tenant_id: str
    title: str
    source_type: str
    visibility: str
    external_ref: str = ""
    original_name: str = ""


@dataclass(slots=True, frozen=True)
class AddDocumentVersionCommand:
    document_id: str
    version_id: str
    tenant_id: str
    raw_text: str
    source_type: str
    trust_level: str
    external_ref: str = ""
    original_name: str = ""


@dataclass(slots=True, frozen=True)
class ChunkInput:
    chunk_id: str
    index: int
    text: str
    start_byte: int
    end_byte: int
    visibility: str


@dataclass(slots=True, frozen=True)
class MarkVersionProcessedCommand:
    document_id: str
    version_id: str
    tenant_id: str
    chunks: tuple[ChunkInput, ...]


@dataclass(slots=True, frozen=True)
class ApproveVersionCommand:
    document_id: str
    version_id: str
    tenant_id: str


@dataclass(slots=True, frozen=True)
class PublishVersionCommand:
    document_id: str
    version_id: str
    tenant_id: str


@dataclass(slots=True, frozen=True)
class DocumentDTO:
    document_id: str
    tenant_id: str
    title: str
    visibility: str
    version_count: int
    published_version_id: str | None = None


@dataclass(slots=True, frozen=True)
class DocumentVersionDTO:
    version_id: str
    document_id: str
    tenant_id: str
    review_status: str
    trust_level: str
    source_type: str
    chunk_count: int
    external_ref: str = ""
    original_name: str = ""
    processed_at: datetime | None = None
    reviewed_at: datetime | None = None
    published_at: datetime | None = None
