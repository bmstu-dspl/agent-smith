from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from typing import Protocol

from sqlalchemy import case, func, literal_column, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.exc import StaleDataError

from DB import PostgresDatabase

from ._domain import Chunk, Document, DocumentVersion, SourceMetadata
from ._errors import ConcurrentModificationError, DocumentAlreadyExistsError
from ._models import ChunkModel, DocumentModel, DocumentVersionModel
from .types import MemorySearchResultDTO


class DocumentStore(Protocol):
    def save(self, document: Document) -> None: ...

    def get(self, tenant_id: str, document_id: str) -> Document | None: ...

    def delete(self, tenant_id: str, document_id: str) -> bool: ...

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
        key = (document.tenant_id, document.document_id)
        stored = self._documents.get(key)
        if stored is not None:
            if document.revision == 0:
                raise DocumentAlreadyExistsError(
                    f"document {document.document_id!r} already exists"
                )
            if stored.revision != document.revision:
                raise ConcurrentModificationError("document was modified concurrently")
        document.revision += 1
        self._documents[key] = deepcopy(document)

    def get(self, tenant_id: str, document_id: str) -> Document | None:
        document = self._documents.get((tenant_id.strip(), document_id.strip()))
        return deepcopy(document) if document is not None else None

    def delete(self, tenant_id: str, document_id: str) -> bool:
        return self._documents.pop((tenant_id.strip(), document_id.strip()), None) is not None

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
        key = (document.tenant_id, document.document_id)
        with self._database.session() as session:
            model = session.get(DocumentModel, key, options=_document_options())
            if model is None:
                model = _document_model(document)
                session.add(model)
                try:
                    session.flush()
                except IntegrityError as error:
                    raise DocumentAlreadyExistsError(
                        f"document {document.document_id!r} already exists"
                    ) from error
                document.revision = model.revision
                return
            if document.revision == 0:
                raise DocumentAlreadyExistsError(
                    f"document {document.document_id!r} already exists"
                )
            if model.revision != document.revision:
                raise ConcurrentModificationError("document was modified concurrently")
            _sync_document_model(model, document)
            try:
                session.flush()
            except StaleDataError as error:
                raise ConcurrentModificationError("document was modified concurrently") from error
            document.revision = model.revision

    def get(self, tenant_id: str, document_id: str) -> Document | None:
        key = (tenant_id.strip(), document_id.strip())
        with self._database.session() as session:
            model = session.get(DocumentModel, key, options=_document_options())
            return _document_domain(model) if model is not None else None

    def delete(self, tenant_id: str, document_id: str) -> bool:
        key = (tenant_id.strip(), document_id.strip())
        with self._database.session() as session:
            model = session.get(DocumentModel, key)
            if model is None:
                return False
            session.delete(model)
            return True

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
        statement = (
            select(DocumentModel)
            .where(DocumentModel.tenant_id == tenant_id.strip())
            .options(*_document_options())
            .order_by(DocumentModel.created_at, DocumentModel.document_id)
            .limit(limit)
            .offset(offset)
        )
        if visibility is not None:
            statement = statement.where(DocumentModel.visibility == visibility.strip().lower())
        if source_type is not None:
            statement = statement.where(
                _source_type_expression() == source_type.strip().lower()
            )
        if review_status is not None:
            statement = statement.where(
                DocumentModel.versions.any(
                    DocumentVersionModel.review_status == review_status.strip().lower()
                )
            )

        with self._database.session() as session:
            return [_document_domain(model) for model in session.scalars(statement).all()]

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

        like_query = f"%{_escape_like(normalized_query)}%"
        language = literal_column("'simple'::regconfig")
        search_query = func.websearch_to_tsquery(language, normalized_query)
        search_vector = func.to_tsvector(language, ChunkModel.text)
        score = (
            func.ts_rank_cd(search_vector, search_query)
            + case((ChunkModel.text.ilike(like_query, escape="\\"), 1.0), else_=0.0)
        ).label("score")
        statement = (
            select(
                ChunkModel.chunk_id,
                DocumentModel.document_id,
                DocumentVersionModel.version_id,
                DocumentModel.tenant_id,
                DocumentModel.title,
                ChunkModel.text,
                ChunkModel.chunk_index,
                _source_type_expression().label("source_type"),
                DocumentVersionModel.trust_level,
                ChunkModel.visibility,
                score,
            )
            .join(DocumentVersionModel, ChunkModel.version)
            .join(DocumentModel, DocumentVersionModel.document)
            .where(
                DocumentModel.tenant_id == tenant_id.strip(),
                DocumentVersionModel.review_status == "published",
                DocumentModel.published_version_id == DocumentVersionModel.version_id,
                search_vector.bool_op("@@")(search_query) | ChunkModel.text.ilike(like_query, escape="\\"),
            )
            .order_by(score.desc(), DocumentModel.document_id, ChunkModel.chunk_index)
            .limit(limit)
        )
        if source_type is not None:
            statement = statement.where(
                _source_type_expression() == source_type.strip().lower()
            )
        if visibility is not None:
            statement = statement.where(ChunkModel.visibility == visibility.strip().lower())

        with self._database.session() as session:
            rows = session.execute(statement).mappings().all()
            return [
                MemorySearchResultDTO(
                    chunk_id=row["chunk_id"],
                    document_id=row["document_id"],
                    version_id=row["version_id"],
                    tenant_id=row["tenant_id"],
                    title=row["title"],
                    text=row["text"],
                    score=float(row["score"]),
                    chunk_index=row["chunk_index"],
                    source_type=row["source_type"],
                    trust_level=row["trust_level"],
                    visibility=row["visibility"],
                )
                for row in rows
            ]


