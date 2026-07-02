import asyncio
import logging
from config import BOT_TOKEN
from aiogram import Bot, Dispatcher
from aiogram.types import WebhookInfo
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from app.hendlers import router

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

WEBHOOK_HOST = "https://sycamore-glaucoma-citadel.ngrok-free.dev"
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

PORT = 8080

async def on_startup(dispatcher: Dispatcher):
    webhook_info = await bot.get_webhook_info()
    if webhook_info.url != WEBHOOK_URL:
        await bot.set_webhook(
            url=WEBHOOK_URL,
            allowed_updates=dispatcher.resolve_used_update_types(),
            drop_pending_updates=True
        )
        logging.info(f"Webhook set to {WEBHOOK_URL}")
    else:
        logging.info(f"Webhook already set correctly")

async def on_shutdown(dispatcher: Dispatcher):
    await bot.delete_webhook()
    logging.info("Webhook deleted")

def main():
    logging.basicConfig(level=logging.INFO)

    app = web.Application()

    dp.include_router(router)
    
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Запуск сервера
    logging.info(f"Starting webhook server on port {PORT}")
    logging.info(f"Webhook URL: {WEBHOOK_URL}")
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Exit')