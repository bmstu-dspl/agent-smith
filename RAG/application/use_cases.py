from __future__ import annotations

from RAG._domain import Chunk, Document, DocumentVersion, SourceMetadata
from RAG._errors import DocumentNotFoundError
from RAG.application.chunking import ChunkingConfig, TextChunker
from RAG.application.mappers import (
    to_chunk_dto,
    to_document_details_dto,
    to_document_dto,
    to_document_list_item_dto,
    to_version_dto,
)
from RAG.application.ports import Clock, DocumentStore
from RAG.application.ports import PublishedMemorySearchStore
from RAG.types import (
    AddDocumentVersionCommand,
    AgentContextDTO,
    ApproveVersionCommand,
    BuildAgentContextQuery,
    ChunkDTO,
    ChunkInput,
    CreateDocumentCommand,
    DocumentDTO,
    DocumentDetailsDTO,
    DocumentListItemDTO,
    DocumentVersionDTO,
    GetDocumentQuery,
    GetVersionChunksQuery,
    IngestTextDocumentCommand,
    IngestTextDocumentResultDTO,
    ListDocumentsQuery,
    MarkVersionProcessedCommand,
    MemorySearchResultDTO,
    PublishVersionCommand,
    RejectVersionCommand,
    SearchPublishedMemoryQuery,
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


class IngestTextDocumentUseCase:
    def __init__(self, store: DocumentStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    def execute(self, command: IngestTextDocumentCommand) -> IngestTextDocumentResultDTO:
        now = self._clock()
        document = self._store.get(command.tenant_id, command.document_id)
        if document is None:
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
        chunk_inputs = TextChunker(
            ChunkingConfig(
                max_chars=command.max_chunk_chars,
                overlap_chars=command.chunk_overlap_chars,
            )
        ).split(
            tenant_id=command.tenant_id,
            document_id=command.document_id,
            version_id=command.version_id,
            text=command.raw_text,
            visibility=command.chunk_visibility,
        )
        version.mark_processed(_to_chunks(command.tenant_id, command.version_id, chunk_inputs), now)
        document.add_version(version, now)
        self._store.save(document)

        return IngestTextDocumentResultDTO(
            document=to_document_dto(document),
            version=to_version_dto(version),
            chunks=tuple(to_chunk_dto(chunk) for chunk in version.chunks),
        )


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


class SearchPublishedMemoryUseCase:
    def __init__(self, search_store: PublishedMemorySearchStore) -> None:
        self._search_store = search_store

    def execute(self, query: SearchPublishedMemoryQuery) -> tuple[MemorySearchResultDTO, ...]:
        return tuple(
            self._search_store.search_published(
                query.tenant_id,
                query.query,
                limit=query.limit,
                source_type=query.source_type,
                visibility=query.visibility,
            )
        )


class BuildAgentContextUseCase:
    def __init__(self, search_store: PublishedMemorySearchStore) -> None:
        self._search_store = search_store

    def execute(self, query: BuildAgentContextQuery) -> AgentContextDTO:
        results = tuple(
            self._search_store.search_published(
                query.tenant_id,
                query.query,
                limit=query.limit,
                source_type=query.source_type,
                visibility=query.visibility,
            )
        )
        context_text = "\n\n".join(
            f"[{index}] {result.title} ({result.document_id}/{result.version_id}/{result.chunk_id})\n{result.text}"
            for index, result in enumerate(results, start=1)
        )
        return AgentContextDTO(query=query.query, context_text=context_text, results=results)


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
