from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update

from DB import PostgresDatabase

from ._crypto import decrypt_json, encrypt_json, sanitize_error_message
from ._models import McpServerModel

@dataclass(slots=True, frozen=True)
class McpServer:
    server_id: str
    name: str
    transport_type: str
    url: str
    headers: dict[str, Any]       # уже расшифрованные, готовые к использованию
    query_params: dict[str, Any]  # уже расшифрованные
    is_active: bool
    last_connected_at: datetime | None
    error_message: str | None


class McpServerStore:
    """Реестр MCP-серверов. headers/query_params шифруются перед записью в БД
    и расшифровываются при чтении"""

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def add_server(
        self,
        name: str,
        url: str,
        transport_type: str = "sse",
        headers: dict[str, Any] | None = None,
        query_params: dict[str, Any] | None = None,
    ) -> str:
        server_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        with self._database.session() as session:
            session.add(
                McpServerModel(
                    server_id=server_id,
                    name=name,
                    transport_type=transport_type,
                    url=url,
                    headers_encrypted=encrypt_json(headers or {}),
                    query_params_encrypted=encrypt_json(query_params or {}),
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
        return server_id

    def get_server(self, server_id: str) -> McpServer | None:
        with self._database.session() as session:
            model = session.get(McpServerModel, server_id)

            return _to_dataclass(model) if model else None

    def list_servers(self, *, only_active: bool = False) -> list[McpServer]:
        statement = select(McpServerModel).order_by(McpServerModel.created_at)
        if only_active:
            statement = statement.where(McpServerModel.is_active.is_(True))
        with self._database.session() as session:
            return [_to_dataclass(model) for model in session.scalars(statement)]

    def set_active(self, server_id: str, is_active: bool) -> None:
        statement = (
            update(McpServerModel)
            .where(McpServerModel.server_id == server_id)
            .values(is_active=is_active, updated_at=datetime.now(timezone.utc))
        )
        with self._database.session() as session:
            session.execute(statement)

    def update_connection_status(
        self, server_id: str, *, success: bool, error_message: str | None = None
    ) -> None:
        """Вызывается после попытки достучаться до сервера (tools/list) — фиксирует результат проверки связи.
        error_message перед записью очищается от значений секретов (headers/query),
        чтобы они не утекли через текст исключения HTTP-клиента."""
        now = datetime.now(timezone.utc)
        values: dict[str, Any] = {"updated_at": now}

        if success:
            values["last_connected_at"] = now
            values["error_message"] = None
        elif error_message is not None:
            server = self.get_server(server_id)
            secrets = {**server.headers, **server.query_params} if server else {}
            values["error_message"] = sanitize_error_message(error_message, secrets)

        statement = update(McpServerModel).where(McpServerModel.server_id == server_id).values(**values)
        with self._database.session() as session:
            session.execute(statement)

    def update_credentials(
        self, server_id: str, *, headers: dict[str, Any] | None = None, query_params: dict[str, Any] | None = None
    ) -> None:
        """Обновление секретов сервера (например, при ротации токена) — отдельно от прочих полей."""
        values: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
        if headers is not None:
            values["headers_encrypted"] = encrypt_json(headers)
        if query_params is not None:
            values["query_params_encrypted"] = encrypt_json(query_params)

        statement = update(McpServerModel).where(McpServerModel.server_id == server_id).values(**values)
        with self._database.session() as session:
            session.execute(statement)

    def delete_server(self, server_id: str) -> None:
        with self._database.session() as session:
            model = session.get(McpServerModel, server_id)
            if model is not None:
                session.delete(model)
def _to_dataclass(model: McpServerModel) -> McpServer:
    return McpServer(
        server_id=model.server_id,
        name=model.name,
        transport_type=model.transport_type,
        url=model.url,
        headers=decrypt_json(model.headers_encrypted),
        query_params=decrypt_json(model.query_params_encrypted),
        is_active=model.is_active,
        last_connected_at=model.last_connected_at,
        error_message=model.error_message,
    )

