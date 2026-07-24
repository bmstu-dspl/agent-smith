from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from DB import OrmBase
from admin_panel.app import create_app
from admin_panel.auth_store import AdminAuthStore
from admin_panel.db_models import AdminSessionModel, AdminUserModel


def _client_with_admin() -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    OrmBase.metadata.create_all(
        engine,
        tables=[AdminUserModel.__table__, AdminSessionModel.__table__],
    )
    store = AdminAuthStore(sessionmaker(bind=engine, expire_on_commit=False))
    store.create_admin("owner", "correct horse battery staple", role="admin")
    return TestClient(create_app(auth_store=store), base_url="https://testserver")


def test_admin_session_requires_login_and_returns_authenticated_identity() -> None:
    with _client_with_admin() as client:
        anonymous = client.get("/admin/api/session")
        assert anonymous.status_code == 401

        login = client.post(
            "/admin/login",
            data={"username": "owner", "password": "correct horse battery staple"},
            follow_redirects=False,
        )
        assert login.status_code == 303
        assert login.cookies.get("admin_session")

        session = client.get("/admin/api/session")
        assert session.status_code == 200
        assert session.headers["cache-control"] == "no-store"
        assert "frame-ancestors 'none'" in session.headers["content-security-policy"]
        assert session.json()["admin"] == {
            "username": "owner",
            "role": "admin",
        }
        assert session.json()["csrf_token"]

        dashboard = client.get("/admin")
        assert dashboard.status_code == 200
        assert "Telegram settings" in dashboard.text
        assert "Agent settings" in dashboard.text
        assert "RAG documents" in dashboard.text
        assert "MCP servers" in dashboard.text
        assert "Administrators" in dashboard.text


def test_only_admin_role_can_create_accounts_and_csrf_is_required() -> None:
    with _client_with_admin() as client:
        client.post(
            "/admin/login",
            data={"username": "owner", "password": "correct horse battery staple"},
        )
        csrf_token = client.get("/admin/api/session").json()["csrf_token"]

        missing_csrf = client.post(
            "/admin/api/admins",
            json={
                "username": "operator",
                "password": "another correct battery staple",
                "role": "editor",
            },
        )
        assert missing_csrf.status_code == 403

        created = client.post(
            "/admin/api/admins",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "username": "operator",
                "password": "another correct battery staple",
                "role": "editor",
            },
        )
        assert created.status_code == 201
        assert created.json()["admin"]["role"] == "editor"

        client.post("/admin/logout", headers={"X-CSRF-Token": csrf_token})
        client.post(
            "/admin/login",
            data={"username": "operator", "password": "another correct battery staple"},
        )
        editor_csrf = client.get("/admin/api/session").json()["csrf_token"]
        forbidden = client.post(
            "/admin/api/admins",
            headers={"X-CSRF-Token": editor_csrf},
            json={
                "username": "second-owner",
                "password": "yet another correct password",
                "role": "admin",
            },
        )
        assert forbidden.status_code == 403
