from __future__ import annotations

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from DB import OrmBase
from RAG import InMemoryDocumentStore, MemoryModule
from admin_panel.app import create_app
from admin_panel.auth_store import AdminAuthStore
from admin_panel.db_models import (
    AdminSessionModel,
    AdminUserModel,
    ServiceSettingsModel,
)
from admin_panel.settings import SettingsStore


def test_admin_can_manage_complete_rag_document_lifecycle() -> None:
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
    rag_memory = MemoryModule(InMemoryDocumentStore())

    with TestClient(
        create_app(
            auth_store=auth_store,
            settings_store=settings_store,
            rag_memory=rag_memory,
        ),
        base_url="https://testserver",
    ) as client:
        client.post(
            "/admin/login",
            data={"username": "owner", "password": "correct horse battery staple"},
        )
        csrf = client.get("/admin/api/session").json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf}

        ingested = client.post(
            "/admin/api/rag/documents/text",
            headers=headers,
            json={
                "tenant_id": "hotel",
                "document_id": "check-in-policy",
                "version_id": "v1",
                "title": "Check-in policy",
                "text": "Check-in begins at 14:00. Early check-in depends on availability.",
                "visibility": "tenant",
                "trust_level": "trusted",
            },
        )
        assert ingested.status_code == 201
        assert ingested.json()["version"]["review_status"] == "processed"

        documents = client.get("/admin/api/rag/documents", params={"tenant_id": "hotel"})
        assert documents.status_code == 200
        assert documents.json()["documents"][0]["document_id"] == "check-in-policy"

        details = client.get(
            "/admin/api/rag/documents/check-in-policy",
            params={"tenant_id": "hotel"},
        )
        assert details.json()["versions"][0]["version_id"] == "v1"

        chunks = client.get(
            "/admin/api/rag/documents/check-in-policy/versions/v1/chunks",
            params={"tenant_id": "hotel"},
        )
        assert "14:00" in chunks.json()["chunks"][0]["text"]

        approved = client.post(
            "/admin/api/rag/documents/check-in-policy/versions/v1/approve",
            headers=headers,
            params={"tenant_id": "hotel"},
        )
        assert approved.json()["review_status"] == "approved"

        published = client.post(
            "/admin/api/rag/documents/check-in-policy/versions/v1/publish",
            headers=headers,
            params={"tenant_id": "hotel"},
        )
        assert published.json()["review_status"] == "published"

        preview = client.get(
            "/admin/api/rag/search",
            params={"tenant_id": "hotel", "query": "early check-in"},
        )
        assert preview.status_code == 200
        assert preview.json()["results"][0]["document_id"] == "check-in-policy"

        uploaded = client.post(
            "/admin/api/rag/documents/file",
            headers=headers,
            data={
                "tenant_id": "hotel",
                "document_id": "breakfast-policy",
                "version_id": "v1",
                "title": "Breakfast policy",
                "visibility": "tenant",
                "trust_level": "trusted",
            },
            files={"file": ("breakfast.txt", b"Breakfast is served until 10:30.", "text/plain")},
        )
        assert uploaded.status_code == 201
        assert uploaded.json()["version"]["source_type"] == "text"

        archived = client.post(
            "/admin/api/rag/documents/check-in-policy/versions/v1/archive",
            headers=headers,
            params={"tenant_id": "hotel"},
        )
        assert archived.json()["review_status"] == "archived"

        removed = client.delete(
            "/admin/api/rag/documents/check-in-policy",
            headers=headers,
            params={"tenant_id": "hotel"},
        )
        assert removed.status_code == 204
        remaining = client.get(
            "/admin/api/rag/documents",
            params={"tenant_id": "hotel"},
        ).json()["documents"]
        assert [item["document_id"] for item in remaining] == ["breakfast-policy"]
