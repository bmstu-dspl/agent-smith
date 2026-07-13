from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from ._errors import ValidationError

_SOURCE_TYPES: Final[set[str]] = {"text", "pdf", "docx", "md", "html"}
_TRUST_LEVELS: Final[set[str]] = {"unknown", "low", "trusted", "canonical"}
_REVIEW_STATUSES: Final[set[str]] = {
    "draft",
    "processed",
    "approved",
    "rejected",
    "published",
    "archived",
}
_VISIBILITIES: Final[set[str]] = {"private", "restricted", "tenant"}


def _normalized_non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValidationError(f"{field_name} must not be empty")
    return normalized


def _normalized_choice(value: str, choices: set[str], field_name: str) -> str:
    normalized = _normalized_non_empty(value, field_name).lower()
    if normalized not in choices:
        raise ValidationError(f"{field_name} has invalid value: {value!r}")
    return normalized


@dataclass(slots=True, frozen=True)
class SourceMetadata:
    source_type: str
    external_ref: str = ""
    original_name: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_type",
            _normalized_choice(self.source_type, _SOURCE_TYPES, "source_type"),
        )
        object.__setattr__(self, "external_ref", self.external_ref.strip())
        object.__setattr__(self, "original_name", self.original_name.strip())


@dataclass(slots=True, frozen=True)
class Chunk:
    chunk_id: str
    tenant_id: str
    version_id: str
    index: int
    text: str
    start_byte: int
    end_byte: int
    visibility: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "chunk_id", _normalized_non_empty(self.chunk_id, "chunk_id"))
        object.__setattr__(self, "tenant_id", _normalized_non_empty(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "version_id", _normalized_non_empty(self.version_id, "version_id"))
        object.__setattr__(self, "text", _normalized_non_empty(self.text, "chunk text"))
        object.__setattr__(
            self,
            "visibility",
            _normalized_choice(self.visibility, _VISIBILITIES, "visibility"),
        )
        if self.index < 0:
            raise ValidationError("chunk index must not be negative")
        if self.start_byte < 0:
            raise ValidationError("chunk start offset must not be negative")
        if self.end_byte <= self.start_byte:
            raise ValidationError("chunk end offset must be greater than start offset")


@dataclass(slots=True)
class DocumentVersion:
    version_id: str
    document_id: str
    tenant_id: str
    raw_text: str
    source_metadata: SourceMetadata
    trust_level: str
    created_at: datetime
    updated_at: datetime
    review_status: str = "draft"
    chunks: list[Chunk] = field(default_factory=list)
    processed_at: datetime | None = None
    reviewed_at: datetime | None = None
    published_at: datetime | None = None

    def __post_init__(self) -> None:
        self.version_id = _normalized_non_empty(self.version_id, "version_id")
        self.document_id = _normalized_non_empty(self.document_id, "document_id")
        self.tenant_id = _normalized_non_empty(self.tenant_id, "tenant_id")
        self.raw_text = _normalized_non_empty(self.raw_text, "raw_text")
        self.trust_level = _normalized_choice(self.trust_level, _TRUST_LEVELS, "trust_level")
        self.review_status = _normalized_choice(
            self.review_status,
            _REVIEW_STATUSES,
            "review_status",
        )

    def mark_processed(self, chunks: list[Chunk], now: datetime) -> None:
        if self.review_status == "archived":
            raise ValidationError("archived version can not be modified")
        if self.review_status != "draft":
            raise ValidationError("version already processed")
        for chunk in chunks:
            if chunk.tenant_id != self.tenant_id:
                raise ValidationError("chunk tenant must match document version tenant")
        self.chunks = list(chunks)
        self.review_status = "processed"
        self.processed_at = now
        self.updated_at = now

    def approve(self, now: datetime) -> None:
        if self.review_status == "archived":
            raise ValidationError("archived version can not be modified")
        if self.review_status != "processed":
            raise ValidationError("version must be processed before review")
        self.review_status = "approved"
        self.reviewed_at = now
        self.updated_at = now

    def reject(self, now: datetime) -> None:
        if self.review_status == "archived":
            raise ValidationError("archived version can not be modified")
        if self.review_status != "processed":
            raise ValidationError("version must be processed before review")
        self.review_status = "rejected"
        self.reviewed_at = now
        self.updated_at = now

    def publish(self, now: datetime) -> None:
        if self.review_status == "archived":
            raise ValidationError("archived version can not be modified")
        if self.review_status == "rejected":
            raise ValidationError("rejected version can not be published")
        if self.review_status != "approved":
            raise ValidationError("only approved version can be published")
        self.review_status = "published"
        self.published_at = now
        self.updated_at = now

    def archive(self, now: datetime) -> None:
        if self.review_status == "archived":
            raise ValidationError("version is already archived")
        self.review_status = "archived"
        self.updated_at = now


@dataclass(slots=True)
class Document:
    document_id: str
    tenant_id: str
    title: str
    source_metadata: SourceMetadata
    visibility: str
    created_at: datetime
    updated_at: datetime
    published_version_id: str | None = None
    versions: dict[str, DocumentVersion] = field(default_factory=dict)
    revision: int = 0

    def __post_init__(self) -> None:
        self.document_id = _normalized_non_empty(self.document_id, "document_id")
        self.tenant_id = _normalized_non_empty(self.tenant_id, "tenant_id")
        self.title = _normalized_non_empty(self.title, "title")
        self.visibility = _normalized_choice(self.visibility, _VISIBILITIES, "visibility")

    def add_version(self, version: DocumentVersion, now: datetime) -> None:
        if version.document_id != self.document_id:
            raise ValidationError("version document id must match aggregate document id")
        if version.tenant_id != self.tenant_id:
            raise ValidationError("version tenant must match document tenant")
        if version.version_id in self.versions:
            raise ValidationError("version already exists")
        self.versions[version.version_id] = version
        self.updated_at = now

    def get_version(self, version_id: str) -> DocumentVersion:
        normalized = _normalized_non_empty(version_id, "version_id")
        version = self.versions.get(normalized)
        if version is None:
            raise ValidationError("version not found")
        return version

    def publish_version(self, version_id: str, now: datetime) -> DocumentVersion:
        version = self.get_version(version_id)
        if self.published_version_id is not None and self.published_version_id != version.version_id:
            raise ValidationError("published version already exists")
        version.publish(now)
        self.published_version_id = version.version_id
        self.updated_at = now
        return version

    def archive_version(self, version_id: str, now: datetime) -> DocumentVersion:
        version = self.get_version(version_id)
        version.archive(now)
        if self.published_version_id == version.version_id:
            self.published_version_id = None
        self.updated_at = now
        return version

    def delete_version(self, version_id: str, now: datetime) -> None:
        version = self.get_version(version_id)
        if self.published_version_id == version.version_id:
            raise ValidationError("published version must be archived before deletion")
        del self.versions[version.version_id]
        self.updated_at = now
