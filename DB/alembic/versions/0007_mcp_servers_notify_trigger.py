"""Add NOTIFY trigger on mcp_servers changes, so the agent can react without polling.

Revision ID: 0007_mcp_servers_notify_trigger
Revises: 0006_admin_control_plane
"""
from __future__ import annotations

from alembic import op

revision = "0007_mcp_servers_notify_trigger"
down_revision = "0006_admin_control_plane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION notify_mcp_servers_change() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify('mcp_servers_changed', 'changed');
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_mcp_servers_notify ON mcp_servers;
        CREATE TRIGGER trg_mcp_servers_notify
        AFTER INSERT OR DELETE OR UPDATE OF
            name, url, transport_type, headers_encrypted, query_params_encrypted, is_active
        ON mcp_servers
        FOR EACH STATEMENT
        EXECUTE FUNCTION notify_mcp_servers_change();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_mcp_servers_notify ON mcp_servers;")
    op.execute("DROP FUNCTION IF EXISTS notify_mcp_servers_change();")
