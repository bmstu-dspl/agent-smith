from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from app.handlers import router, set_esc_service, get_esc_service
from app.escalation_service import EscalationService
from app_runtime import AppRuntime
from config import (
    BOT_TOKEN, 
    MANAGER_GROUP_ID, 
    WEBHOOK_URL, 
    WEBHOOK_PATH, 
    PORT,
    LOG_LEVEL
)

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
runtime: AppRuntime | None = None


def _env_bool(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


async def on_startup(dispatcher: Dispatcher) -> None:
    """Действия при запуске бота"""
    global runtime
    
    logger.info("=" * 50)
    logger.info("🚀 ON_STARTUP CALLED!")
    logger.info("=" * 50)
    
    # Инициализация runtime
    try:
        runtime = AppRuntime.from_env()
        dispatcher["runtime"] = runtime
        dispatcher["memory"] = runtime.memory
        logger.info("✅ Runtime initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize runtime: {e}")
    
    # Инициализируем сервис эскалации
    logger.info(f"📋 MANAGER_GROUP_ID from config: {MANAGER_GROUP_ID}")
    logger.info(f"📋 MANAGER_GROUP_ID type: {type(MANAGER_GROUP_ID)}")
    
    if MANAGER_GROUP_ID:
        try:
            # Создаем сервис
            esc_service = EscalationService(bot, MANAGER_GROUP_ID)
            logger.info(f"✅ EscalationService instance created")
            
            # Сохраняем в глобальную переменную через setter
            set_esc_service(esc_service)
            logger.info(f"✅ Escalation service set in global variable")
            
            # Проверяем, что сервис действительно инициализирован
            test_service = get_esc_service()
            if test_service:
                logger.info(f"✅ Escalation service retrieved successfully")
                logger.info(f"   is_initialized: {test_service.is_initialized}")
                logger.info(f"   manager_group_id: {test_service.manager_group_id}")
            else:
                logger.error("❌ Failed to retrieve escalation service after setting")
            
            logger.info(f"✅ Escalation service initialized with group ID: {MANAGER_GROUP_ID}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize escalation service: {e}", exc_info=True)
    else:
        logger.warning("⚠️ MANAGER_GROUP_ID not set or is 0! Escalation service will not work.")
        logger.warning("⚠️ Please add MANAGER_GROUP_ID to .env file")
    
    # Настройка вебхука
    try:
        webhook_info = await bot.get_webhook_info()
        logger.info(f"Current webhook info: {webhook_info}")
        
        if webhook_info.url != WEBHOOK_URL:
            await bot.set_webhook(
                url=WEBHOOK_URL,
                allowed_updates=dispatcher.resolve_used_update_types(),
                drop_pending_updates=_env_bool("DROP_PENDING_UPDATES"),
            )
            logger.info(f"✅ Webhook set to {WEBHOOK_URL}")
        else:
            logger.info(f"ℹ️ Webhook already set correctly to {WEBHOOK_URL}")
            
    except Exception as e:
        logger.error(f"❌ Failed to set webhook: {e}")
        raise
    
    logger.info("=" * 50)
    logger.info("✅ BOT STARTED SUCCESSFULLY!")
    logger.info("=" * 50)


async def on_shutdown(dispatcher: Dispatcher) -> None:
    """Действия при остановке бота"""
    global runtime
    
    logger.info("=" * 50)
    logger.info("🛑 ON_SHUTDOWN CALLED!")
    logger.info("=" * 50)
    
    # Закрываем runtime
    if runtime is not None:
        try:
            runtime.close()
            runtime = None
            logger.info("✅ Runtime closed")
        except Exception as e:
            logger.error(f"❌ Error closing runtime: {e}")
    
    # Удаляем вебхук
    if _env_bool("DELETE_WEBHOOK_ON_SHUTDOWN"):
        try:
            await bot.delete_webhook()
            logger.info("✅ Webhook deleted")
        except Exception as e:
            logger.error(f"❌ Error deleting webhook: {e}")
    
    # Закрываем сессию бота
    try:
        await bot.session.close()
        logger.info("✅ Bot session closed")
    except Exception as e:
        logger.error(f"❌ Error closing bot session: {e}")
    
    logger.info("✅ Bot stopped successfully!")


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
    
    # Регистрируем обработчики запуска и остановки ДО того как подключаем роутеры
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
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    # ВАЖНО: используем setup_application для правильной инициализации
    setup_application(app, dp, bot=bot)
    
    # Запускаем сервер
    logger.info("=" * 50)
    logger.info(f"🚀 Starting webhook server on port {PORT}")
    logger.info(f"📡 Webhook URL: {WEBHOOK_URL}")
    logger.info(f"👥 Manager Group ID: {MANAGER_GROUP_ID or 'Not set'}")
    logger.info("=" * 50)
    
    try:
        web.run_app(app, host="0.0.0.0", port=PORT, print=None)
    except KeyboardInterrupt:
        logger.info("⏹️ Server stopped by user")
    except Exception as e:
        logger.error(f"❌ Server error: {e}")
        raise
    finally:
        logger.info("🛑 Server shutdown complete")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n⏹️ Bot stopped by user')
    except Exception as e:
        print(f'❌ Fatal error: {e}')
        sys.exit(1)
