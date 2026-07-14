import json

import os

import logging
from datetime import datetime, timezone

import httpx
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

from app.models import IncomingMessage
from app.middleware.session_middleware import SessionMiddleware

router = Router()
router.message.middleware(SessionMiddleware())

logger = logging.getLogger(__name__)

AI_CORE_URL = os.getenv('AI_AGENT_URL', 'http://ai_agent:8000') + "/agent/process"


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет!\n\n"
        "Просто отправь мне любое сообщение, и я передам его AI агенту.\n"
    )


@router.message(F.text)
async def handle_message(message: Message, session_id: str = None, user_metadata: dict = None):
    """
    Принимает текстовое сообщение, отправляет в AI-ядро и стримит ответ,
    редактируя сообщение в реальном времени.
    """
    # Формируем объект запроса (Pydantic v2)
    incoming = IncomingMessage(
        session_id=session_id or f"temp_{message.from_user.id}",
        user_message=message.text,
        metadata=user_metadata or {},
        timestamp=datetime.now(timezone.utc)
    )

    # Отправляем начальное сообщение-заглушку, которое будем редактировать
    sent_message = await message.answer("⏳ Генерация ответа...")
    # Показываем статус "печатает"
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    full_text = ""
    buttons = []
    last_edit_text = ""  # для минимизации количества запросов к Telegram

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                AI_CORE_URL,
                json=incoming.model_dump(mode="json")
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue

                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        logger.error(f"Невалидный JSON в строке: {line}")
                        continue

                    etype = event.get("type")

                    if etype == "text_chunk":
                        chunk = event.get("content", "")
                        full_text += chunk

                        new_text = full_text + "▌"
                        if new_text != last_edit_text:
                            try:
                                await sent_message.edit_text(new_text)
                                last_edit_text = new_text
                            except TelegramBadRequest as e:
                                if "message is not modified" not in str(e):
                                    logger.warning(f"Ошибка при редактировании: {e}")
                                # если сообщение не изменилось, игнорируем

                    elif etype == "buttons":
                        raw_buttons = event.get("buttons", [])
                        buttons = [
                            {"text": b["text"], "callback_data": b["callback_data"]}
                            for b in raw_buttons
                        ]
                        logger.info(f"Получено кнопок: {len(buttons)}")

                    elif etype == "end":
                        logger.info("Поток завершён, отправляем финальное сообщение")
                        break  # выходим из цикла, дальше финальная отправка

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

        # Отправляем финальный текст без курсора
        final_text = full_text.strip() or "Агент вернул пустой ответ."
        await sent_message.edit_text(final_text, reply_markup=reply_markup)

    except httpx.HTTPStatusError as e:
        logger.error(f"Ошибка HTTP {e.response.status_code}: {e.response.text}")
        await sent_message.edit_text("Ошибка AI-ядра. Попробуйте позже.")
    except httpx.RequestError as e:
        logger.error(f"Сетевая ошибка: {e}")
        await sent_message.edit_text("Не удалось соединиться с AI-ядром.")
    except Exception as e:
        logger.error(f"Неизвестная ошибка: {e}", exc_info=True)
        try:
            await sent_message.edit_text("Произошла непредвиденная ошибка.")
        except Exception:
            pass


@router.callback_query(F.data == "book_room")
async def handle_book_room_callback(callback: CallbackQuery):
    """
    Обработчик нажатия на кнопку "Забронировать номер"
    """
    await callback.answer()  
    
    # Отправляем сообщение пользователю
    await callback.message.answer("Вы нажали на кнопку забронировать номер")

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        logger.warning(f"Не удалось убрать клавиатуру: {e}")


@router.message()
async def handle_other_messages(message: Message):
    await message.answer("Пожалуйста, отправьте текстовое сообщение.")
