from __future__ import annotations

from RAG.application.ports import Clock, DocumentStore, utcnow
from RAG.application.use_cases import (
    AddDocumentVersionUseCase,
    ApproveVersionUseCase,
    CreateDocumentUseCase,
    GetDocumentUseCase,
    GetVersionChunksUseCase,
    ListDocumentsUseCase,
    MarkVersionProcessedUseCase,
    PublishVersionUseCase,
    RejectVersionUseCase,
)
from RAG.types import (
    AddDocumentVersionCommand,
    ApproveVersionCommand,
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
    ChunkDTO,
)


class MemoryUseCases:
    def __init__(self, store: DocumentStore, *, now_provider: Clock | None = None) -> None:
        clock = now_provider or utcnow
        self.create_document_uc = CreateDocumentUseCase(store, clock)
        self.add_document_version_uc = AddDocumentVersionUseCase(store, clock)
        self.mark_version_processed_uc = MarkVersionProcessedUseCase(store, clock)
        self.approve_version_uc = ApproveVersionUseCase(store, clock)
        self.reject_version_uc = RejectVersionUseCase(store, clock)
        self.publish_version_uc = PublishVersionUseCase(store, clock)
        self.get_document_uc = GetDocumentUseCase(store)
        self.list_documents_uc = ListDocumentsUseCase(store)
        self.get_version_chunks_uc = GetVersionChunksUseCase(store)

    def create_document(self, command: CreateDocumentCommand) -> DocumentDTO:
        return self.create_document_uc.execute(command)

    def add_document_version(self, command: AddDocumentVersionCommand) -> DocumentVersionDTO:
        return self.add_document_version_uc.execute(command)

    def mark_version_processed(self, command: MarkVersionProcessedCommand) -> DocumentVersionDTO:
        return self.mark_version_processed_uc.execute(command)

    def approve_version(self, command: ApproveVersionCommand) -> DocumentVersionDTO:
        return self.approve_version_uc.execute(command)

    def reject_version(self, command: RejectVersionCommand) -> DocumentVersionDTO:
        return self.reject_version_uc.execute(command)

    def publish_version(self, command: PublishVersionCommand) -> DocumentVersionDTO:
        return self.publish_version_uc.execute(command)

    def get_document(self, query: GetDocumentQuery) -> DocumentDetailsDTO:
        return self.get_document_uc.execute(query)

    def list_documents(self, query: ListDocumentsQuery) -> tuple[DocumentListItemDTO, ...]:
        return self.list_documents_uc.execute(query)

    def get_version_chunks(self, query: GetVersionChunksQuery) -> tuple[ChunkDTO, ...]:
        return self.get_version_chunks_uc.execute(query)
