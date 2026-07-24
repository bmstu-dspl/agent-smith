from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import WebhookInfo
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import httpx
from sqlalchemy.orm import sessionmaker

# Добавляем текущую директорию в PYTHONPATH для импорта модулей
sys.path.append(str(Path(__file__).parent))

from app.escalation_service import EscalationService
from app.handlers import get_esc_service, router, set_esc_service, set_settings_provider
from app.live_config import LiveTelegramSettingsProvider
from app.middleware.session_middleware import SessionMiddleware
from app_runtime import AppRuntime
from config import LOG_LEVEL, PORT
from shared.redis_client import get_redis_client
from admin_panel.settings import SettingsStore

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Глобальные переменные
redis_client = None
runtime: AppRuntime | None = None
bot_instance: Bot | None = None
settings_provider: LiveTelegramSettingsProvider | None = None


def _env_bool(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


async def on_startup(dispatcher: Dispatcher) -> None:
    """Действия при запуске бота"""
    global redis_client, runtime, bot_instance, settings_provider
    
    logger.info("=" * 50)
    logger.info("ON_STARTUP CALLED!")
    logger.info("=" * 50)
    
    # Получаем бота из данных диспетчера или используем глобальный
    bot = dispatcher.workflow_data.get('bot')
    if bot is None:
        bot = bot_instance
    if bot is None:
        logger.error("Bot instance not found!")
        return
    
    # Инициализация Redis
    try:
        redis_client = await get_redis_client()
        if redis_client:
            logger.info("Redis connected")
    except Exception as e:
        logger.error(f"Redis initialization failed: {e}")

    if runtime is None or settings_provider is None:
        raise RuntimeError("bot runtime was not initialized before dispatcher startup")
    dispatcher["runtime"] = runtime
    dispatcher["memory"] = runtime.memory
    current_settings = await settings_provider.get()
    
    # Настройка SessionMiddleware с Redis (если доступен)
    session_middleware = SessionMiddleware(redis_client)
    
    # Удаляем старый middleware если есть
    try:
        for i, (mw, _) in enumerate(dispatcher.message.middleware._middlewares):
            if isinstance(mw, SessionMiddleware):
                dispatcher.message.middleware._middlewares.pop(i)
                break
    except Exception as e:
        logger.debug(f"No existing SessionMiddleware to remove: {e}")
    
    dispatcher.message.middleware(session_middleware)
    
    # Также добавляем для callback_query
    if hasattr(dispatcher, 'callback_query'):
        try:
            for i, (mw, _) in enumerate(dispatcher.callback_query.middleware._middlewares):
                if isinstance(mw, SessionMiddleware):
                    dispatcher.callback_query.middleware._middlewares.pop(i)
                    break
            dispatcher.callback_query.middleware(session_middleware)
        except Exception as e:
            logger.debug(f"Could not set middleware for callback_query: {e}")
    
    logger.info("SessionMiddleware configured")
    
    # Инициализация сервиса эскалации
    if current_settings.enable_escalation and current_settings.manager_group_id:
        try:
            esc_service = EscalationService(bot, current_settings.manager_group_id)
            set_esc_service(esc_service)
            
            # Проверяем, что сервис действительно установлен
            test_service = get_esc_service()
            if test_service:
                logger.info(f"Escalation service configured and verified")
                logger.info(f"   is_initialized: {test_service.is_initialized}")
                logger.info(f"   manager_group_id: {test_service.manager_group_id}")
            else:
                logger.error("Failed to verify escalation service")
            
            logger.info(
                "Escalation service initialized with group ID: %s",
                current_settings.manager_group_id,
            )
        except Exception as e:
            logger.error(f"Failed to initialize escalation service: {e}", exc_info=True)
    else:
        logger.warning("Management group is not configured; escalation service disabled.")
    
    # Настройка вебхука
    try:
        webhook_info = await bot.get_webhook_info()
        logger.info(f"Current webhook info: {webhook_info}")
        
        if webhook_info.url != current_settings.webhook_url:
            await bot.set_webhook(
                url=current_settings.webhook_url,
                allowed_updates=dispatcher.resolve_used_update_types(),
                drop_pending_updates=_env_bool("DROP_PENDING_UPDATES"),
            )
            logger.info("Webhook set to %s", current_settings.webhook_url)
        else:
            logger.info("Webhook already set correctly to %s", current_settings.webhook_url)
            
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}")
        raise
    
    logger.info("=" * 50)
    logger.info("BOT STARTED SUCCESSFULLY!")
    logger.info("=" * 50)


