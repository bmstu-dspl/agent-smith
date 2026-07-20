import os

import pytest
from cryptography.fernet import Fernet

from mcp_registry._crypto import (
    McpRegistryConfigurationError,
    decrypt_json,
    encrypt_json,
    sanitize_error_message,
)


# --- encrypt_json / decrypt_json ---


def test_encrypt_decrypt_round_trip():
    """Базовый сценарий: что зашифровали — то и расшифровали, без потерь."""
    data = {"Authorization": "Bearer xyz123secret", "X-Api-Key": "abc"}

    encrypted = encrypt_json(data)
    decrypted = decrypt_json(encrypted)

    assert decrypted == data


def test_encrypt_produces_different_string_each_time():
    """Fernet добавляет случайную соль — одинаковые данные дают разные зашифрованные строки.
    Это нормально и ожидаемо, не баг."""
    data = {"token": "same-value"}

    first = encrypt_json(data)
    second = encrypt_json(data)

    assert first != second
    assert decrypt_json(first) == decrypt_json(second) == data


def test_encrypt_empty_dict():
    """Пустой словарь (сервер без заголовков) должен шифроваться и расшифровываться без ошибок."""
    encrypted = encrypt_json({})
    assert decrypt_json(encrypted) == {}


def test_decrypt_none_returns_empty_dict():
    """Если в базе NULL (сервер создан без headers) — должен вернуться пустой словарь, а не ошибка."""
    assert decrypt_json(None) == {}


def test_decrypt_empty_string_returns_empty_dict():
    assert decrypt_json("") == {}


def test_decrypt_garbage_string_returns_empty_dict():
    """Повреждённые данные не должны ронять систему — только тихо терять данные."""
    assert decrypt_json("this-is-not-a-valid-token") == {}


def test_decrypt_with_wrong_key_returns_empty_dict(monkeypatch):
    """Ключ шифрования сменили — старые данные больше не читаются, но приложение не падает."""
    encrypted = encrypt_json({"token": "secret"})

    monkeypatch.setenv("MCP_SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())

    assert decrypt_json(encrypted) == {}


def test_encrypt_raises_without_encryption_key(monkeypatch):
    """Без переменной окружения шифрование должно явно падать, а не молча использовать что-то по умолчанию."""
    monkeypatch.delenv("MCP_SECRETS_ENCRYPTION_KEY", raising=False)

    with pytest.raises(McpRegistryConfigurationError):
        encrypt_json({"token": "secret"})


def test_decrypt_raises_without_encryption_key_only_if_data_present(monkeypatch):
    """Если данных нет (None) — ошибка ключа не должна всплывать, т.к. расшифровывать нечего."""
    monkeypatch.delenv("MCP_SECRETS_ENCRYPTION_KEY", raising=False)

    assert decrypt_json(None) == {}


def test_encrypt_supports_nested_and_non_ascii_values():
    """Заголовки могут содержать не-ASCII текст и вложенные структуры — не должно падать на сериализации."""
    data = {"X-Comment": "тест на русском", "nested": {"a": 1, "b": [1, 2, 3]}}

    encrypted = encrypt_json(data)

    assert decrypt_json(encrypted) == data


# --- sanitize_error_message ---


def test_sanitize_replaces_all_secret_values():
    message = "Connection failed: Authorization=Bearer xyz123secret, timeout after 5s"
    secrets = {"Authorization": "Bearer xyz123secret"}

    result = sanitize_error_message(message, secrets)

    assert "xyz123secret" not in result
    assert "***REDACTED***" in result
    assert "timeout after 5s" in result  # остальной текст не должен пострадать


def test_sanitize_replaces_multiple_secrets():
    message = "headers: Bearer abc, query: key123"
    secrets = {"Authorization": "Bearer abc", "api_key": "key123"}

    result = sanitize_error_message(message, secrets)

    assert "Bearer abc" not in result
    assert "key123" not in result


def test_sanitize_with_no_secrets_returns_message_unchanged():
    message = "connection timed out"
    assert sanitize_error_message(message, {}) == message


def test_sanitize_ignores_non_string_secret_values():
    """Если в headers/query случайно оказалось не строковое значение (число, None, dict) —
    не должно падать с ошибкой при попытке .replace()."""
    message = "error occurred"
    secrets = {"retries": 3, "enabled": True, "extra": None, "nested": {"a": 1}}

    result = sanitize_error_message(message, secrets)

    assert result == message


def test_sanitize_empty_secret_value_does_not_break():
    """Пустая строка в качестве значения секрета не должна приводить к замене всего текста."""
    message = "normal error text"
    secrets = {"token": ""}

    result = sanitize_error_message(message, secrets)

    assert result == message


def test_sanitize_empty_message():
    assert sanitize_error_message("", {"token": "secret"}) == ""
