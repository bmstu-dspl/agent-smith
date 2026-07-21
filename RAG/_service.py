from __future__ import annotations

from ._file_parser import extract_file_text
from ._repository import DocumentStore
from .application import MemoryUseCases
from .application.ports import EmbeddingProvider
from .types import (
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
    IngestFileDocumentCommand,
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


class MemoryModule:
    def __init__(
        self,
        store: DocumentStore,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        now_provider=None,
    ) -> None:
        self._use_cases = MemoryUseCases(
            store,
            embedding_provider=embedding_provider,
            now_provider=now_provider,
        )

    def create_document(self, command: CreateDocumentCommand) -> DocumentDTO:
        return self._use_cases.create_document(command)

    def add_document_version(self, command: AddDocumentVersionCommand) -> DocumentVersionDTO:
        return self._use_cases.add_document_version(command)

    def ingest_text_document(self, command: IngestTextDocumentCommand) -> IngestTextDocumentResultDTO:
        return self._use_cases.ingest_text_document(command)

    def ingest_file_document(
        self, command: IngestFileDocumentCommand
    ) -> IngestTextDocumentResultDTO:
        extracted = extract_file_text(command.file_name, command.file_content)
        return self.ingest_text_document(
            IngestTextDocumentCommand(
                document_id=command.document_id,
                version_id=command.version_id,
                tenant_id=command.tenant_id,
                title=command.title,
                raw_text=extracted.text,
                source_type=extracted.source_type,
                visibility=command.visibility,
                trust_level=command.trust_level,
                chunk_visibility=command.chunk_visibility,
                external_ref=command.external_ref,
                original_name=extracted.original_name,
                max_chunk_chars=command.max_chunk_chars,
                chunk_overlap_chars=command.chunk_overlap_chars,
            )
        )

    def mark_version_processed(self, command: MarkVersionProcessedCommand) -> DocumentVersionDTO:
        return self._use_cases.mark_version_processed(command)

    def approve_version(self, command: ApproveVersionCommand) -> DocumentVersionDTO:
        return self._use_cases.approve_version(command)

    def reject_version(self, command: RejectVersionCommand) -> DocumentVersionDTO:
        return self._use_cases.reject_version(command)

    def archive_version(self, command: ArchiveVersionCommand) -> DocumentVersionDTO:
        return self._use_cases.archive_version(command)

    def delete_version(self, command: DeleteVersionCommand) -> None:
        self._use_cases.delete_version(command)

    def delete_document(self, command: DeleteDocumentCommand) -> None:
        self._use_cases.delete_document(command)

    def publish_version(self, command: PublishVersionCommand) -> DocumentVersionDTO:
        return self._use_cases.publish_version(command)

    def get_document(self, query: GetDocumentQuery) -> DocumentDetailsDTO:
        return self._use_cases.get_document(query)

    def list_documents(self, query: ListDocumentsQuery) -> tuple[DocumentListItemDTO, ...]:
        return self._use_cases.list_documents(query)

    def get_version_chunks(self, query: GetVersionChunksQuery) -> tuple[ChunkDTO, ...]:
        return self._use_cases.get_version_chunks(query)

    def vectorize_version(self, command: VectorizeVersionCommand) -> tuple[ChunkDTO, ...]:
        return self._use_cases.vectorize_version(command)

    def search_published_memory(self, query: SearchPublishedMemoryQuery) -> tuple[MemorySearchResultDTO, ...]:
        return self._use_cases.search_published_memory(query)

    def build_agent_context(self, query: BuildAgentContextQuery) -> AgentContextDTO:
        return self._use_cases.build_agent_context(query)
