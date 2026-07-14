from __future__ import annotations

from datetime import datetime, timezone
from unittest import TestCase

from RAG import (
    AddDocumentVersionCommand,
    ApproveVersionCommand,
    ArchiveVersionCommand,
    BuildAgentContextQuery,
    ChunkInput,
    ConcurrentModificationError,
    CreateDocumentCommand,
    DeleteDocumentCommand,
    DeleteVersionCommand,
    DocumentAlreadyExistsError,
    DocumentNotFoundError,
    GetDocumentQuery,
    GetVersionChunksQuery,
    InMemoryDocumentStore,
    IngestTextDocumentCommand,
    ListDocumentsQuery,
    MarkVersionProcessedCommand,
    PublishVersionCommand,
    RejectVersionCommand,
    SearchPublishedMemoryQuery,
)
from RAG.application import MemoryUseCases


class MemoryUseCasesTestCase(TestCase):
    def test_ingest_text_document_creates_processed_version_and_chunks(self) -> None:
        now = datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc)
        use_cases = MemoryUseCases(InMemoryDocumentStore(), now_provider=lambda: now)

        result = use_cases.ingest_text_document(
            IngestTextDocumentCommand(
                document_id="doc-ingest",
                version_id="ver-ingest",
                tenant_id="tenant-1",
                title="Ingested Notes",
                raw_text="First memory fact. Second memory fact. Third memory fact.",
                trust_level="trusted",
                max_chunk_chars=35,
                chunk_overlap_chars=5,
            )
        )

        self.assertEqual(result.document.document_id, "doc-ingest")
        self.assertEqual(result.version.review_status, "processed")
        self.assertGreater(len(result.chunks), 1)

        chunks = use_cases.get_version_chunks(
            GetVersionChunksQuery(
                tenant_id="tenant-1",
                document_id="doc-ingest",
                version_id="ver-ingest",
            )
        )
        self.assertEqual(chunks, result.chunks)

    def test_command_and_query_use_cases(self) -> None:
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        use_cases = MemoryUseCases(InMemoryDocumentStore(), now_provider=lambda: now)

        document = use_cases.create_document(
            CreateDocumentCommand(
                document_id="doc-1",
                tenant_id="tenant-1",
                title="Architecture Notes",
                source_type="text",
                visibility="tenant",
            )
        )
        self.assertEqual(document.version_count, 0)

        version = use_cases.add_document_version(
            AddDocumentVersionCommand(
                document_id="doc-1",
                version_id="ver-1",
                tenant_id="tenant-1",
                raw_text="This is a long-term memory note.",
                source_type="text",
                trust_level="trusted",
            )
        )
        self.assertEqual(version.review_status, "draft")

        version = use_cases.mark_version_processed(
            MarkVersionProcessedCommand(
                document_id="doc-1",
                version_id="ver-1",
                tenant_id="tenant-1",
                chunks=(
                    ChunkInput(
                        chunk_id="chunk-1",
                        index=0,
                        text="This is a long-term memory note.",
                        start_byte=0,
                        end_byte=32,
                        visibility="tenant",
                    ),
                ),
            )
        )
        self.assertEqual(version.review_status, "processed")

        chunks = use_cases.get_version_chunks(
            GetVersionChunksQuery(
                tenant_id="tenant-1",
                document_id="doc-1",
                version_id="ver-1",
            )
        )
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_id, "chunk-1")

        version = use_cases.approve_version(
            ApproveVersionCommand(
                document_id="doc-1",
                version_id="ver-1",
                tenant_id="tenant-1",
            )
        )
        self.assertEqual(version.review_status, "approved")

        version = use_cases.publish_version(
            PublishVersionCommand(
                document_id="doc-1",
                version_id="ver-1",
                tenant_id="tenant-1",
            )
        )
        self.assertEqual(version.review_status, "published")

        details = use_cases.get_document(GetDocumentQuery(tenant_id="tenant-1", document_id="doc-1"))
        self.assertEqual(details.document.published_version_id, "ver-1")
        self.assertEqual(len(details.versions), 1)

        documents = use_cases.list_documents(ListDocumentsQuery(tenant_id="tenant-1", review_status="published"))
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].document_id, "doc-1")

        search_results = use_cases.search_published_memory(
            SearchPublishedMemoryQuery(tenant_id="tenant-1", query="long-term memory")
        )
        self.assertEqual(len(search_results), 1)
        self.assertEqual(search_results[0].chunk_id, "chunk-1")

        context = use_cases.build_agent_context(
            BuildAgentContextQuery(tenant_id="tenant-1", query="long-term memory")
        )
        self.assertEqual(len(context.results), 1)
        self.assertIn("Architecture Notes", context.context_text)

    def test_reject_version_use_case(self) -> None:
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        use_cases = MemoryUseCases(InMemoryDocumentStore(), now_provider=lambda: now)

        use_cases.create_document(
            CreateDocumentCommand(
                document_id="doc-1",
                tenant_id="tenant-1",
                title="Draft",
                source_type="text",
                visibility="tenant",
            )
        )
        use_cases.add_document_version(
            AddDocumentVersionCommand(
                document_id="doc-1",
                version_id="ver-1",
                tenant_id="tenant-1",
                raw_text="Draft text",
                source_type="text",
                trust_level="low",
            )
        )
        use_cases.mark_version_processed(
            MarkVersionProcessedCommand(
                document_id="doc-1",
                version_id="ver-1",
                tenant_id="tenant-1",
                chunks=(
                    ChunkInput(
                        chunk_id="chunk-1",
                        index=0,
                        text="Draft text",
                        start_byte=0,
                        end_byte=10,
                        visibility="tenant",
                    ),
                ),
            )
        )

        version = use_cases.reject_version(
            RejectVersionCommand(
                document_id="doc-1",
                version_id="ver-1",
                tenant_id="tenant-1",
            )
        )

        self.assertEqual(version.review_status, "rejected")

    def test_duplicate_document_is_rejected_without_data_loss(self) -> None:
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        use_cases = MemoryUseCases(InMemoryDocumentStore(), now_provider=lambda: now)
        command = CreateDocumentCommand("doc-1", "tenant-1", "Title", "text", "tenant")
        use_cases.create_document(command)
        use_cases.add_document_version(
            AddDocumentVersionCommand("doc-1", "ver-1", "tenant-1", "Text", "text", "trusted")
        )

        with self.assertRaises(DocumentAlreadyExistsError):
            use_cases.create_document(command)

        details = use_cases.get_document(GetDocumentQuery("tenant-1", "doc-1"))
        self.assertEqual(len(details.versions), 1)

    def test_archive_and_delete_lifecycle(self) -> None:
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        use_cases = MemoryUseCases(InMemoryDocumentStore(), now_provider=lambda: now)
        self._create_published_document(use_cases)

        archived = use_cases.archive_version(ArchiveVersionCommand("doc-1", "ver-1", "tenant-1"))
        self.assertEqual(archived.review_status, "archived")
        self.assertIsNone(use_cases.get_document(GetDocumentQuery("tenant-1", "doc-1")).document.published_version_id)

        use_cases.delete_version(DeleteVersionCommand("doc-1", "ver-1", "tenant-1"))
        self.assertEqual(use_cases.get_document(GetDocumentQuery("tenant-1", "doc-1")).versions, ())
        use_cases.delete_document(DeleteDocumentCommand("doc-1", "tenant-1"))
        with self.assertRaises(DocumentNotFoundError):
            use_cases.get_document(GetDocumentQuery("tenant-1", "doc-1"))

    def test_query_validation_and_context_budget(self) -> None:
        with self.assertRaises(ValueError):
            ListDocumentsQuery(tenant_id="tenant-1", limit=0)
        with self.assertRaises(ValueError):
            SearchPublishedMemoryQuery(tenant_id="tenant-1", query=" ")

        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        use_cases = MemoryUseCases(InMemoryDocumentStore(), now_provider=lambda: now)
        self._create_published_document(use_cases)
        context = use_cases.build_agent_context(
            BuildAgentContextQuery("tenant-1", "long-term memory", max_context_chars=50)
        )
        self.assertLessEqual(len(context.context_text), 50)

    def test_in_memory_store_rejects_stale_aggregate(self) -> None:
        store = InMemoryDocumentStore()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        use_cases = MemoryUseCases(store, now_provider=lambda: now)
        use_cases.create_document(CreateDocumentCommand("doc-1", "tenant-1", "Title", "text", "tenant"))
        first = store.get("tenant-1", "doc-1")
        stale = store.get("tenant-1", "doc-1")
        assert first is not None and stale is not None
        first.title = "Changed"
        store.save(first)

        stale.title = "Lost update"
        with self.assertRaises(ConcurrentModificationError):
            store.save(stale)

    def _create_published_document(self, use_cases: MemoryUseCases) -> None:
        use_cases.create_document(CreateDocumentCommand("doc-1", "tenant-1", "Title", "text", "tenant"))
        use_cases.add_document_version(
            AddDocumentVersionCommand(
                "doc-1",
                "ver-1",
                "tenant-1",
                "Long-term memory text",
                "text",
                "trusted",
            )
        )
        use_cases.mark_version_processed(
            MarkVersionProcessedCommand(
                "doc-1",
                "ver-1",
                "tenant-1",
                (ChunkInput("chunk-1", 0, "Long-term memory text", 0, 21, "tenant"),),
            )
        )
        use_cases.approve_version(ApproveVersionCommand("doc-1", "ver-1", "tenant-1"))
        use_cases.publish_version(PublishVersionCommand("doc-1", "ver-1", "tenant-1"))
