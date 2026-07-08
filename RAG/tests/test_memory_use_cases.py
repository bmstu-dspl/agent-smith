from __future__ import annotations

from datetime import datetime, timezone
from unittest import TestCase

from RAG import (
    AddDocumentVersionCommand,
    ApproveVersionCommand,
    ChunkInput,
    CreateDocumentCommand,
    GetDocumentQuery,
    GetVersionChunksQuery,
    InMemoryDocumentStore,
    ListDocumentsQuery,
    MarkVersionProcessedCommand,
    PublishVersionCommand,
    RejectVersionCommand,
)
from RAG.application import MemoryUseCases


class MemoryUseCasesTestCase(TestCase):
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
