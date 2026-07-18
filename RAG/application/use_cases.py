from __future__ import annotations

from dataclasses import replace
import math

from RAG._embedding_constants import EMBEDDING_DIMENSIONS
from RAG._domain import Chunk, Document, DocumentVersion, SourceMetadata
from RAG._errors import DocumentAlreadyExistsError, DocumentNotFoundError, EmbeddingConfigurationError
from RAG.application.chunking import ChunkingConfig, TextChunker
from RAG.application.mappers import (
    to_chunk_dto,
    to_document_details_dto,
    to_document_dto,
    to_document_list_item_dto,
    to_version_dto,
)
from RAG.application.ports import Clock, DocumentStore, EmbeddingProvider
from RAG.application.ports import PublishedMemorySearchStore
from RAG.types import (
    AddDocumentVersionCommand,
    AgentContextDTO,
    ApproveVersionCommand,
    ArchiveVersionCommand,
    BuildAgentContextQuery,
    ChunkDTO,
    ChunkInput,
    CreateDocumentCommand,
    DeleteDocumentCommand,
    DeleteVersionCommand,
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
    VectorizeVersionCommand,
)


class CreateDocumentUseCase:
    def __init__(self, store: DocumentStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    def execute(self, command: CreateDocumentCommand) -> DocumentDTO:
        if self._store.get(command.tenant_id, command.document_id) is not None:
            raise DocumentAlreadyExistsError(f"document {command.document_id!r} already exists")
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
    def __init__(
        self,
        store: DocumentStore,
        clock: Clock,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._store = store
        self._clock = clock
        self._embedding_provider = embedding_provider

    def execute(self, command: MarkVersionProcessedCommand) -> DocumentVersionDTO:
        document = _load_document(self._store, command.tenant_id, command.document_id)
        version = document.get_version(command.version_id)
        now = self._clock()
        chunks = _to_chunks(command.tenant_id, command.version_id, command.chunks)
        if self._embedding_provider is not None:
            chunks = _vectorize_chunks(chunks, self._embedding_provider, now)
        version.mark_processed(chunks, now)
        self._store.save(document)
        return to_version_dto(version)


class IngestTextDocumentUseCase:
    def __init__(
        self,
        store: DocumentStore,
        clock: Clock,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._store = store
        self._clock = clock
        self._embedding_provider = embedding_provider

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
        chunks = _to_chunks(command.tenant_id, command.version_id, chunk_inputs)
        if self._embedding_provider is not None:
            chunks = _vectorize_chunks(chunks, self._embedding_provider, now)
        version.mark_processed(chunks, now)
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


class ArchiveVersionUseCase:
    def __init__(self, store: DocumentStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    def execute(self, command: ArchiveVersionCommand) -> DocumentVersionDTO:
        document = _load_document(self._store, command.tenant_id, command.document_id)
        version = document.archive_version(command.version_id, self._clock())
        self._store.save(document)
        return to_version_dto(version)


class DeleteVersionUseCase:
    def __init__(self, store: DocumentStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    def execute(self, command: DeleteVersionCommand) -> None:
        document = _load_document(self._store, command.tenant_id, command.document_id)
        document.delete_version(command.version_id, self._clock())
        self._store.save(document)


class DeleteDocumentUseCase:
    def __init__(self, store: DocumentStore) -> None:
        self._store = store

    def execute(self, command: DeleteDocumentCommand) -> None:
        if not self._store.delete(command.tenant_id, command.document_id):
            raise DocumentNotFoundError(f"document {command.document_id!r} was not found")


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


class VectorizeVersionUseCase:
    def __init__(self, store: DocumentStore, clock: Clock, provider: EmbeddingProvider) -> None:
        self._store = store
        self._clock = clock
        self._provider = provider

    def execute(self, command: VectorizeVersionCommand) -> tuple[ChunkDTO, ...]:
        document = _load_document(self._store, command.tenant_id, command.document_id)
        version = document.get_version(command.version_id)
        if not version.chunks:
            raise EmbeddingConfigurationError("version has no chunks to vectorize")
        now = self._clock()
        chunks = _vectorize_chunks(version.chunks, self._provider, now)
        document.vectorize_version(command.version_id, chunks, now)
        self._store.save(document)
        return tuple(to_chunk_dto(chunk) for chunk in version.chunks)


class SearchPublishedMemoryUseCase:
    def __init__(
        self,
        search_store: PublishedMemorySearchStore,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._search_store = search_store
        self._embedding_provider = embedding_provider

    def execute(self, query: SearchPublishedMemoryQuery) -> tuple[MemorySearchResultDTO, ...]:
        query_embedding = _query_embedding(self._embedding_provider, query.query, query.retrieval_mode)
        return tuple(
            self._search_store.search_published(
                query.tenant_id,
                query.query,
                limit=query.limit,
                source_type=query.source_type,
                visibility=query.visibility,
                query_embedding=query_embedding,
                query_embedding_model=(
                    self._embedding_provider.model if query_embedding is not None else None
                ),
                retrieval_mode=query.retrieval_mode,
            )
        )


class BuildAgentContextUseCase:
    def __init__(
        self,
        search_store: PublishedMemorySearchStore,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._search_store = search_store
        self._embedding_provider = embedding_provider

    def execute(self, query: BuildAgentContextQuery) -> AgentContextDTO:
        query_embedding = _query_embedding(self._embedding_provider, query.query, query.retrieval_mode)
        results = tuple(
            self._search_store.search_published(
                query.tenant_id,
                query.query,
                limit=query.limit,
                source_type=query.source_type,
                visibility=query.visibility,
                query_embedding=query_embedding,
                query_embedding_model=(
                    self._embedding_provider.model if query_embedding is not None else None
                ),
                retrieval_mode=query.retrieval_mode,
            )
        )
        context_text, included_results = _build_bounded_context(results, query.max_context_chars)
        return AgentContextDTO(query=query.query, context_text=context_text, results=included_results)


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
            embedding=item.embedding,
            embedding_model=item.embedding_model,
            embedded_at=item.embedded_at,
        )
        for item in chunks
    ]


def _vectorize_chunks(
    chunks: list[Chunk],
    provider: EmbeddingProvider,
    now,
) -> list[Chunk]:
    vectors = provider.embed_documents(tuple(chunk.text for chunk in chunks))
    if len(vectors) != len(chunks):
        raise EmbeddingConfigurationError("embedding count does not match chunk count")
    vectors = tuple(_validate_provider_vector(vector, provider) for vector in vectors)
    return [
        replace(
            chunk,
            embedding=vector,
            embedding_model=provider.model,
            embedded_at=now,
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]


def _query_embedding(
    provider: EmbeddingProvider | None,
    query: str,
    retrieval_mode: str,
) -> tuple[float, ...] | None:
    if retrieval_mode == "lexical":
        return None
    if provider is None:
        if retrieval_mode == "semantic":
            raise EmbeddingConfigurationError("semantic retrieval requires an embedding provider")
        return None
    return _validate_provider_vector(provider.embed_query(query), provider)


def _validate_provider_vector(
    vector: tuple[float, ...],
    provider: EmbeddingProvider,
) -> tuple[float, ...]:
    if provider.dimensions != EMBEDDING_DIMENSIONS:
        raise EmbeddingConfigurationError(
            f"embedding provider dimensions must be {EMBEDDING_DIMENSIONS}"
        )
    if len(vector) != provider.dimensions:
        raise EmbeddingConfigurationError("embedding vector has unexpected dimensions")
    if not all(math.isfinite(value) for value in vector):
        raise EmbeddingConfigurationError("embedding vector contains a non-finite value")
    if not any(value != 0 for value in vector):
        raise EmbeddingConfigurationError("embedding vector must not be zero")
    return vector


def _build_bounded_context(
    results: tuple[MemorySearchResultDTO, ...],
    max_chars: int,
) -> tuple[str, tuple[MemorySearchResultDTO, ...]]:
    entries: list[str] = []
    included: list[MemorySearchResultDTO] = []
    used = 0
    for index, result in enumerate(results, start=1):
        separator = "\n\n" if entries else ""
        entry = f"[{index}] {result.title} ({result.document_id}/{result.version_id}/{result.chunk_id})\n{result.text}"
        remaining = max_chars - used - len(separator)
        if remaining <= 0:
            break
        if len(entry) > remaining:
            entry = entry[:remaining].rstrip()
        entries.append(entry)
        included.append(result)
        used += len(separator) + len(entry)
        if len(entry) == remaining:
            break
    return "\n\n".join(entries), tuple(included)
