# app/handlers.py

import logging
from aiogram import Router, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from app.models import IncomingMessage
from app.services.ai_agent import ai_agent
from app.middleware.session_middleware import SessionMiddleware

router = Router()
router.message.middleware(SessionMiddleware())
logger = logging.getLogger(__name__)


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет!\n\n"
        "Просто отправь мне любое сообщение, и я передам его AI агенту.\n"
    )


@router.message(F.text)
async def handle_message(message: Message, session_id: str = None, user_metadata: dict = None):
    # Создаём модель запроса
    incoming_message = IncomingMessage(
        session_id=session_id or f"temp_{message.from_user.id}",
        user_message=message.text,
        metadata=user_metadata or {}
    )

    # Отправляем индикатор набора текста
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        # Получаем структурированный ответ от AI-ядра
        response = await ai_agent.process_message(incoming_message)
        text = response.get("text", "Пустой ответ от агента")
        buttons = response.get("buttons", [])

        # Формируем клавиатуру, если есть кнопки
        reply_markup = None
        if buttons:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])]
                    for btn in buttons
                ]
            )
            reply_markup = keyboard

        # Отправляем ответ пользователю
        await message.answer(text, reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}", exc_info=True)
        await message.answer("Произошла ошибка при обращении к AI-агенту. Попробуйте позже.")


@router.message()
async def handle_other_messages(message: Message):
    await message.answer("Пожалуйста, отправьте текстовое сообщение.")