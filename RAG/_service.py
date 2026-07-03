from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from ._domain import Chunk, Document, DocumentVersion, SourceMetadata
from ._errors import DocumentNotFoundError
from ._repository import DocumentStore
from .types import (
    AddDocumentVersionCommand,
    ApproveVersionCommand,
    ChunkInput,
    CreateDocumentCommand,
    DocumentDTO,
    DocumentVersionDTO,
    MarkVersionProcessedCommand,
    PublishVersionCommand,
)


class MemoryModule:
    def __init__(self, store: DocumentStore, *, now_provider=None) -> None:
        self._store = store
        self._now_provider = now_provider or self._utcnow

    def create_document(self, command: CreateDocumentCommand) -> DocumentDTO:
        now = self._now_provider()
        document = Document(
            document_id=command.document_id,
            tenant_id=command.tenant_id,
            title=command.title,
            source_metadata=SourceMetadata(
                source_type=command.source_type,
                external_ref=command.external_ref,
                original_name=command.original_name,
            ),
            visibility=command.visibility,
            created_at=now,
            updated_at=now,
        )
        self._store.save(document)
        return self._to_document_dto(document)

    def add_document_version(self, command: AddDocumentVersionCommand) -> DocumentVersionDTO:
        document = self._load_document(command.tenant_id, command.document_id)
        now = self._now_provider()
        version = DocumentVersion(
            version_id=command.version_id,
            document_id=command.document_id,
            tenant_id=command.tenant_id,
            raw_text=command.raw_text,
            source_metadata=SourceMetadata(
                source_type=command.source_type,
                external_ref=command.external_ref,
                original_name=command.original_name,
            ),
            trust_level=command.trust_level,
            created_at=now,
            updated_at=now,
        )
        document.add_version(version, now)
        self._store.save(document)
        return self._to_version_dto(version)

    def mark_version_processed(self, command: MarkVersionProcessedCommand) -> DocumentVersionDTO:
        document = self._load_document(command.tenant_id, command.document_id)
        version = document.get_version(command.version_id)
        now = self._now_provider()
        version.mark_processed(self._to_chunks(command.tenant_id, command.version_id, command.chunks), now)
        self._store.save(document)
        return self._to_version_dto(version)

    def approve_version(self, command: ApproveVersionCommand) -> DocumentVersionDTO:
        document = self._load_document(command.tenant_id, command.document_id)
        version = document.get_version(command.version_id)
        now = self._now_provider()
        version.approve(now)
        self._store.save(document)
        return self._to_version_dto(version)

    def publish_version(self, command: PublishVersionCommand) -> DocumentVersionDTO:
        document = self._load_document(command.tenant_id, command.document_id)
        version = document.publish_version(command.version_id, self._now_provider())
        self._store.save(document)
        return self._to_version_dto(version)

    def _load_document(self, tenant_id: str, document_id: str) -> Document:
        document = self._store.get(tenant_id, document_id)
        if document is None:
            raise DocumentNotFoundError(f"document {document_id!r} was not found")
        return document

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(tz=timezone.utc)

    @staticmethod
    def _to_chunks(tenant_id: str, version_id: str, chunks: tuple[ChunkInput, ...]) -> list[Chunk]:
        return [
            Chunk(
                chunk_id=item.chunk_id,
                tenant_id=tenant_id,
                version_id=version_id,
                index=item.index,
                text=item.text,
                start_byte=item.start_byte,
                end_byte=item.end_byte,
                visibility=item.visibility,
            )
            for item in chunks
        ]

    @staticmethod
    def _to_document_dto(document: Document) -> DocumentDTO:
        return DocumentDTO(
            document_id=document.document_id,
            tenant_id=document.tenant_id,
            title=document.title,
            visibility=document.visibility,
            version_count=len(document.versions),
            published_version_id=document.published_version_id,
        )

    @staticmethod
    def _to_version_dto(version: DocumentVersion) -> DocumentVersionDTO:
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
