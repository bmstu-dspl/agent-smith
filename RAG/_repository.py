from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from typing import Protocol

from DB import PostgresDatabase

from ._domain import Chunk, Document, DocumentVersion, SourceMetadata
from .types import MemorySearchResultDTO


class DocumentStore(Protocol):
    def save(self, document: Document) -> None: ...

    def get(self, tenant_id: str, document_id: str) -> Document | None: ...

    def list(
        self,
        tenant_id: str,
        *,
        review_status: str | None = None,
        visibility: str | None = None,
        source_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Document]: ...


class PublishedMemorySearchStore(Protocol):
    def search_published(
        self,
        tenant_id: str,
        query: str,
        *,
        limit: int = 8,
        source_type: str | None = None,
        visibility: str | None = None,
    ) -> list[MemorySearchResultDTO]: ...


class InMemoryDocumentStore:
    def __init__(self) -> None:
        self._documents: dict[tuple[str, str], Document] = {}

    def save(self, document: Document) -> None:
        self._documents[(document.tenant_id, document.document_id)] = deepcopy(document)

    def get(self, tenant_id: str, document_id: str) -> Document | None:
        document = self._documents.get((tenant_id.strip(), document_id.strip()))
        return deepcopy(document) if document is not None else None

    def list(
        self,
        tenant_id: str,
        *,
        review_status: str | None = None,
        visibility: str | None = None,
        source_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Document]:
        documents = [
            document
            for (document_tenant_id, _), document in self._documents.items()
            if document_tenant_id == tenant_id.strip()
        ]
        if visibility is not None:
            documents = [document for document in documents if document.visibility == visibility.strip().lower()]
        if source_type is not None:
            documents = [
                document
                for document in documents
                if document.source_metadata.source_type == source_type.strip().lower()
            ]
        if review_status is not None:
            normalized_status = review_status.strip().lower()
            documents = [
                document
                for document in documents
                if any(version.review_status == normalized_status for version in document.versions.values())
            ]

        documents.sort(key=lambda document: document.created_at)
        return deepcopy(documents[offset : offset + limit])

    def search_published(
        self,
        tenant_id: str,
        query: str,
        *,
        limit: int = 8,
        source_type: str | None = None,
        visibility: str | None = None,
    ) -> list[MemorySearchResultDTO]:
        normalized_query = query.strip().lower()
        if not normalized_query:
            return []

        results: list[MemorySearchResultDTO] = []
        for document in self.list(
            tenant_id,
            review_status="published",
            source_type=source_type,
            visibility=visibility,
            limit=10_000,
        ):
            if document.published_version_id is None:
                continue
            version = document.versions.get(document.published_version_id)
            if version is None or version.review_status != "published":
                continue
            for chunk in version.chunks:
                text = chunk.text.lower()
                if normalized_query not in text:
                    continue
                results.append(
                    MemorySearchResultDTO(
                        chunk_id=chunk.chunk_id,
                        document_id=document.document_id,
                        version_id=version.version_id,
                        tenant_id=document.tenant_id,
                        title=document.title,
                        text=chunk.text,
                        score=float(text.count(normalized_query)),
                        chunk_index=chunk.index,
                        source_type=document.source_metadata.source_type,
                        trust_level=version.trust_level,
                        visibility=chunk.visibility,
                    )
                )

        results.sort(key=lambda item: (-item.score, item.document_id, item.chunk_index))
        return results[:limit]


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
                """
                DELETE FROM rag_chunks
                WHERE tenant_id = %s
                  AND version_id IN (
                      SELECT version_id
                      FROM rag_document_versions
                      WHERE tenant_id = %s AND document_id = %s
                  );
                """,
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

        return self._hydrate_document(document_row)

    def list(
        self,
        tenant_id: str,
        *,
        review_status: str | None = None,
        visibility: str | None = None,
        source_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Document]:
        filters: list[str] = ["d.tenant_id = %s"]
        parameters: list[object] = [tenant_id.strip()]

        if visibility is not None:
            filters.append("d.visibility = %s")
            parameters.append(visibility.strip().lower())
        if source_type is not None:
            filters.append("d.source_metadata->>'source_type' = %s")
            parameters.append(source_type.strip().lower())
        if review_status is not None:
            filters.append(
                """
                EXISTS (
                    SELECT 1
                    FROM rag_document_versions AS v
                    WHERE v.tenant_id = d.tenant_id
                      AND v.document_id = d.document_id
                      AND v.review_status = %s
                )
                """
            )
            parameters.append(review_status.strip().lower())

        parameters.extend([limit, offset])
        rows = self._database.fetch_all(
            f"""
            SELECT
                d.document_id,
                d.tenant_id,
                d.title,
                d.source_metadata,
                d.visibility,
                d.published_version_id,
                d.created_at,
                d.updated_at
            FROM rag_documents AS d
            WHERE {" AND ".join(filters)}
            ORDER BY d.created_at, d.document_id
            LIMIT %s OFFSET %s;
            """,
            tuple(parameters),
        )

        return [self._hydrate_document(row) for row in rows]

    def search_published(
        self,
        tenant_id: str,
        query: str,
        *,
        limit: int = 8,
        source_type: str | None = None,
        visibility: str | None = None,
    ) -> list[MemorySearchResultDTO]:
        normalized_query = query.strip()
        if not normalized_query:
            return []

        like_query = f"%{normalized_query}%"
        filters: list[str] = [
            "d.tenant_id = %s",
            "v.review_status = 'published'",
            "d.published_version_id = v.version_id",
            "(to_tsvector('simple', c.text) @@ sq.query OR c.text ILIKE %s)",
        ]
        parameters: list[object] = [tenant_id.strip(), like_query]

        if source_type is not None:
            filters.append("d.source_metadata->>'source_type' = %s")
            parameters.append(source_type.strip().lower())
        if visibility is not None:
            filters.append("c.visibility = %s")
            parameters.append(visibility.strip().lower())

        parameters = [normalized_query, like_query, *parameters, limit]
        rows = self._database.fetch_all(
            f"""
            WITH sq AS (
                SELECT websearch_to_tsquery('simple', %s) AS query
            )
            SELECT
                c.chunk_id,
                d.document_id,
                v.version_id,
                d.tenant_id,
                d.title,
                c.text,
                c.chunk_index,
                d.source_metadata->>'source_type' AS source_type,
                v.trust_level,
                c.visibility,
                ts_rank_cd(
                    to_tsvector('simple', c.text),
                    sq.query
                ) + CASE WHEN c.text ILIKE %s THEN 1.0 ELSE 0.0 END AS score
            FROM rag_chunks AS c
            JOIN rag_document_versions AS v
              ON v.tenant_id = c.tenant_id AND v.version_id = c.version_id
            JOIN rag_documents AS d
              ON d.tenant_id = v.tenant_id AND d.document_id = v.document_id
            CROSS JOIN sq
            WHERE {" AND ".join(filters)}
            ORDER BY score DESC, d.document_id, c.chunk_index
            LIMIT %s;
            """,
            tuple(parameters),
        )

        return [
            MemorySearchResultDTO(
                chunk_id=str(row["chunk_id"]),
                document_id=str(row["document_id"]),
                version_id=str(row["version_id"]),
                tenant_id=str(row["tenant_id"]),
                title=str(row["title"]),
                text=str(row["text"]),
                score=float(row["score"]),
                chunk_index=int(row["chunk_index"]),
                source_type=str(row["source_type"]),
                trust_level=str(row["trust_level"]),
                visibility=str(row["visibility"]),
            )
            for row in rows
        ]

    def _hydrate_document(self, document_row: dict[str, object]) -> Document:
        tenant_id = str(document_row["tenant_id"])
        document_id = str(document_row["document_id"])
        document = Document(
            document_id=document_id,
            tenant_id=tenant_id,
            title=str(document_row["title"]),
            source_metadata=SourceMetadata(**_dict(document_row["source_metadata"])),
            visibility=str(document_row["visibility"]),
            created_at=_datetime(document_row["created_at"]),
            updated_at=_datetime(document_row["updated_at"]),
            published_version_id=_optional_str(document_row["published_version_id"]),
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
            ORDER BY created_at, version_id;
            """,
            (tenant_id, document_id),
        )
        chunk_rows = self._database.fetch_all(
            """
            SELECT
                c.chunk_id,
                c.tenant_id,
                c.version_id,
                c.chunk_index,
                c.text,
                c.start_byte,
                c.end_byte,
                c.visibility
            FROM rag_chunks AS c
            JOIN rag_document_versions AS v
              ON v.tenant_id = c.tenant_id AND v.version_id = c.version_id
            WHERE v.tenant_id = %s AND v.document_id = %s
            ORDER BY c.version_id, c.chunk_index;
            """,
            (tenant_id, document_id),
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


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
