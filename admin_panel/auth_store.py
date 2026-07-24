from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import uuid

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db_models import AdminSessionModel, AdminUserModel


SESSION_TTL = timedelta(hours=8)


@dataclass(frozen=True, slots=True)
class AdminIdentity:
    admin_id: str
    username: str
    role: str
    csrf_token: str


class AdminAuthStore:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def create_admin(self, username: str, password: str, *, role: str = "viewer") -> str:
        normalized = username.strip().lower()
        if not normalized:
            raise ValueError("username must not be empty")
        if len(password) < 12:
            raise ValueError("password must contain at least 12 characters")
        if len(password.encode("utf-8")) > 72:
            raise ValueError("password must not exceed 72 UTF-8 bytes")
        if role not in {"admin", "editor", "viewer"}:
            raise ValueError("role must be admin, editor, or viewer")

        admin_id = str(uuid.uuid4())
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        with self._session_factory() as session, session.begin():
            session.add(
                AdminUserModel(
                    admin_id=admin_id,
                    username=normalized,
                    password_hash=password_hash,
                    role=role,
                )
            )
        return admin_id

    def count_admins(self) -> int:
        with self._session_factory() as session:
            return session.scalar(select(func.count()).select_from(AdminUserModel)) or 0

    def login(self, username: str, password: str) -> tuple[str, AdminIdentity] | None:
        now = datetime.now(timezone.utc)
        with self._session_factory() as session, session.begin():
            user = session.scalar(
                select(AdminUserModel).where(
                    func.lower(AdminUserModel.username) == username.strip().lower()
                )
            )
            if (
                user is None
                or not user.is_active
                or not bcrypt.checkpw(password.encode(), user.password_hash.encode())
            ):
                return None

            raw_session = secrets.token_urlsafe(48)
            csrf_token = secrets.token_urlsafe(32)
            session.add(
                AdminSessionModel(
                    session_hash=_hash_session(raw_session),
                    admin_id=user.admin_id,
                    csrf_token=csrf_token,
                    expires_at=now + SESSION_TTL,
                    last_seen_at=now,
                )
            )
            user.last_login_at = now
            identity = AdminIdentity(user.admin_id, user.username, user.role, csrf_token)
        return raw_session, identity

    def get_identity(self, raw_session: str) -> AdminIdentity | None:
        now = datetime.now(timezone.utc)
        with self._session_factory() as session, session.begin():
            row = session.execute(
                select(AdminSessionModel, AdminUserModel)
                .join(AdminUserModel, AdminUserModel.admin_id == AdminSessionModel.admin_id)
                .where(AdminSessionModel.session_hash == _hash_session(raw_session))
            ).one_or_none()
            if row is None:
                return None
            admin_session, user = row
            if admin_session.expires_at.replace(tzinfo=timezone.utc) <= now or not user.is_active:
                session.delete(admin_session)
                return None
            admin_session.last_seen_at = now
            return AdminIdentity(user.admin_id, user.username, user.role, admin_session.csrf_token)

    def logout(self, raw_session: str) -> None:
        with self._session_factory() as session, session.begin():
            record = session.get(AdminSessionModel, _hash_session(raw_session))
            if record is not None:
                session.delete(record)


def _hash_session(raw_session: str) -> str:
    return hashlib.sha256(raw_session.encode()).hexdigest()
