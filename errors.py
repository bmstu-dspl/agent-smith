"""Единый формат ошибок и ответов для инструментов плагина.
исключения и обертка
"""
import functools
import json
import logging
import os

logger = logging.getLogger(__name__)


class PluginError(Exception):
    """Базовая ошибка плагина - от неё наследуются все остальные."""
    error_type = "internal_error"
    retryable = False

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ValidationError(PluginError):
    """Некорректные входные параметры (пр: дата в прошлом)"""
    error_type = "validation_error"


class AuthenticationError(PluginError):
    """Проблема с авторизацией у внешнего API"""
    error_type = "authentication_error"
    retryable = True


class BookingUnavailableError(PluginError):
    """Номер недоступен"""
    error_type = "booking_unavailable"


class ExternalServiceError(PluginError):
    """Сбой на стороне внешнего API (сеть, таймаут и тд)"""
    error_type = "external_service_error"
    retryable = True


def _to_error_dict(exc: Exception) -> dict:
    if isinstance(exc, PluginError):
        logger.warning("Ошибка инструмента [%s]: %s", exc.error_type, exc.message)
        return {
            "ok": False,
            "error_type": exc.error_type,
            "message": exc.message,
            "retryable": exc.retryable,
        }
    
    # Непредвидимая ошибка, баг
    # полный трейсбек/вывод оставляем для себя, наружу только общее сообщение
    logger.exception("Неожиданная ошибка в инструменте плагина")
    return {
        "ok": False,
        "error_type": "internal_error",
        "message": "Внутренняя ошибка сервиса, попробуйте позже",
        "retryable": True,
    }


def safe_tool(func):
    """Декоратор: приводит результат ЛЮБОГО инструмента (синхронного или
    асинхронного) к единому формату {"ok": true, "data": ...} или
    {"ok": false, "error_type": ..., ...}."""

    if asyncio.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
                return json.dumps({"ok": True, "data": result}, ensure_ascii=False)
            except Exception as exc:
                return json.dumps(_to_error_dict(exc), ensure_ascii=False)

        return async_wrapper

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            return json.dumps({"ok": True, "data": result}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps(_to_error_dict(exc), ensure_ascii=False)

    return sync_wrapper


def require_env(var_name: str) -> str:
    """Проверка при инициализации: переменная окружения обязана быть задана.
    Если нет, то падаем сразу
    """
    
    value = os.getenv(var_name)
    if not value:
        raise RuntimeError(
            f"Переменная окружения {var_name} не задана - плагин не может стартовать"
        )
    return value