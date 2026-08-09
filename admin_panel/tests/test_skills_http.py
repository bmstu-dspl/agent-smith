from __future__ import annotations

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
    AgentSkillModel,
    SkillCatalogModel,
)
from admin_panel.skills import SkillStore


def _client(*, role: str = "admin") -> TestClient:
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
            SkillCatalogModel.__table__,
            AgentSkillModel.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    auth_store = AdminAuthStore(session_factory)
    auth_store.create_admin(
        "owner",
        "correct horse battery staple",
        role=role,
    )
    return TestClient(
        create_app(
            auth_store=auth_store,
            skill_store=SkillStore(session_factory),
        ),
        base_url="https://testserver",
    )


def test_admin_can_manage_the_skill_catalog_through_http() -> None:
    with _client() as client:
        client.post(
            "/admin/login",
            data={
                "username": "owner",
                "password": "correct horse battery staple",
            },
        )
        csrf = client.get("/admin/api/session").json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf}

        empty = client.get("/admin/api/skills")
        assert empty.status_code == 200
        assert empty.json() == {"revision": 0, "skills": []}

        created = client.post(
            "/admin/api/skills",
            headers=headers,
            json={
                "revision": 0,
                "name": "room-availability",
                "description": "Use when a guest asks to find available rooms.",
                "instructions": "Collect dates before searching.",
                "enabled": True,
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert body["revision"] == 1
        assert body["skills"][0]["name"] == "room-availability"
        skill_id = body["skills"][0]["skill_id"]

        updated = client.put(
            f"/admin/api/skills/{skill_id}",
            headers=headers,
            json={
                "revision": 1,
                "name": "room-availability",
                "description": "Use for requests about available hotel rooms.",
                "instructions": "Collect dates and guest counts before searching.",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["skills"][0]["version"] == 2

        disabled = client.post(
            f"/admin/api/skills/{skill_id}/toggle",
            headers=headers,
            json={"revision": 2, "enabled": False},
        )
        assert disabled.status_code == 200
        assert disabled.json()["skills"][0]["enabled"] is False

        deleted = client.request(
            "DELETE",
            f"/admin/api/skills/{skill_id}",
            headers=headers,
            json={"revision": 3},
        )
        assert deleted.status_code == 200
        assert deleted.json() == {"revision": 4, "skills": []}


def test_skill_api_rejects_invalid_stale_and_duplicate_changes() -> None:
    with _client() as client:
        assert client.get("/admin/api/skills").status_code == 401
        client.post(
            "/admin/login",
            data={
                "username": "owner",
                "password": "correct horse battery staple",
            },
        )
        csrf = client.get("/admin/api/session").json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf}
        base = {
            "revision": 0,
            "description": "Use when a guest asks to find available rooms.",
            "instructions": "Collect dates before searching.",
            "enabled": True,
        }

        invalid = client.post(
            "/admin/api/skills",
            headers=headers,
            json={**base, "name": "Room Availability"},
        )
        assert invalid.status_code == 422

        created = client.post(
            "/admin/api/skills",
            headers=headers,
            json={**base, "name": "room-availability"},
        )
        assert created.status_code == 201

        stale = client.post(
            "/admin/api/skills",
            headers=headers,
            json={**base, "name": "booking"},
        )
        assert stale.status_code == 409

        duplicate = client.post(
            "/admin/api/skills",
            headers=headers,
            json={**base, "revision": 1, "name": "room-availability"},
        )
        assert duplicate.status_code == 409


def test_dashboard_exposes_skill_editor_actions() -> None:
    with _client() as client:
        client.post(
            "/admin/login",
            data={
                "username": "owner",
                "password": "correct horse battery staple",
            },
        )

        dashboard = client.get("/admin")

        assert dashboard.status_code == 200
        assert 'data-tab="skills"' in dashboard.text
        assert 'id="skill-form"' in dashboard.text
        assert 'name="description"' in dashboard.text
        assert 'name="instructions"' in dashboard.text
        assert 'api("/admin/api/skills")' in dashboard.text
        assert "Delete skill permanently?" in dashboard.text


def test_viewer_can_read_but_cannot_change_skills() -> None:
    with _client(role="viewer") as client:
        client.post(
            "/admin/login",
            data={
                "username": "owner",
                "password": "correct horse battery staple",
            },
        )
        csrf = client.get("/admin/api/session").json()["csrf_token"]

        assert client.get("/admin/api/skills").status_code == 200
        denied = client.post(
            "/admin/api/skills",
            headers={"X-CSRF-Token": csrf},
            json={
                "revision": 0,
                "name": "room-availability",
                "description": "Use when a guest asks to find available rooms.",
                "instructions": "Collect dates before searching.",
            },
        )
        assert denied.status_code == 403
