from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy.schema import CreateSchema, DropSchema

from DB import DatabaseConfig, PostgresDatabase
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
    GetDocumentQuery,
    GetVersionChunksQuery,
    IngestTextDocumentCommand,
    ListDocumentsQuery,
    MarkVersionProcessedCommand,
    PostgresDocumentStore,
    PublishVersionCommand,
    SearchPublishedMemoryQuery,
)
from RAG.application import MemoryUseCases


class PostgresDocumentStoreIntegrationTestCase(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        env_path = Path(__file__).resolve().parents[2] / ".env"
        env = {
            key: value
            for key, value in dotenv_values(env_path).items()
            if value is not None
        }
        cls._schema = f"test_rag_{uuid4().hex[:12]}"
        cls._database = PostgresDatabase(
            DatabaseConfig(
                dsn=_dsn_from_env(env),
                pool_size=4,
                max_overflow=0,
                session_statements=(f"SET search_path TO {cls._schema}, public",),
            )
        )
        cls._database.open()
        with cls._database.engine.begin() as connection:
            connection.execute(CreateSchema(cls._schema))
        cls._database.migrate()

    @classmethod
    def tearDownClass(cls) -> None:
        with cls._database.engine.begin() as connection:
            connection.execute(DropSchema(cls._schema, cascade=True, if_exists=True))
        cls._database.close()

    def test_memory_use_cases_roundtrip_via_postgres(self) -> None:
        now = datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc)
        use_cases = MemoryUseCases(PostgresDocumentStore(self._database), now_provider=lambda: now)

        document = use_cases.create_document(
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

        version = use_cases.add_document_version(
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

        use_cases.mark_version_processed(
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
        use_cases.approve_version(
            ApproveVersionCommand(
                document_id="doc-1",
                version_id="ver-1",
                tenant_id="tenant-1",
            )
        )
        published = use_cases.publish_version(
            PublishVersionCommand(
                document_id="doc-1",
                version_id="ver-1",
                tenant_id="tenant-1",
            )
        )
        self.assertEqual(published.review_status, "published")

        details = use_cases.get_document(GetDocumentQuery(tenant_id="tenant-1", document_id="doc-1"))
        self.assertEqual(details.document.published_version_id, "ver-1")
        self.assertEqual(details.versions[0].review_status, "published")

        chunks = use_cases.get_version_chunks(
            GetVersionChunksQuery(
                tenant_id="tenant-1",
                document_id="doc-1",
                version_id="ver-1",
            )
        )
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_id, "chunk-1")

        documents = use_cases.list_documents(
            ListDocumentsQuery(
                tenant_id="tenant-1",
                review_status="published",
                source_type="text",
                visibility="tenant",
            )
        )
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].document_id, "doc-1")

        search_results = use_cases.search_published_memory(
            SearchPublishedMemoryQuery(tenant_id="tenant-1", query="long-term memory")
        )
        self.assertEqual(len(search_results), 1)
        self.assertEqual(search_results[0].chunk_id, "chunk-1")
        self.assertGreaterEqual(search_results[0].score, 0)
        self.assertEqual(
            use_cases.search_published_memory(SearchPublishedMemoryQuery(tenant_id="tenant-1", query="%")),
            (),
        )

        context = use_cases.build_agent_context(
            BuildAgentContextQuery(tenant_id="tenant-1", query="long-term memory")
        )
        self.assertEqual(len(context.results), 1)
        self.assertIn("doc-1/ver-1/chunk-1", context.context_text)

    def test_ingest_text_document_via_postgres(self) -> None:
        now = datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc)
        use_cases = MemoryUseCases(PostgresDocumentStore(self._database), now_provider=lambda: now)

        result = use_cases.ingest_text_document(
            IngestTextDocumentCommand(
                document_id="doc-ingest",
                version_id="ver-ingest",
                tenant_id="tenant-1",
                title="Ingested Notes",
                raw_text="First PostgreSQL memory fact. Second PostgreSQL memory fact. Third PostgreSQL memory fact.",
                trust_level="trusted",
                max_chunk_chars=45,
                chunk_overlap_chars=8,
            )
        )

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

    def test_postgres_store_rejects_stale_aggregate(self) -> None:
        now = datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc)
        store = PostgresDocumentStore(self._database)
        use_cases = MemoryUseCases(store, now_provider=lambda: now)
        use_cases.create_document(
            CreateDocumentCommand("doc-concurrent", "tenant-1", "Title", "text", "tenant")
        )
        first = store.get("tenant-1", "doc-concurrent")
        stale = store.get("tenant-1", "doc-concurrent")
        assert first is not None and stale is not None
        first.title = "First update"
        store.save(first)

        stale.title = "Lost update"
        with self.assertRaises(ConcurrentModificationError):
            store.save(stale)

        use_cases.delete_document(DeleteDocumentCommand("doc-concurrent", "tenant-1"))
        self.assertIsNone(store.get("tenant-1", "doc-concurrent"))

    def test_duplicate_create_preserves_existing_document(self) -> None:
        now = datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc)
        use_cases = MemoryUseCases(PostgresDocumentStore(self._database), now_provider=lambda: now)
        command = CreateDocumentCommand(
            "doc-duplicate", "tenant-1", "Original title", "text", "tenant"
        )
        use_cases.create_document(command)
        use_cases.add_document_version(
            AddDocumentVersionCommand(
                "doc-duplicate", "ver-duplicate", "tenant-1", "Memory", "text", "trusted"
            )
        )

        with self.assertRaises(DocumentAlreadyExistsError):
            use_cases.create_document(command)

        details = use_cases.get_document(GetDocumentQuery("tenant-1", "doc-duplicate"))
        self.assertEqual(details.document.title, "Original title")
        self.assertEqual([version.version_id for version in details.versions], ["ver-duplicate"])

    def test_archive_and_delete_lifecycle_via_postgres(self) -> None:
        now = datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc)
        store = PostgresDocumentStore(self._database)
        use_cases = MemoryUseCases(store, now_provider=lambda: now)
        use_cases.create_document(
            CreateDocumentCommand("doc-lifecycle", "tenant-1", "Lifecycle", "text", "tenant")
        )
        use_cases.add_document_version(
            AddDocumentVersionCommand(
                "doc-lifecycle", "ver-lifecycle", "tenant-1", "Memory", "text", "trusted"
            )
        )

        archived = use_cases.archive_version(
            ArchiveVersionCommand("doc-lifecycle", "ver-lifecycle", "tenant-1")
        )
        self.assertEqual(archived.review_status, "archived")

        use_cases.delete_version(
            DeleteVersionCommand("doc-lifecycle", "ver-lifecycle", "tenant-1")
        )
        details = use_cases.get_document(GetDocumentQuery("tenant-1", "doc-lifecycle"))
        self.assertEqual(details.versions, ())

        use_cases.delete_document(DeleteDocumentCommand("doc-lifecycle", "tenant-1"))
        self.assertIsNone(store.get("tenant-1", "doc-lifecycle"))


def _dsn_from_env(env: dict[str, str]) -> str:
    direct_dsn = os.environ.get("DB_TEST_POSTGRES_DSN")
    if direct_dsn:
        return direct_dsn

    for key in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_PORT"):
        if not env.get(key):
            raise ValueError(f"missing {key} in .env")

    host = os.environ.get("DB_TEST_POSTGRES_HOST") or os.environ.get("POSTGRES_HOST") or "127.0.0.1"
    port = os.environ.get("DB_TEST_POSTGRES_PORT") or env["POSTGRES_PORT"]
    user = os.environ.get("DB_TEST_POSTGRES_USER") or env["POSTGRES_USER"]
    password = os.environ.get("DB_TEST_POSTGRES_PASSWORD") or env["POSTGRES_PASSWORD"]
    database = os.environ.get("DB_TEST_POSTGRES_DB") or env["POSTGRES_DB"]
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"
