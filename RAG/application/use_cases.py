from __future__ import annotations

from RAG._domain import Chunk, Document, DocumentVersion, SourceMetadata
from RAG._errors import DocumentNotFoundError
from RAG.application.mappers import (
    to_chunk_dto,
    to_document_details_dto,
    to_document_dto,
    to_document_list_item_dto,
    to_version_dto,
)
from RAG.application.ports import Clock, DocumentStore
from RAG.types import (
    AddDocumentVersionCommand,
    ApproveVersionCommand,
    ChunkDTO,
    ChunkInput,
    CreateDocumentCommand,
    DocumentDTO,
    DocumentDetailsDTO,
    DocumentListItemDTO,
    DocumentVersionDTO,
    GetDocumentQuery,
    GetVersionChunksQuery,
    ListDocumentsQuery,
    MarkVersionProcessedCommand,
    PublishVersionCommand,
    RejectVersionCommand,
)


class CreateDocumentUseCase:
    def __init__(self, store: DocumentStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    def execute(self, command: CreateDocumentCommand) -> DocumentDTO:
        now = self._clock()
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
        return to_document_dto(document)


class AddDocumentVersionUseCase:
    def __init__(self, store: DocumentStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    def execute(self, command: AddDocumentVersionCommand) -> DocumentVersionDTO:
        document = _load_document(self._store, command.tenant_id, command.document_id)
        now = self._clock()
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
        return to_version_dto(version)


class MarkVersionProcessedUseCase:
    def __init__(self, store: DocumentStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    def execute(self, command: MarkVersionProcessedCommand) -> DocumentVersionDTO:
        document = _load_document(self._store, command.tenant_id, command.document_id)
        version = document.get_version(command.version_id)
        version.mark_processed(_to_chunks(command.tenant_id, command.version_id, command.chunks), self._clock())
        self._store.save(document)
        return to_version_dto(version)


class ApproveVersionUseCase:
    def __init__(self, store: DocumentStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    def execute(self, command: ApproveVersionCommand) -> DocumentVersionDTO:
        document = _load_document(self._store, command.tenant_id, command.document_id)
        version = document.get_version(command.version_id)
        version.approve(self._clock())
        self._store.save(document)
        return to_version_dto(version)


class RejectVersionUseCase:
    def __init__(self, store: DocumentStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    def execute(self, command: RejectVersionCommand) -> DocumentVersionDTO:
        document = _load_document(self._store, command.tenant_id, command.document_id)
        version = document.get_version(command.version_id)
        version.reject(self._clock())
        self._store.save(document)
        return to_version_dto(version)


class PublishVersionUseCase:
    def __init__(self, store: DocumentStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    def execute(self, command: PublishVersionCommand) -> DocumentVersionDTO:
        document = _load_document(self._store, command.tenant_id, command.document_id)
        version = document.publish_version(command.version_id, self._clock())
        self._store.save(document)
        return to_version_dto(version)


class GetDocumentUseCase:
    def __init__(self, store: DocumentStore) -> None:
        self._store = store

    def execute(self, query: GetDocumentQuery) -> DocumentDetailsDTO:
        document = _load_document(self._store, query.tenant_id, query.document_id)
        return to_document_details_dto(document)


class ListDocumentsUseCase:
    def __init__(self, store: DocumentStore) -> None:
        self._store = store

    def execute(self, query: ListDocumentsQuery) -> tuple[DocumentListItemDTO, ...]:
        documents = self._store.list(
            query.tenant_id,
            review_status=query.review_status,
            visibility=query.visibility,
            source_type=query.source_type,
            limit=query.limit,
            offset=query.offset,
        )
        return tuple(to_document_list_item_dto(document) for document in documents)


class GetVersionChunksUseCase:
    def __init__(self, store: DocumentStore) -> None:
        self._store = store

    def execute(self, query: GetVersionChunksQuery) -> tuple[ChunkDTO, ...]:
        document = _load_document(self._store, query.tenant_id, query.document_id)
        version = document.get_version(query.version_id)
        return tuple(to_chunk_dto(chunk) for chunk in version.chunks)


def _load_document(store: DocumentStore, tenant_id: str, document_id: str) -> Document:
    document = store.get(tenant_id, document_id)
    if document is None:
        raise DocumentNotFoundError(f"document {document_id!r} was not found")
    return document


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
