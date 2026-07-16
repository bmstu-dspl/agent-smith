"""Create agent memory schema (messages, system_settings).

Revision ID: 0003_memory_baseline
Revises: 0001_orm_baseline
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_memory_baseline"
down_revision = "0002_rag_document_revision"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "messages" not in tables:
        op.create_table(
            "messages",
            sa.Column("message_id", sa.Text(), nullable=False),
            sa.Column("session_id", sa.Text(), nullable=False),
            sa.Column("role", sa.Text(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("is_final", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("message_id", name="pk_messages"),
            sa.CheckConstraint("role IN ('user', 'assistant', 'system', 'tool')", name="ck_messages_role_valid"),
        )
    if "system_settings" not in tables:
        op.create_table(
            "system_settings",
            sa.Column("setting_key", sa.Text(), nullable=False),
            sa.Column("setting_value", postgresql.JSONB(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("setting_key", name="pk_system_settings"),
        )

    _create_index("idx_messages_session_created", "messages", ["session_id", "created_at"])
    _create_index("idx_messages_session_active_final", "messages", ["session_id", "is_active", "is_final"])


def downgrade() -> None:
    op.drop_table("system_settings")
    op.drop_table("messages")


def _create_index(name: str, table: str, columns: list[object], **kwargs: object) -> None:
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns, **kwargs)
