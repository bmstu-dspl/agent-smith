"""Add optimistic-lock revision to RAG documents.

Revision ID: 0002_rag_document_revision
Revises: 0001_orm_baseline
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_rag_document_revision"
down_revision = "0001_orm_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("rag_documents")}
    if "revision" not in columns:
        op.add_column(
            "rag_documents",
            sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("rag_documents")}
    if "revision" in columns:
        op.drop_column("rag_documents", "revision")
