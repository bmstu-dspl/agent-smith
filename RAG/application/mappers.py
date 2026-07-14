from __future__ import annotations

from dataclasses import asdict

from RAG._domain import Chunk, Document, DocumentVersion
from RAG.types import (
    ChunkDTO,
    DocumentDTO,
    DocumentDetailsDTO,
    DocumentListItemDTO,
    DocumentVersionDTO,
)


def to_document_dto(document: Document) -> DocumentDTO:
    return DocumentDTO(
        document_id=document.document_id,
        tenant_id=document.tenant_id,
        title=document.title,
        visibility=document.visibility,
        version_count=len(document.versions),
        published_version_id=document.published_version_id,
    )


def to_document_details_dto(document: Document) -> DocumentDetailsDTO:
    versions = tuple(to_version_dto(version) for version in document.versions.values())
    return DocumentDetailsDTO(document=to_document_dto(document), versions=versions)


def to_document_list_item_dto(document: Document) -> DocumentListItemDTO:
    return DocumentListItemDTO(
        document_id=document.document_id,
        tenant_id=document.tenant_id,
        title=document.title,
        visibility=document.visibility,
        source_type=document.source_metadata.source_type,
        version_count=len(document.versions),
        published_version_id=document.published_version_id,
    )


def to_version_dto(version: DocumentVersion) -> DocumentVersionDTO:
    payload = asdict(version.source_metadata)
    return DocumentVersionDTO(
        version_id=version.version_id,
        document_id=version.document_id,
        tenant_id=version.tenant_id,
        review_status=version.review_status,
        trust_level=version.trust_level,
        source_type=payload["source_type"],
        external_ref=payload["external_ref"],
        original_name=payload["original_name"],
        chunk_count=len(version.chunks),
        processed_at=version.processed_at,
        reviewed_at=version.reviewed_at,
        published_at=version.published_at,
    )


def to_chunk_dto(chunk: Chunk) -> ChunkDTO:
    return ChunkDTO(
        chunk_id=chunk.chunk_id,
        version_id=chunk.version_id,
        tenant_id=chunk.tenant_id,
        index=chunk.index,
        text=chunk.text,
        start_byte=chunk.start_byte,
        end_byte=chunk.end_byte,
        visibility=chunk.visibility,
    )
