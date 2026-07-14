"""Create graph and RAG persistence schema.

Revision ID: 0001_orm_baseline
Revises: None
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_orm_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    if "graph_nodes" not in tables:
        op.create_table(
            "graph_nodes",
            sa.Column("node_id", sa.Text(), nullable=False),
            sa.Column("node_type", sa.Text(), nullable=False),
            sa.Column("properties", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("node_id", name="pk_graph_nodes"),
        )
    if "graph_edges" not in tables:
        op.create_table(
            "graph_edges",
            sa.Column("edge_id", sa.Text(), nullable=False),
            sa.Column("from_node_id", sa.Text(), nullable=False),
            sa.Column("to_node_id", sa.Text(), nullable=False),
            sa.Column("edge_type", sa.Text(), nullable=False),
            sa.Column("properties", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["from_node_id"], ["graph_nodes.node_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["to_node_id"], ["graph_nodes.node_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("edge_id", name="pk_graph_edges"),
        )
    if "rag_documents" not in tables:
        op.create_table(
            "rag_documents",
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("document_id", sa.Text(), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("source_metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
            sa.Column("visibility", sa.Text(), nullable=False),
            sa.Column("published_version_id", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
            sa.PrimaryKeyConstraint("tenant_id", "document_id", name="pk_rag_documents"),
        )
    if "rag_document_versions" not in tables:
        op.create_table(
            "rag_document_versions",
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("version_id", sa.Text(), nullable=False),
            sa.Column("document_id", sa.Text(), nullable=False),
            sa.Column("raw_text", sa.Text(), nullable=False),
            sa.Column("source_metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
            sa.Column("trust_level", sa.Text(), nullable=False),
            sa.Column("review_status", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(
                ["tenant_id", "document_id"],
                ["rag_documents.tenant_id", "rag_documents.document_id"],
                name="fk_rag_document_versions_document",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("tenant_id", "version_id", name="pk_rag_document_versions"),
        )
    if "rag_chunks" not in tables:
        op.create_table(
            "rag_chunks",
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("chunk_id", sa.Text(), nullable=False),
            sa.Column("version_id", sa.Text(), nullable=False),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("start_byte", sa.Integer(), nullable=False),
            sa.Column("end_byte", sa.Integer(), nullable=False),
            sa.Column("visibility", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(
                ["tenant_id", "version_id"],
                ["rag_document_versions.tenant_id", "rag_document_versions.version_id"],
                name="fk_rag_chunks_version",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("tenant_id", "chunk_id", name="pk_rag_chunks"),
        )

    _create_index("idx_graph_nodes_type", "graph_nodes", ["node_type"])
    _create_index("idx_graph_edges_from_node", "graph_edges", ["from_node_id"])
    _create_index("idx_graph_edges_to_node", "graph_edges", ["to_node_id"])
    _create_index("idx_graph_edges_type", "graph_edges", ["edge_type"])
    _create_index("idx_rag_documents_tenant_visibility", "rag_documents", ["tenant_id", "visibility"])
    _create_index("idx_rag_documents_published_version", "rag_documents", ["tenant_id", "published_version_id"])
    _create_index("idx_rag_versions_document", "rag_document_versions", ["tenant_id", "document_id"])
    _create_index("idx_rag_versions_review_status", "rag_document_versions", ["tenant_id", "review_status"])
    _create_index("idx_rag_chunks_version", "rag_chunks", ["tenant_id", "version_id", "chunk_index"])
    _create_index(
        "idx_rag_documents_source_type",
        "rag_documents",
        [sa.text("(source_metadata->>'source_type')")],
    )
    _create_index(
        "idx_rag_chunks_text_fts",
        "rag_chunks",
        [sa.text("to_tsvector('simple', text)")],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_table("rag_chunks")
    op.drop_table("rag_document_versions")
    op.drop_table("rag_documents")
    op.drop_table("graph_edges")
    op.drop_table("graph_nodes")


def _create_index(name: str, table: str, columns: list[object], **kwargs: object) -> None:
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns, **kwargs)
