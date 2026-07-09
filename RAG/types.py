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
class IngestTextDocumentCommand:
    document_id: str
    version_id: str
    tenant_id: str
    title: str
    raw_text: str
    source_type: str = "text"
    visibility: str = "tenant"
    trust_level: str = "unknown"
    chunk_visibility: str = "tenant"
    external_ref: str = ""
    original_name: str = ""
    max_chunk_chars: int = 1200
    chunk_overlap_chars: int = 150


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
class RejectVersionCommand:
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


@dataclass(slots=True, frozen=True)
class IngestTextDocumentResultDTO:
    document: DocumentDTO
    version: DocumentVersionDTO
    chunks: tuple[ChunkDTO, ...]


@dataclass(slots=True, frozen=True)
class ChunkDTO:
    chunk_id: str
    version_id: str
    tenant_id: str
    index: int
    text: str
    start_byte: int
    end_byte: int
    visibility: str


@dataclass(slots=True, frozen=True)
class DocumentDetailsDTO:
    document: DocumentDTO
    versions: tuple[DocumentVersionDTO, ...]


@dataclass(slots=True, frozen=True)
class DocumentListItemDTO:
    document_id: str
    tenant_id: str
    title: str
    visibility: str
    source_type: str
    version_count: int
    published_version_id: str | None = None


@dataclass(slots=True, frozen=True)
class GetDocumentQuery:
    tenant_id: str
    document_id: str


@dataclass(slots=True, frozen=True)
class ListDocumentsQuery:
    tenant_id: str
    review_status: str | None = None
    visibility: str | None = None
    source_type: str | None = None
    limit: int = 100
    offset: int = 0


@dataclass(slots=True, frozen=True)
class GetVersionChunksQuery:
    tenant_id: str
    document_id: str
    version_id: str


@dataclass(slots=True, frozen=True)
class SearchPublishedMemoryQuery:
    tenant_id: str
    query: str
    limit: int = 8
    source_type: str | None = None
    visibility: str | None = None


@dataclass(slots=True, frozen=True)
class MemorySearchResultDTO:
    chunk_id: str
    document_id: str
    version_id: str
    tenant_id: str
    title: str
    text: str
    score: float
    chunk_index: int
    source_type: str
    trust_level: str
    visibility: str


@dataclass(slots=True, frozen=True)
class BuildAgentContextQuery:
    tenant_id: str
    query: str
    limit: int = 8
    source_type: str | None = None
    visibility: str | None = None


@dataclass(slots=True, frozen=True)
class AgentContextDTO:
    query: str
    context_text: str
    results: tuple[MemorySearchResultDTO, ...]
