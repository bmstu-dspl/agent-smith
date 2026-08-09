"""Add the global Agent Skills catalog.

Revision ID: 0008_agent_skills
Revises: 0007_mcp_servers_notify_trigger
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008_agent_skills"
down_revision = "0007_mcp_servers_notify_trigger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_skill_catalog",
        sa.Column("catalog_id", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["admin_users.admin_id"],
            name=op.f("fk_agent_skill_catalog_updated_by_admin_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("catalog_id", name=op.f("pk_agent_skill_catalog")),
    )
    op.create_table(
        "agent_skills",
        sa.Column("skill_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_agent_skills_agent_skill_version_positive")),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["admin_users.admin_id"],
            name=op.f("fk_agent_skills_created_by_admin_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["admin_users.admin_id"],
            name=op.f("fk_agent_skills_updated_by_admin_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("skill_id", name=op.f("pk_agent_skills")),
        sa.UniqueConstraint("name", name=op.f("uq_agent_skills_name")),
    )
    op.create_index("ix_agent_skills_enabled", "agent_skills", ["enabled"])
    op.execute(
        "INSERT INTO agent_skill_catalog (catalog_id, revision) VALUES ('global', 0)"
    )


def downgrade() -> None:
    op.drop_index("ix_agent_skills_enabled", table_name="agent_skills")
    op.drop_table("agent_skills")
    op.drop_table("agent_skill_catalog")
