"""Add vector embeddings and HNSW index to RAG chunks.

Revision ID: 0004_rag_chunk_embeddings
Revises: 0003_memory_baseline
"""
from __future__ import annotations

from alembic import op
from pgvector.sqlalchemy import VECTOR
import sqlalchemy as sa

from RAG._embedding_constants import EMBEDDING_DIMENSIONS

revision = "0004_rag_chunk_embeddings"
down_revision = "0003_memory_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("rag_chunks")}
    if "embedding" not in columns:
        op.add_column("rag_chunks", sa.Column("embedding", VECTOR(EMBEDDING_DIMENSIONS)))
    if "embedding_model" not in columns:
        op.add_column("rag_chunks", sa.Column("embedding_model", sa.Text()))
    if "embedded_at" not in columns:
        op.add_column("rag_chunks", sa.Column("embedded_at", sa.DateTime(timezone=True)))

    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("rag_chunks")}
    if "idx_rag_chunks_embedding_hnsw" not in indexes:
        op.create_index(
            "idx_rag_chunks_embedding_hnsw",
            "rag_chunks",
            ["embedding"],
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_where=sa.text("embedding IS NOT NULL"),
        )


def downgrade() -> None:
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("rag_chunks")}
    if "idx_rag_chunks_embedding_hnsw" in indexes:
        op.drop_index("idx_rag_chunks_embedding_hnsw", table_name="rag_chunks")
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("rag_chunks")}
    for column in ("embedded_at", "embedding_model", "embedding"):
        if column in columns:
            op.drop_column("rag_chunks", column)
