# Бот-заглушка
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from dotenv import load_dotenv

from app_runtime import AppRuntime

# Загружаем переменные из файла .env (включая BOT_TOKEN)
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Диспетчер — объект, который раздаёт входящие сообщения нужным обработчикам
dp = Dispatcher()
runtime: AppRuntime | None = None


# Обработчик срабатывает на любое текстовое сообщение
@dp.message()
async def echo_alive(message: Message) -> None:
    await message.answer("Бот жив!")


async def on_startup() -> None:
    global runtime

    runtime = AppRuntime.from_env()
    dp["runtime"] = runtime
    dp["memory"] = runtime.memory


async def on_shutdown() -> None:
    global runtime

    if runtime is not None:
        runtime.close()
        runtime = None


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=BOT_TOKEN)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    # Запускаем «long polling» - бот сам спрашивает у тг новые сообщения
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
