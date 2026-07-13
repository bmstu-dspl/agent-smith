from __future__ import annotations

import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web

from app.handlers import router
from app_runtime import AppRuntime
from config import BOT_TOKEN

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
runtime: AppRuntime | None = None

WEBHOOK_HOST = os.environ["WEBHOOK_HOST"].rstrip("/")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
PORT = int(os.getenv("PORT", "8080"))


def _env_bool(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


async def on_startup(dispatcher: Dispatcher) -> None:
    global runtime

    runtime = AppRuntime.from_env()
    dispatcher["runtime"] = runtime
    dispatcher["memory"] = runtime.memory

    webhook_info = await bot.get_webhook_info()
    if webhook_info.url != WEBHOOK_URL:
        await bot.set_webhook(
            url=WEBHOOK_URL,
            allowed_updates=dispatcher.resolve_used_update_types(),
            drop_pending_updates=_env_bool("DROP_PENDING_UPDATES"),
        )
        logging.info("Telegram webhook configured")
    else:
        logging.info("Telegram webhook already configured")


async def on_shutdown(_: Dispatcher) -> None:
    global runtime

    if runtime is not None:
        runtime.close()
        runtime = None
    if _env_bool("DELETE_WEBHOOK_ON_SHUTDOWN"):
        await bot.delete_webhook()
        logging.info("Telegram webhook deleted")
    await bot.session.close()


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
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    application = web.Application()
    application.router.add_get("/healthz", healthcheck)
    dp.include_router(router)

    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(application, path=WEBHOOK_PATH)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logging.info("Starting webhook server on port %s", PORT)
    web.run_app(application, host="0.0.0.0", port=PORT, print=None)


if __name__ == "__main__":
    main()
