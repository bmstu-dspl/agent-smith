from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from DB import OrmBase
from admin_panel.app import create_app
from admin_panel.auth_store import AdminAuthStore
from admin_panel.db_models import AdminSessionModel, AdminUserModel


@dataclass
class _Server:
    server_id: str
    name: str
    url: str
    transport_type: str
    headers: dict
    query_params: dict
    is_active: bool = True
    last_connected_at: object = None
    error_message: str | None = None


class _McpStore:
    def __init__(self) -> None:
        self.servers: dict[str, _Server] = {}

    def list_servers(self):
        return list(self.servers.values())

    def get_server(self, server_id):
        return self.servers.get(server_id)

    def add_server(self, **values):
        server_id = "server-1"
        self.servers[server_id] = _Server(server_id=server_id, **values)
        return server_id

    def set_active(self, server_id, active):
        self.servers[server_id].is_active = active

    def update_credentials(self, server_id, *, headers=None, query_params=None):
        if headers is not None:
            self.servers[server_id].headers = headers
        if query_params is not None:
            self.servers[server_id].query_params = query_params

    def delete_server(self, server_id):
        self.servers.pop(server_id, None)


def test_mcp_registry_mutations_are_authenticated_authorized_and_secret_safe() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    OrmBase.metadata.create_all(
        engine,
        tables=[AdminUserModel.__table__, AdminSessionModel.__table__],
    )
    auth_store = AdminAuthStore(sessionmaker(bind=engine, expire_on_commit=False))
    auth_store.create_admin("owner", "correct horse battery staple", role="admin")
    mcp_store = _McpStore()

    with TestClient(
        create_app(auth_store=auth_store, mcp_store=mcp_store),
        base_url="https://testserver",
    ) as client:
        assert client.get("/admin/api/mcp/servers").status_code == 401
        client.post(
            "/admin/login",
            data={"username": "owner", "password": "correct horse battery staple"},
        )
        csrf = client.get("/admin/api/session").json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf}

        created = client.post(
            "/admin/api/mcp/servers",
            headers=headers,
            json={
                "name": "Booking",
                "url": "https://mcp.example.test/sse",
                "transport_type": "sse",
                "headers": {"Authorization": "Bearer secret"},
                "query_params": {},
            },
        )
        assert created.status_code == 201

        listed = client.get("/admin/api/mcp/servers").json()["servers"]
        assert listed[0]["has_secrets"] is True
        assert "headers" not in listed[0]
        assert "Bearer secret" not in str(listed[0])

        toggled = client.post(
            "/admin/api/mcp/servers/server-1/toggle",
            headers=headers,
            json={"is_active": False},
        )
        assert toggled.status_code == 200
        assert mcp_store.servers["server-1"].is_active is False

        deleted = client.delete("/admin/api/mcp/servers/server-1", headers=headers)
        assert deleted.status_code == 204
