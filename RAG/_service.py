from __future__ import annotations

from .application import MemoryUseCases
from ._repository import DocumentStore
from .types import (
    AddDocumentVersionCommand,
    AgentContextDTO,
    ApproveVersionCommand,
    BuildAgentContextQuery,
    ChunkDTO,
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


class MemoryModule:
    def __init__(self, store: DocumentStore, *, now_provider=None) -> None:
        self._use_cases = MemoryUseCases(store, now_provider=now_provider)

    def create_document(self, command: CreateDocumentCommand) -> DocumentDTO:
        return self._use_cases.create_document(command)

    def add_document_version(self, command: AddDocumentVersionCommand) -> DocumentVersionDTO:
        return self._use_cases.add_document_version(command)

    def ingest_text_document(self, command: IngestTextDocumentCommand) -> IngestTextDocumentResultDTO:
        return self._use_cases.ingest_text_document(command)

    def mark_version_processed(self, command: MarkVersionProcessedCommand) -> DocumentVersionDTO:
        return self._use_cases.mark_version_processed(command)

    def approve_version(self, command: ApproveVersionCommand) -> DocumentVersionDTO:
        return self._use_cases.approve_version(command)

    def reject_version(self, command: RejectVersionCommand) -> DocumentVersionDTO:
        return self._use_cases.reject_version(command)

    def publish_version(self, command: PublishVersionCommand) -> DocumentVersionDTO:
        return self._use_cases.publish_version(command)

    def get_document(self, query: GetDocumentQuery) -> DocumentDetailsDTO:
        return self._use_cases.get_document(query)

    def list_documents(self, query: ListDocumentsQuery) -> tuple[DocumentListItemDTO, ...]:
        return self._use_cases.list_documents(query)

    def get_version_chunks(self, query: GetVersionChunksQuery) -> tuple[ChunkDTO, ...]:
        return self._use_cases.get_version_chunks(query)

    def search_published_memory(self, query: SearchPublishedMemoryQuery) -> tuple[MemorySearchResultDTO, ...]:
        return self._use_cases.search_published_memory(query)

    def build_agent_context(self, query: BuildAgentContextQuery) -> AgentContextDTO:
        return self._use_cases.build_agent_context(query)
