from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKeyConstraint, Index, Integer, Text, func, literal_column, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import VECTOR

from DB import OrmBase
from RAG._embedding_constants import EMBEDDING_DIMENSIONS


class DocumentModel(OrmBase):
    __tablename__ = "rag_documents"
    __table_args__ = (
        Index("idx_rag_documents_tenant_visibility", "tenant_id", "visibility"),
        Index("idx_rag_documents_published_version", "tenant_id", "published_version_id"),
    )

    tenant_id: Mapped[str] = mapped_column(Text, primary_key=True)
    document_id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    visibility: Mapped[str] = mapped_column(Text, nullable=False)
    published_version_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    versions: Mapped[list[DocumentVersionModel]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: (DocumentVersionModel.created_at, DocumentVersionModel.version_id),
    )
    __mapper_args__ = {"version_id_col": revision}


class DocumentVersionModel(OrmBase):
    __tablename__ = "rag_document_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["rag_documents.tenant_id", "rag_documents.document_id"],
            name="fk_rag_document_versions_document",
            ondelete="CASCADE",
        ),
        Index("idx_rag_versions_document", "tenant_id", "document_id"),
        Index("idx_rag_versions_review_status", "tenant_id", "review_status"),
    )

    tenant_id: Mapped[str] = mapped_column(Text, primary_key=True)
    version_id: Mapped[str] = mapped_column(Text, primary_key=True)
    document_id: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    trust_level: Mapped[str] = mapped_column(Text, nullable=False)
    review_status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    document: Mapped[DocumentModel] = relationship(back_populates="versions")
    chunks: Mapped[list[ChunkModel]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: ChunkModel.chunk_index,
    )


class ChunkModel(OrmBase):
    __tablename__ = "rag_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "version_id"],
            ["rag_document_versions.tenant_id", "rag_document_versions.version_id"],
            name="fk_rag_chunks_version",
            ondelete="CASCADE",
        ),
        Index("idx_rag_chunks_version", "tenant_id", "version_id", "chunk_index"),
    )

    tenant_id: Mapped[str] = mapped_column(Text, primary_key=True)
    chunk_id: Mapped[str] = mapped_column(Text, primary_key=True)
    version_id: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_byte: Mapped[int] = mapped_column(Integer, nullable=False)
    end_byte: Mapped[int] = mapped_column(Integer, nullable=False)
    visibility: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR(EMBEDDING_DIMENSIONS))
    embedding_model: Mapped[str | None] = mapped_column(Text)
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[DocumentVersionModel] = relationship(back_populates="chunks")


Index(
    "idx_rag_documents_source_type",
    DocumentModel.source_metadata.op("->>")(literal_column("'source_type'")),
)
_chunk_fts_index = Index(
    "idx_rag_chunks_text_fts",
    func.to_tsvector(literal_column("'simple'"), ChunkModel.text),
    postgresql_using="gin",
)
ChunkModel.__table__.append_constraint(_chunk_fts_index)
_chunk_embedding_index = Index(
    "idx_rag_chunks_embedding_hnsw",
    ChunkModel.embedding,
    postgresql_using="hnsw",
    postgresql_with={"m": 16, "ef_construction": 64},
    postgresql_ops={"embedding": "vector_cosine_ops"},
    postgresql_where=ChunkModel.embedding.is_not(None),
)
ChunkModel.__table__.append_constraint(_chunk_embedding_index)
