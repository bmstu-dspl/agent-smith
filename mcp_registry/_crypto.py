from __future__ import annotations

import json
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class McpRegistryConfigurationError(Exception):
    """Raised when mcp_registry encryption key is missing or invalid."""


def _get_fernet() -> Fernet:
    """Ключ шифрования берётся из окружения, никогда не хранится в базе или коде.
    Генерируется один раз через Fernet.generate_key() и кладётся в .env"""
    key = os.environ.get("MCP_SECRETS_ENCRYPTION_KEY")
    if not key:
        raise McpRegistryConfigurationError(
            "MCP_SECRETS_ENCRYPTION_KEY не задан — обязателен для хранения headers/query MCP-серверов"
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_json(data: dict[str, Any]) -> str:
    """Сериализует dict в JSON и шифрует"""
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    token = _get_fernet().encrypt(raw)
    return token.decode("ascii")


def decrypt_json(encrypted: str | None) -> dict[str, Any]:
    """Обратная операция. Возвращает пустой dict, если данных нет или расшифровка не удалась
    (например, ключ был сменён)"""
    if not encrypted:
        return {}
    try:
        raw = _get_fernet().decrypt(encrypted.encode("ascii"))
        return json.loads(raw.decode("utf-8"))
    except (InvalidToken, ValueError):
        return {}


def sanitize_error_message(message: str, secrets: dict[str, Any]) -> str:
    """Убирает из текста ошибки любые значения секретов (например, значения из headers),
    чтобы они случайно не утекли в error_message, который не шифруется."""
    sanitized = message
    for value in secrets.values():
        if isinstance(value, str) and value:
            sanitized = sanitized.replace(value, "***REDACTED***")
    return sanitized
