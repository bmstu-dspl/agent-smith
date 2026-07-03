from __future__ import annotations

from datetime import datetime, timezone
from unittest import TestCase

from RAG import (
    AddDocumentVersionCommand,
    ApproveVersionCommand,
    ChunkInput,
    CreateDocumentCommand,
    InMemoryDocumentStore,
    MarkVersionProcessedCommand,
    MemoryModule,
    PublishVersionCommand,
)


class MemoryModuleTestCase(TestCase):
    def test_document_lifecycle(self) -> None:
        now = datetime(2026, 7, 3, 12, 0, 0, tzinfo=timezone.utc)
        module = MemoryModule(InMemoryDocumentStore(), now_provider=lambda: now)

        document = module.create_document(
            CreateDocumentCommand(
                document_id="doc-1",
                tenant_id="tenant-1",
                title="Architecture Notes",
                source_type="text",
                visibility="tenant",
                original_name="notes.txt",
            )
        )
        self.assertEqual(document.version_count, 0)

        version = module.add_document_version(
            AddDocumentVersionCommand(
                document_id="doc-1",
                version_id="ver-1",
                tenant_id="tenant-1",
                raw_text="This is a long-term memory note.",
                source_type="text",
                trust_level="trusted",
                original_name="notes.txt",
            )
        )
        self.assertEqual(version.review_status, "draft")

        version = module.mark_version_processed(
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
        self.assertEqual(version.chunk_count, 1)

        version = module.approve_version(
            ApproveVersionCommand(
                document_id="doc-1",
                version_id="ver-1",
                tenant_id="tenant-1",
            )
        )
        self.assertEqual(version.review_status, "approved")

        version = module.publish_version(
            PublishVersionCommand(
                document_id="doc-1",
                version_id="ver-1",
                tenant_id="tenant-1",
            )
        )
        self.assertEqual(version.review_status, "published")
        self.assertEqual(version.published_at, now)
