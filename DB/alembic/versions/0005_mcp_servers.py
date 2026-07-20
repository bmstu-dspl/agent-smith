"""Create mcp_servers table.

Revision ID: 0005_mcp_servers
Revises: 0004_rag_chunk_embeddings
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_mcp_servers"
down_revision = "0004_rag_chunk_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "mcp_servers" not in tables:
        op.create_table(
            "mcp_servers",
            sa.Column("server_id", sa.Text(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("transport_type", sa.Text(), nullable=False),
            sa.Column("url", sa.Text(), nullable=False),
            sa.Column("headers_encrypted", sa.Text(), nullable=True),
            sa.Column("query_params_encrypted", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("server_id", name="pk_mcp_servers"),
            sa.CheckConstraint(
                "transport_type IN ('sse', 'stdio', 'http', 'streamable_http')", name="ck_mcp_servers_transport_type_valid"
            ),
        )

    _create_index("idx_mcp_servers_is_active", "mcp_servers", ["is_active"])


def downgrade() -> None:
    op.drop_table("mcp_servers")


def _create_index(name: str, table: str, columns: list[object], **kwargs: object) -> None:
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns, **kwargs)
