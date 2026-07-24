from __future__ import annotations

from contextlib import asynccontextmanager
import os
import secrets
import time

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import sessionmaker

from DB import DatabaseConfig, PostgresDatabase

from .auth_store import AdminAuthStore, AdminIdentity
from .rag_api import create_rag_router
from .mcp_api import create_mcp_router
from .ui import dashboard_html
from .settings import (
    AgentSettingsUpdate,
    RagSettingsUpdate,
    SettingsConflictError,
    SettingsRecord,
    SettingsStore,
    TelegramSettingsRecord,
    TelegramSettingsUpdate,
)


SESSION_COOKIE = "admin_session"


class AdminCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=200)
    role: str = Field(pattern="^(admin|editor|viewer)$")


def create_app(
    *,
    auth_store: AdminAuthStore | None = None,
    settings_store: SettingsStore | None = None,
    rag_memory=None,
    mcp_store=None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = None
        embedding_provider = None
        if auth_store is None:
            database = PostgresDatabase(DatabaseConfig.from_env())
            database.open()
            database.migrate()
            store = AdminAuthStore(sessionmaker(bind=database.engine, expire_on_commit=False))
            _bootstrap_first_admin(store)
            app.state.auth_store = store
            encryption_key = os.getenv("CONFIG_SECRETS_ENCRYPTION_KEY") or os.getenv(
                "MCP_SECRETS_ENCRYPTION_KEY"
            )
            if not encryption_key:
                raise RuntimeError("CONFIG_SECRETS_ENCRYPTION_KEY is required")
            app.state.settings_store = SettingsStore(
                sessionmaker(bind=database.engine, expire_on_commit=False),
                encryption_key,
            )
            from RAG import (
                GoogleEmbeddingConfig,
                GoogleEmbeddingProvider,
                MemoryModule,
                PostgresDocumentStore,
            )

            if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
                embedding_provider = GoogleEmbeddingProvider(GoogleEmbeddingConfig.from_env())
            app.state.rag_memory = MemoryModule(
                PostgresDocumentStore(database),
                embedding_provider=embedding_provider,
            )
            from mcp_registry import McpServerStore

            app.state.mcp_store = McpServerStore(database)
        else:
            app.state.auth_store = auth_store
            if settings_store is not None:
                app.state.settings_store = settings_store
            if rag_memory is not None:
                app.state.rag_memory = rag_memory
            if mcp_store is not None:
                app.state.mcp_store = mcp_store
        yield
        if embedding_provider is not None:
            embedding_provider.close()
        if database is not None:
            database.close()

    application = FastAPI(title="Agent Smith Admin", lifespan=lifespan)

    @application.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'unsafe-inline'; "
            "script-src 'unsafe-inline'; img-src 'self' data:; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    application.include_router(create_rag_router(_require_identity, _require_mutation_access))
    application.include_router(create_mcp_router(_require_identity, _require_mutation_access))

    @application.get("/admin/login", response_class=HTMLResponse)
    async def login_page() -> str:
        return """
        <!doctype html><html><body><main>
        <h1>Agent Smith Admin</h1>
        <form method="post" action="/admin/login">
          <label>Username <input name="username" autocomplete="username" required></label>
          <label>Password <input name="password" type="password" autocomplete="current-password" required></label>
          <button type="submit">Sign in</button>
        </form>
        </main></body></html>
        """

    @application.post("/admin/login")
    async def login(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
    ) -> RedirectResponse:
        result = request.app.state.auth_store.login(username, password)
        if result is None:
            # Keep credential probing deliberately slow without revealing whether
            # the username exists. A reverse proxy should add IP-level throttling.
            await _minimum_login_delay()
            return RedirectResponse("/admin/login?error=invalid", status_code=303)
        raw_session, _identity = result
        response = RedirectResponse("/admin", status_code=303)
        response.set_cookie(
            SESSION_COOKIE,
            raw_session,
            max_age=8 * 60 * 60,
            httponly=True,
            secure=_env_bool("ADMIN_SECURE_COOKIES", default=True),
            samesite="strict",
            path="/admin",
        )
        return response

    @application.get("/admin/api/session")
    async def current_session(request: Request) -> dict[str, object]:
        identity = _require_identity(request)
        return {
            "admin": {"username": identity.username, "role": identity.role},
            "csrf_token": identity.csrf_token,
        }

    @application.post("/admin/api/admins", status_code=201)
    async def create_admin(request: Request, payload: AdminCreateRequest) -> dict[str, object]:
        identity = _require_mutation_access(request, required_role="admin")
        del identity
        admin_id = request.app.state.auth_store.create_admin(
            payload.username,
            payload.password,
            role=payload.role,
        )
        return {
            "admin": {
                "admin_id": admin_id,
                "username": payload.username.strip(),
                "role": payload.role,
            }
        }

    @application.post("/admin/logout")
    async def logout(request: Request) -> RedirectResponse:
        _require_mutation_access(request, required_role="viewer")
        raw_session = request.cookies.get(SESSION_COOKIE)
        if raw_session:
            request.app.state.auth_store.logout(raw_session)
        response = RedirectResponse("/admin/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE, path="/admin")
        return response

    @application.get("/admin/api/settings/telegram")
    async def get_telegram_settings(request: Request) -> dict[str, object]:
        _require_identity(request)
        return _public_telegram_settings(request.app.state.settings_store.get_telegram())

    @application.put("/admin/api/settings/telegram")
    async def put_telegram_settings(
        request: Request,
        payload: TelegramSettingsUpdate,
    ) -> dict[str, object]:
        identity = _require_mutation_access(request, required_role="editor")
        try:
            record = request.app.state.settings_store.save_telegram(
                payload,
                updated_by=identity.admin_id,
            )
        except SettingsConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return _public_telegram_settings(record)

    @application.get("/admin/api/settings/agent")
    async def get_agent_settings(request: Request) -> dict[str, object]:
        _require_identity(request)
        return _public_settings(request.app.state.settings_store.get_agent())

    @application.put("/admin/api/settings/agent")
    async def put_agent_settings(
        request: Request,
        payload: AgentSettingsUpdate,
    ) -> dict[str, object]:
        identity = _require_mutation_access(request, required_role="editor")
        try:
            record = request.app.state.settings_store.save_agent(
                payload,
                updated_by=identity.admin_id,
            )
        except SettingsConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return _public_settings(record)

    @application.get("/admin/api/settings/rag")
    async def get_rag_settings(request: Request) -> dict[str, object]:
        _require_identity(request)
        return _public_settings(request.app.state.settings_store.get_rag())

    @application.put("/admin/api/settings/rag")
    async def put_rag_settings(
        request: Request,
        payload: RagSettingsUpdate,
    ) -> dict[str, object]:
        identity = _require_mutation_access(request, required_role="editor")
        try:
            record = request.app.state.settings_store.save_rag(
                payload,
                updated_by=identity.admin_id,
            )
        except SettingsConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return _public_settings(record)

    @application.get("/admin", response_class=HTMLResponse)
    async def dashboard(request: Request) -> str:
        identity = _require_identity(request)
        return dashboard_html(identity.username, identity.role)

    @application.get("/health")
    async def health(request: Request) -> dict[str, str]:
        if not hasattr(request.app.state, "auth_store"):
            raise HTTPException(status_code=503, detail="starting")
        return {"status": "ok"}

    return application


def _require_identity(request: Request) -> AdminIdentity:
    raw_session = request.cookies.get(SESSION_COOKIE)
    identity = request.app.state.auth_store.get_identity(raw_session) if raw_session else None
    if identity is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return identity


def _require_mutation_access(request: Request, *, required_role: str) -> AdminIdentity:
    identity = _require_identity(request)
    csrf_token = request.headers.get("X-CSRF-Token", "")
    if not secrets.compare_digest(csrf_token, identity.csrf_token):
        raise HTTPException(status_code=403, detail="invalid CSRF token")
    role_rank = {"viewer": 0, "editor": 1, "admin": 2}
    if role_rank[identity.role] < role_rank[required_role]:
        raise HTTPException(status_code=403, detail="insufficient role")
    return identity


def _bootstrap_first_admin(store: AdminAuthStore) -> None:
    if store.count_admins():
        return
    username = os.getenv("ADMIN_BOOTSTRAP_USERNAME")
    password = os.getenv("ADMIN_BOOTSTRAP_PASSWORD")
    if not username or not password:
        raise RuntimeError(
            "no administrators exist; set ADMIN_BOOTSTRAP_USERNAME and "
            "ADMIN_BOOTSTRAP_PASSWORD for the first startup"
        )
    store.create_admin(username, password, role="admin")


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _public_telegram_settings(record: TelegramSettingsRecord) -> dict[str, object]:
    return {
        **record.settings.model_dump(mode="json"),
        "revision": record.revision,
        "bot_token_configured": bool(record.bot_token),
    }


def _public_settings(record: SettingsRecord) -> dict[str, object]:
    return {
        **record.settings.model_dump(mode="json"),
        "revision": record.revision,
    }


app = create_app()


async def _minimum_login_delay() -> None:
    import asyncio

    started = time.monotonic()
    await asyncio.sleep(max(0, 0.35 - (time.monotonic() - started)))
