from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase
from uuid import uuid4

from dotenv import dotenv_values

from sqlalchemy import select
from sqlalchemy.schema import CreateSchema, DropSchema

from DB import DatabaseConfig, PostgresDatabase
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
from RAG._models import ChunkModel, DocumentModel


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

        with self._database.session() as session:
            document_rows = session.execute(
                select(DocumentModel.document_id, DocumentModel.published_version_id)
                .order_by(DocumentModel.document_id)
            ).mappings().all()
            chunk_rows = session.execute(
                select(ChunkModel.chunk_id, ChunkModel.chunk_index, ChunkModel.visibility)
                .where(ChunkModel.tenant_id == "tenant-1")
                .order_by(ChunkModel.chunk_index)
            ).mappings().all()
        self.assertEqual([dict(row) for row in document_rows], [{"document_id": "doc-1", "published_version_id": "ver-1"}])
        self.assertEqual(
            [dict(row) for row in chunk_rows],
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