def _document_options():
    return (selectinload(DocumentModel.versions).selectinload(DocumentVersionModel.chunks),)


def _source_type_expression():
    return DocumentModel.source_metadata.op("->>")(literal_column("'source_type'"))


def _document_model(document: Document) -> DocumentModel:
    return DocumentModel(
        tenant_id=document.tenant_id,
        document_id=document.document_id,
        title=document.title,
        source_metadata=asdict(document.source_metadata),
        visibility=document.visibility,
        published_version_id=document.published_version_id,
        created_at=document.created_at,
        updated_at=document.updated_at,
        revision=max(document.revision, 1),
        versions=[_version_model(version) for version in document.versions.values()],
    )


def _version_model(version: DocumentVersion) -> DocumentVersionModel:
    return DocumentVersionModel(
        tenant_id=version.tenant_id,
        version_id=version.version_id,
        document_id=version.document_id,
        raw_text=version.raw_text,
        source_metadata=asdict(version.source_metadata),
        trust_level=version.trust_level,
        review_status=version.review_status,
        created_at=version.created_at,
        updated_at=version.updated_at,
        processed_at=version.processed_at,
        reviewed_at=version.reviewed_at,
        published_at=version.published_at,
        chunks=[
            ChunkModel(
                tenant_id=chunk.tenant_id,
                chunk_id=chunk.chunk_id,
                version_id=chunk.version_id,
                chunk_index=chunk.index,
                text=chunk.text,
                start_byte=chunk.start_byte,
                end_byte=chunk.end_byte,
                visibility=chunk.visibility,
            )
            for chunk in version.chunks
        ],
    )


def _document_domain(model: DocumentModel) -> Document:
    document = Document(
        document_id=model.document_id,
        tenant_id=model.tenant_id,
        title=model.title,
        source_metadata=SourceMetadata(**model.source_metadata),
        visibility=model.visibility,
        created_at=model.created_at,
        updated_at=model.updated_at,
        published_version_id=model.published_version_id,
        revision=model.revision,
    )
    for version_model in model.versions:
        document.versions[version_model.version_id] = DocumentVersion(
            version_id=version_model.version_id,
            document_id=version_model.document_id,
            tenant_id=version_model.tenant_id,
            raw_text=version_model.raw_text,
            source_metadata=SourceMetadata(**version_model.source_metadata),
            trust_level=version_model.trust_level,
            review_status=version_model.review_status,
            created_at=version_model.created_at,
            updated_at=version_model.updated_at,
            processed_at=version_model.processed_at,
            reviewed_at=version_model.reviewed_at,
            published_at=version_model.published_at,
            chunks=[
                Chunk(
                    chunk_id=chunk.chunk_id,
                    tenant_id=chunk.tenant_id,
                    version_id=chunk.version_id,
                    index=chunk.chunk_index,
                    text=chunk.text,
                    start_byte=chunk.start_byte,
                    end_byte=chunk.end_byte,
                    visibility=chunk.visibility,
                )
                for chunk in version_model.chunks
            ],
        )
    return document


def _sync_document_model(model: DocumentModel, document: Document) -> None:
    model.title = document.title
    model.source_metadata = asdict(document.source_metadata)
    model.visibility = document.visibility
    model.published_version_id = document.published_version_id
    model.created_at = document.created_at
    model.updated_at = document.updated_at

    versions = {version.version_id: version for version in model.versions}
    desired_ids = set(document.versions)
    model.versions[:] = [version for version in model.versions if version.version_id in desired_ids]
    for version in document.versions.values():
        version_model = versions.get(version.version_id)
        if version_model is None:
            model.versions.append(_version_model(version))
        else:
            _sync_version_model(version_model, version)


def _sync_version_model(model: DocumentVersionModel, version: DocumentVersion) -> None:
    model.raw_text = version.raw_text
    model.source_metadata = asdict(version.source_metadata)
    model.trust_level = version.trust_level
    model.review_status = version.review_status
    model.created_at = version.created_at
    model.updated_at = version.updated_at
    model.processed_at = version.processed_at
    model.reviewed_at = version.reviewed_at
    model.published_at = version.published_at

    chunks = {chunk.chunk_id: chunk for chunk in model.chunks}
    desired_ids = {chunk.chunk_id for chunk in version.chunks}
    model.chunks[:] = [chunk for chunk in model.chunks if chunk.chunk_id in desired_ids]
    for chunk in version.chunks:
        chunk_model = chunks.get(chunk.chunk_id)
        if chunk_model is None:
            model.chunks.append(_chunk_model(chunk))
        else:
            chunk_model.chunk_index = chunk.index
            chunk_model.text = chunk.text
            chunk_model.start_byte = chunk.start_byte
            chunk_model.end_byte = chunk.end_byte
            chunk_model.visibility = chunk.visibility


def _chunk_model(chunk: Chunk) -> ChunkModel:
    return ChunkModel(
        tenant_id=chunk.tenant_id,
        chunk_id=chunk.chunk_id,
        version_id=chunk.version_id,
        chunk_index=chunk.index,
        text=chunk.text,
        start_byte=chunk.start_byte,
        end_byte=chunk.end_byte,
        visibility=chunk.visibility,
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