async def on_shutdown(dispatcher: Dispatcher) -> None:
    """Действия при остановке бота"""
    global runtime, redis_client, bot_instance
    
    logger.info("=" * 50)
    logger.info("ON_SHUTDOWN CALLED!")
    logger.info("=" * 50)
    
    # Получаем бота
    bot = dispatcher.workflow_data.get('bot')
    if bot is None:
        bot = bot_instance
    
    # Закрываем runtime
    if runtime is not None:
        try:
            runtime.close()
            runtime = None
            logger.info("Runtime closed")
        except Exception as e:
            logger.error(f"Error closing runtime: {e}")
    
    # Закрываем Redis
    if redis_client is not None:
        try:
            await redis_client.close()
            redis_client = None
            logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis: {e}")
    
    # Удаляем вебхук
    if bot:
        if _env_bool("DELETE_WEBHOOK_ON_SHUTDOWN"):
            try:
                await bot.delete_webhook()
                logger.info("Webhook deleted")
            except Exception as e:
                logger.error(f"Error deleting webhook: {e}")
        
        # Закрываем сессию бота
        try:
            await bot.session.close()
            logger.info("Bot session closed")
        except Exception as e:
            logger.error(f"Error closing bot session: {e}")
    
    logger.info("Bot stopped successfully!")


async def healthcheck(_: web.Request) -> web.Response:
    if runtime is None:
        raise web.HTTPServiceUnavailable(text="starting")
    try:
        runtime.database.healthcheck()
    except Exception:
        logging.exception("database healthcheck failed")
        raise web.HTTPServiceUnavailable(text="database unavailable") from None
    return web.Response(text="ok")


def main() -> None:
    """Основная функция запуска бота"""
    global bot_instance, runtime, settings_provider
    
    try:
        runtime = AppRuntime.from_env()
        encryption_key = os.getenv("CONFIG_SECRETS_ENCRYPTION_KEY") or os.getenv(
            "MCP_SECRETS_ENCRYPTION_KEY"
        )
        if not encryption_key:
            raise RuntimeError("CONFIG_SECRETS_ENCRYPTION_KEY is required")
        settings_provider = LiveTelegramSettingsProvider(
            SettingsStore(
                sessionmaker(bind=runtime.database.engine, expire_on_commit=False),
                encryption_key,
            )
        )
        initial_settings = settings_provider.load_initial()
        set_settings_provider(settings_provider)

        bot_instance = Bot(
            token=initial_settings.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        
        # Создаем диспетчер
        dp = Dispatcher()
        
        # Сохраняем бота в workflow_data
        dp.workflow_data['bot'] = bot_instance
        
        # Регистрируем обработчики запуска и остановки
        dp.startup.register(on_startup)
        dp.shutdown.register(on_shutdown)
        
        # Подключаем роутеры
        dp.include_router(router)
        
        # Создаем aiohttp приложение
        app = web.Application()
        app.router.add_get("/healthz", healthcheck)
        
        # Настраиваем обработчик вебхука
        webhook_requests_handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot_instance,
        )
        webhook_requests_handler.register(app, path=initial_settings.webhook_path)
        
        # ВАЖНО: используем setup_application для правильной инициализации
        setup_application(app, dp, bot=bot_instance)
        
        # Запускаем сервер
        logger.info("=" * 50)
        logger.info(f"Starting webhook server on port {PORT}")
        logger.info("Webhook URL: %s", initial_settings.webhook_url)
        logger.info(
            "Manager Group ID: %s",
            initial_settings.manager_group_id or "Not set",
        )
        logger.info("=" * 50)
        
        web.run_app(app, host="0.0.0.0", port=PORT)
        
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise
    finally:
        if runtime is not None:
            runtime.close()
            runtime = None
        logger.info("Server shutdown complete")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nBot stopped by user')
    except Exception as e:
        print(f'Fatal error: {e}')
        sys.exit(1)
