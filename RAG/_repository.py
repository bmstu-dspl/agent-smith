from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from typing import Protocol

from DB import PostgresDatabase

from ._domain import Chunk, Document, DocumentVersion, SourceMetadata
from ._domain import Document


class DocumentStore(Protocol):
    def save(self, document: Document) -> None: ...

    def get(self, tenant_id: str, document_id: str) -> Document | None: ...


class InMemoryDocumentStore:
    def __init__(self) -> None:
        self._documents: dict[tuple[str, str], Document] = {}

    def save(self, document: Document) -> None:
        self._documents[(document.tenant_id, document.document_id)] = deepcopy(document)

    def get(self, tenant_id: str, document_id: str) -> Document | None:
        document = self._documents.get((tenant_id.strip(), document_id.strip()))
        return deepcopy(document) if document is not None else None


class PostgresDocumentStore:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def save(self, document: Document) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO rag_documents (
                    document_id,
                    tenant_id,
                    title,
                    source_metadata,
                    visibility,
                    published_version_id,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, document_id) DO UPDATE
                SET title = EXCLUDED.title,
                    source_metadata = EXCLUDED.source_metadata,
                    visibility = EXCLUDED.visibility,
                    published_version_id = EXCLUDED.published_version_id,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at;
                """,
                (
                    document.document_id,
                    document.tenant_id,
                    document.title,
                    _json(asdict(document.source_metadata)),
                    document.visibility,
                    document.published_version_id,
                    document.created_at,
                    document.updated_at,
                ),
            )
            connection.execute(
                "DELETE FROM rag_chunks WHERE tenant_id = %s AND version_id IN (SELECT version_id FROM rag_document_versions WHERE tenant_id = %s AND document_id = %s);",
                (document.tenant_id, document.tenant_id, document.document_id),
            )
            connection.execute(
                "DELETE FROM rag_document_versions WHERE tenant_id = %s AND document_id = %s;",
                (document.tenant_id, document.document_id),
            )

            for version in document.versions.values():
                connection.execute(
                    """
                    INSERT INTO rag_document_versions (
                        version_id,
                        tenant_id,
                        document_id,
                        raw_text,
                        source_metadata,
                        trust_level,
                        review_status,
                        created_at,
                        updated_at,
                        processed_at,
                        reviewed_at,
                        published_at
                    )
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s);
                    """,
                    (
                        version.version_id,
                        version.tenant_id,
                        version.document_id,
                        version.raw_text,
                        _json(asdict(version.source_metadata)),
                        version.trust_level,
                        version.review_status,
                        version.created_at,
                        version.updated_at,
                        version.processed_at,
                        version.reviewed_at,
                        version.published_at,
                    ),
                )

                if version.chunks:
                    with connection.cursor() as cursor:
                        cursor.executemany(
                            """
                            INSERT INTO rag_chunks (
                                chunk_id,
                                tenant_id,
                                version_id,
                                chunk_index,
                                text,
                                start_byte,
                                end_byte,
                                visibility
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                            """,
                            [
                                (
                                    chunk.chunk_id,
                                    chunk.tenant_id,
                                    chunk.version_id,
                                    chunk.index,
                                    chunk.text,
                                    chunk.start_byte,
                                    chunk.end_byte,
                                    chunk.visibility,
                                )
                                for chunk in version.chunks
                            ],
                        )

    def get(self, tenant_id: str, document_id: str) -> Document | None:
        document_row = self._database.fetch_one(
            """
            SELECT
                document_id,
                tenant_id,
                title,
                source_metadata,
                visibility,
                published_version_id,
                created_at,
                updated_at
            FROM rag_documents
            WHERE tenant_id = %s AND document_id = %s;
            """,
            (tenant_id.strip(), document_id.strip()),
        )
        if document_row is None:
            return None

        document = Document(
            document_id=str(document_row["document_id"]),
            tenant_id=str(document_row["tenant_id"]),
            title=str(document_row["title"]),
            source_metadata=SourceMetadata(**_dict(document_row["source_metadata"])),
            visibility=str(document_row["visibility"]),
            created_at=_datetime(document_row["created_at"]),
            updated_at=_datetime(document_row["updated_at"]),
            published_version_id=document_row["published_version_id"],
        )

        version_rows = self._database.fetch_all(
            """
            SELECT
                version_id,
                tenant_id,
                document_id,
                raw_text,
                source_metadata,
                trust_level,
                review_status,
                created_at,
                updated_at,
                processed_at,
                reviewed_at,
                published_at
            FROM rag_document_versions
            WHERE tenant_id = %s AND document_id = %s
            ORDER BY version_id;
            """,
            (tenant_id.strip(), document_id.strip()),
        )

        chunk_rows = self._database.fetch_all(
            """
            SELECT
                chunk_id,
                tenant_id,
                version_id,
                chunk_index,
                text,
                start_byte,
                end_byte,
                visibility
            FROM rag_chunks
            WHERE tenant_id = %s
              AND version_id IN (
                  SELECT version_id
                  FROM rag_document_versions
                  WHERE tenant_id = %s AND document_id = %s
              )
            ORDER BY version_id, chunk_index;
            """,
            (tenant_id.strip(), tenant_id.strip(), document_id.strip()),
        )
        chunks_by_version: dict[str, list[Chunk]] = {}
        for row in chunk_rows:
            chunk = Chunk(
                chunk_id=str(row["chunk_id"]),
                tenant_id=str(row["tenant_id"]),
                version_id=str(row["version_id"]),
                index=int(row["chunk_index"]),
                text=str(row["text"]),
                start_byte=int(row["start_byte"]),
                end_byte=int(row["end_byte"]),
                visibility=str(row["visibility"]),
            )
            chunks_by_version.setdefault(chunk.version_id, []).append(chunk)

        for row in version_rows:
            version_id = str(row["version_id"])
            document.versions[version_id] = DocumentVersion(
                version_id=version_id,
                document_id=str(row["document_id"]),
                tenant_id=str(row["tenant_id"]),
                raw_text=str(row["raw_text"]),
                source_metadata=SourceMetadata(**_dict(row["source_metadata"])),
                trust_level=str(row["trust_level"]),
                review_status=str(row["review_status"]),
                created_at=_datetime(row["created_at"]),
                updated_at=_datetime(row["updated_at"]),
                processed_at=_optional_datetime(row["processed_at"]),
                reviewed_at=_optional_datetime(row["reviewed_at"]),
                published_at=_optional_datetime(row["published_at"]),
                chunks=chunks_by_version.get(version_id, []),
            )

        return document


def _json(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    raise TypeError(f"unsupported json value type: {type(value)!r}")


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    raise TypeError(f"unsupported datetime value type: {type(value)!r}")


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return _datetime(value)
