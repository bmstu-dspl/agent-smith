import json
import pytest

from errors import (
    AuthenticationError,
    BookingUnavailableError,
    ValidationError,
    require_env,
    safe_tool,
)


def test_safe_tool_wraps_success():
    @safe_tool
    def ok_func():
        return {"foo": "bar"}

    result = json.loads(ok_func())
    assert result["ok"] is True
    assert result["data"] == {"foo": "bar"}


def test_safe_tool_wraps_known_error():
    @safe_tool
    def failing_func():
        raise ValidationError("плохие данные")

    result = json.loads(failing_func())
    assert result["ok"] is False
    assert result["error_type"] == "validation_error"
    assert result["retryable"] is False
    assert "плохие данные" in result["message"]


def test_safe_tool_wraps_unexpected_error():
    @safe_tool
    def broken_func():
        return 1 / 0  # непредвиденная ошибка, не PluginError

    result = json.loads(broken_func())
    assert result["ok"] is False
    assert result["error_type"] == "internal_error"
    assert result["retryable"] is True
    # наружу не должно утекать техническое сообщение
    assert "ZeroDivision" not in result["message"]


def test_require_env_raises_when_missing(monkeypatch):
    monkeypatch.delenv("SOME_TEST_VAR", raising=False)
    with pytest.raises(RuntimeError):
        require_env("SOME_TEST_VAR")


def test_require_env_returns_value_when_present(monkeypatch):
    monkeypatch.setenv("SOME_TEST_VAR", "hello")
    assert require_env("SOME_TEST_VAR") == "hello"


def test_error_retryable_flags():
    assert AuthenticationError("x").retryable is True
    assert ValidationError("x").retryable is False
    assert BookingUnavailableError("x").retryable is False
