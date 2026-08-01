from __future__ import annotations

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from DB import OrmBase
from admin_panel.app import create_app
from admin_panel.auth_store import AdminAuthStore
from admin_panel.db_models import (
    AdminSessionModel,
    AdminUserModel,
    ServiceSettingsModel,
)
from admin_panel.settings import SettingsStore


def test_telegram_settings_are_typed_durable_and_do_not_disclose_bot_token() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    OrmBase.metadata.create_all(
        engine,
        tables=[
            AdminUserModel.__table__,
            AdminSessionModel.__table__,
            ServiceSettingsModel.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    auth_store = AdminAuthStore(session_factory)
    auth_store.create_admin("owner", "correct horse battery staple", role="admin")
    encryption_key = Fernet.generate_key().decode()

    with TestClient(
        create_app(
            auth_store=auth_store,
            settings_store=SettingsStore(session_factory, encryption_key),
        ),
        base_url="https://testserver",
    ) as client:
        client.post(
            "/admin/login",
            data={"username": "owner", "password": "correct horse battery staple"},
        )
        csrf = client.get("/admin/api/session").json()["csrf_token"]

        fresh = client.get("/admin/api/settings/telegram")
        assert fresh.status_code == 200
        assert fresh.json()["revision"] == 0
        assert fresh.json()["webhook_host"] == ""
        assert fresh.json()["bot_token_configured"] is False

        invalid = client.put(
            "/admin/api/settings/telegram",
            headers={"X-CSRF-Token": csrf},
            json={
                "revision": 0,
                "bot_token": "123:secret",
                "webhook_host": "https://bot.example.test",
                "manager_group_id": 100,
                "ai_agent_url": "http://ai-agent:8000",
                "enable_escalation": True,
            },
        )
        assert invalid.status_code == 422

        saved = client.put(
            "/admin/api/settings/telegram",
            headers={"X-CSRF-Token": csrf},
            json={
                "revision": 0,
                "bot_token": "123:secret",
                "webhook_host": "https://bot.example.test",
                "manager_group_id": -1001234567890,
                "ai_agent_url": "http://ai-agent:8000",
                "enable_escalation": True,
            },
        )
        assert saved.status_code == 200
        assert saved.json()["revision"] == 1

        visible = client.get("/admin/api/settings/telegram")
        assert visible.status_code == 200
        assert visible.json()["bot_token_configured"] is True
        assert "bot_token" not in visible.json()

    reopened_store = SettingsStore(session_factory, encryption_key)
    persisted = reopened_store.get_telegram()
    assert persisted.settings.manager_group_id == -1001234567890
    assert persisted.bot_token == "123:secret"


def test_agent_and_rag_settings_use_explicit_validated_areas() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    OrmBase.metadata.create_all(
        engine,
        tables=[
            AdminUserModel.__table__,
            AdminSessionModel.__table__,
            ServiceSettingsModel.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    auth_store = AdminAuthStore(session_factory)
    auth_store.create_admin("owner", "correct horse battery staple", role="admin")
    settings_store = SettingsStore(session_factory, Fernet.generate_key().decode())

    with TestClient(
        create_app(auth_store=auth_store, settings_store=settings_store),
        base_url="https://testserver",
    ) as client:
        client.post(
            "/admin/login",
            data={"username": "owner", "password": "correct horse battery staple"},
        )
        csrf = client.get("/admin/api/session").json()["csrf_token"]

        agent = client.put(
            "/admin/api/settings/agent",
            headers={"X-CSRF-Token": csrf},
            json={
                "revision": 0,
                "provider": "openai",
                "model": "gpt-5-mini",
                "temperature": 0.3,
                "system_prompt": "You assist hotel guests.",
                "vertex_location": "global",
                "primary_timezone": "Europe/Moscow",
            },
        )
        assert agent.status_code == 200
        assert agent.json()["revision"] == 1
        assert agent.json()["vertex_location"] == "global"
        assert agent.json()["primary_timezone"] == "Europe/Moscow"

        invalid_timezone = client.put(
            "/admin/api/settings/agent",
            headers={"X-CSRF-Token": csrf},
            json={
                "revision": 1,
                "provider": "openai",
                "model": "gpt-5-mini",
                "temperature": 0.3,
                "system_prompt": "You assist hotel guests.",
                "vertex_location": "global",
                "primary_timezone": "Mars/Olympus_Mons",
            },
        )
        assert invalid_timezone.status_code == 422

        invalid_rag = client.put(
            "/admin/api/settings/rag",
            headers={"X-CSRF-Token": csrf},
            json={
                "revision": 0,
                "enabled": True,
                "additional_instructions": "Prefer approved policies.",
                "max_chunk_chars": 500,
                "chunk_overlap_chars": 500,
                "retrieval_mode": "hybrid",
                "limit": 8,
                "max_context_chars": 12000,
            },
        )
        assert invalid_rag.status_code == 422

        rag = client.put(
            "/admin/api/settings/rag",
            headers={"X-CSRF-Token": csrf},
            json={
                "revision": 0,
                "enabled": True,
                "additional_instructions": "Prefer approved policies.",
                "max_chunk_chars": 1200,
                "chunk_overlap_chars": 150,
                "retrieval_mode": "hybrid",
                "limit": 8,
                "max_context_chars": 12000,
            },
        )
        assert rag.status_code == 200
        assert client.get("/admin/api/settings/agent").json()["model"] == "gpt-5-mini"
        assert (
            client.get("/admin/api/settings/agent").json()["vertex_location"]
            == "global"
        )
        assert (
            client.get("/admin/api/settings/agent").json()["primary_timezone"]
            == "Europe/Moscow"
        )
        assert (
            client.get("/admin/api/settings/rag").json()["additional_instructions"]
            == "Prefer approved policies."
        )
