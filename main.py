# Бот-заглушка
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from dotenv import load_dotenv

# Загружаем переменные из файла .env (включая BOT_TOKEN)
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Диспетчер — объект, который раздаёт входящие сообщения нужным обработчикам
dp = Dispatcher()


# Обработчик срабатывает на любое текстовое сообщение
@dp.message()
async def echo_alive(message: Message) -> None:
    await message.answer("Бот жив!")


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=BOT_TOKEN)
    # Запускаем «long polling» - бот сам спрашивает у тг новые сообщения
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())