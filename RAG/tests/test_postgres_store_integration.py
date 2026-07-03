from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase
from uuid import uuid4

from dotenv import dotenv_values

from DB import DatabaseConfig, Migrator, PostgresDatabase
from RAG import (
    AddDocumentVersionCommand,
    ApproveVersionCommand,
    ChunkInput,
    CreateDocumentCommand,
    MarkVersionProcessedCommand,
    MemoryModule,
    PostgresDocumentStore,
    PublishVersionCommand,
)


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
                min_pool_size=1,
                max_pool_size=4,
                session_statements=(f"SET search_path TO {cls._schema}, public",),
            )
        )
        cls._database.open()
        cls._database.execute(f'CREATE SCHEMA "{cls._schema}";')
        cls._database.apply_migrations(Migrator().load())

    @classmethod
    def tearDownClass(cls) -> None:
        cls._database.execute(f'DROP SCHEMA IF EXISTS "{cls._schema}" CASCADE;')
        cls._database.close()

    def test_memory_module_roundtrip_via_postgres(self) -> None:
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        module = MemoryModule(PostgresDocumentStore(self._database), now_provider=lambda: now)

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

        stored_document = PostgresDocumentStore(self._database).get("tenant-1", "doc-1")
        self.assertIsNotNone(stored_document)
        assert stored_document is not None
        self.assertEqual(stored_document.published_version_id, "ver-1")
        self.assertEqual(stored_document.versions["ver-1"].review_status, "published")
        self.assertEqual(len(stored_document.versions["ver-1"].chunks), 1)

        document_rows = self._database.fetch_all("SELECT document_id, published_version_id FROM rag_documents ORDER BY document_id;")
        self.assertEqual(document_rows, [{"document_id": "doc-1", "published_version_id": "ver-1"}])

        chunk_rows = self._database.fetch_all(
            "SELECT chunk_id, chunk_index, visibility FROM rag_chunks WHERE tenant_id = %s ORDER BY chunk_index;",
            ("tenant-1",),
        )
        self.assertEqual(
            chunk_rows,
            [{"chunk_id": "chunk-1", "chunk_index": 0, "visibility": "tenant"}],
        )


def _dsn_from_env(env: dict[str, str]) -> str:
    direct_dsn = os.environ.get("DB_TEST_POSTGRES_DSN")
    if direct_dsn:
        return direct_dsn

    host = os.environ.get("DB_TEST_POSTGRES_HOST") or os.environ.get("POSTGRES_HOST") or "127.0.0.1"
    port = os.environ.get("DB_TEST_POSTGRES_PORT") or env["POSTGRES_PORT"]
    user = os.environ.get("DB_TEST_POSTGRES_USER") or env["POSTGRES_USER"]
    password = os.environ.get("DB_TEST_POSTGRES_PASSWORD") or env["POSTGRES_PASSWORD"]
    database = os.environ.get("DB_TEST_POSTGRES_DB") or env["POSTGRES_DB"]
    return (
        f"postgresql://{user}:{password}"
        f"@{host}:{port}/{database}"
    )
