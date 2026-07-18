from __future__ import annotations

from RAG.application.ports import Clock, DocumentStore, EmbeddingProvider, utcnow
from RAG._errors import EmbeddingConfigurationError
from RAG.application.ports import PublishedMemorySearchStore
from RAG.application.use_cases import (
    AddDocumentVersionUseCase,
    ApproveVersionUseCase,
    ArchiveVersionUseCase,
    BuildAgentContextUseCase,
    CreateDocumentUseCase,
    DeleteDocumentUseCase,
    DeleteVersionUseCase,
    GetDocumentUseCase,
    GetVersionChunksUseCase,
    IngestTextDocumentUseCase,
    ListDocumentsUseCase,
    MarkVersionProcessedUseCase,
    PublishVersionUseCase,
    RejectVersionUseCase,
    SearchPublishedMemoryUseCase,
    VectorizeVersionUseCase,
)
from RAG.types import (
    AddDocumentVersionCommand,
    AgentContextDTO,
    ApproveVersionCommand,
    ArchiveVersionCommand,
    BuildAgentContextQuery,
    ChunkDTO,
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


class MemoryUseCases:
    def __init__(
        self,
        store: DocumentStore,
        *,
        search_store: PublishedMemorySearchStore | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        now_provider: Clock | None = None,
    ) -> None:
        clock = now_provider or utcnow
        resolved_search_store = search_store or store
        self.create_document_uc = CreateDocumentUseCase(store, clock)
        self.add_document_version_uc = AddDocumentVersionUseCase(store, clock)
        self.ingest_text_document_uc = IngestTextDocumentUseCase(store, clock, embedding_provider)
        self.mark_version_processed_uc = MarkVersionProcessedUseCase(store, clock, embedding_provider)
        self.approve_version_uc = ApproveVersionUseCase(store, clock)
        self.reject_version_uc = RejectVersionUseCase(store, clock)
        self.archive_version_uc = ArchiveVersionUseCase(store, clock)
        self.delete_version_uc = DeleteVersionUseCase(store, clock)
        self.delete_document_uc = DeleteDocumentUseCase(store)
        self.publish_version_uc = PublishVersionUseCase(store, clock)
        self.get_document_uc = GetDocumentUseCase(store)
        self.list_documents_uc = ListDocumentsUseCase(store)
        self.get_version_chunks_uc = GetVersionChunksUseCase(store)
        self.vectorize_version_uc = (
            VectorizeVersionUseCase(store, clock, embedding_provider)
            if embedding_provider is not None
            else None
        )
        self.search_published_memory_uc = SearchPublishedMemoryUseCase(
            resolved_search_store, embedding_provider
        )
        self.build_agent_context_uc = BuildAgentContextUseCase(
            resolved_search_store, embedding_provider
        )

    def create_document(self, command: CreateDocumentCommand) -> DocumentDTO:
        return self.create_document_uc.execute(command)

    def add_document_version(self, command: AddDocumentVersionCommand) -> DocumentVersionDTO:
        return self.add_document_version_uc.execute(command)

    def ingest_text_document(self, command: IngestTextDocumentCommand) -> IngestTextDocumentResultDTO:
        return self.ingest_text_document_uc.execute(command)

    def mark_version_processed(self, command: MarkVersionProcessedCommand) -> DocumentVersionDTO:
        return self.mark_version_processed_uc.execute(command)

    def approve_version(self, command: ApproveVersionCommand) -> DocumentVersionDTO:
        return self.approve_version_uc.execute(command)

    def reject_version(self, command: RejectVersionCommand) -> DocumentVersionDTO:
        return self.reject_version_uc.execute(command)

    def archive_version(self, command: ArchiveVersionCommand) -> DocumentVersionDTO:
        return self.archive_version_uc.execute(command)

    def delete_version(self, command: DeleteVersionCommand) -> None:
        self.delete_version_uc.execute(command)

    def delete_document(self, command: DeleteDocumentCommand) -> None:
        self.delete_document_uc.execute(command)

    def publish_version(self, command: PublishVersionCommand) -> DocumentVersionDTO:
        return self.publish_version_uc.execute(command)

    def get_document(self, query: GetDocumentQuery) -> DocumentDetailsDTO:
        return self.get_document_uc.execute(query)

    def list_documents(self, query: ListDocumentsQuery) -> tuple[DocumentListItemDTO, ...]:
        return self.list_documents_uc.execute(query)

    def get_version_chunks(self, query: GetVersionChunksQuery) -> tuple[ChunkDTO, ...]:
        return self.get_version_chunks_uc.execute(query)

    def vectorize_version(self, command: VectorizeVersionCommand) -> tuple[ChunkDTO, ...]:
        if self.vectorize_version_uc is None:
            raise EmbeddingConfigurationError("vectorization requires an embedding provider")
        return self.vectorize_version_uc.execute(command)

    def search_published_memory(self, query: SearchPublishedMemoryQuery) -> tuple[MemorySearchResultDTO, ...]:
        return self.search_published_memory_uc.execute(query)

    def build_agent_context(self, query: BuildAgentContextQuery) -> AgentContextDTO:
        return self.build_agent_context_uc.execute(query)
