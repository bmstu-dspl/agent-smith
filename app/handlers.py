import asyncio
import json
import logging
import os
from datetime import datetime, timezone

import httpx
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.middleware.session_middleware import SessionMiddleware
from app.models import IncomingMessage

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
    incoming = IncomingMessage(
        session_id=session_id or f"temp_{message.from_user.id}",
        user_message=message.text,
        metadata=user_metadata or {},
        timestamp=datetime.now(timezone.utc)
    )

    sent_message = await message.answer("⏳ Генерация ответа...")
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    full_text = ""
    buttons = []
    last_edit_text = ""

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

                    elif etype == "buttons":
                        raw_buttons = event.get("buttons", [])
                        buttons = [
                            {"text": b["text"], "callback_data": b["callback_data"]}
                            for b in raw_buttons
                        ]
                        logger.info(f"Получено кнопок: {len(buttons)}")

                    elif etype == "end":
                        logger.info("Поток завершён, отправляем финальное сообщение")
                        break

        reply_markup = None
        if buttons:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])]
                    for btn in buttons
                ]
            )
            reply_markup = keyboard

        final_text = full_text.strip() or "Агент вернул пустой ответ."
        await sent_message.edit_text(final_text, reply_markup=reply_markup)

    except httpx.HTTPStatusError as e:
        logger.error(f"Ошибка HTTP {e.response.status_code}")
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


@router.callback_query(F.data)
async def handle_callback_query(callback: CallbackQuery, session_id: str = None, user_metadata: dict = None):
    """
    Универсальный обработчик нажатий на кнопки.
    Отправляет callback_data в AI-ядро и возвращает ответ.
    """
    callback_data = callback.data
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    logger.info(f"Получен callback: {callback_data} от пользователя {user_id}")

    # НЕМЕДЛЕННО отвечаем на callback
    await callback.answer()

    # Удаляем кнопки у исходного сообщения
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        logger.warning(f"Не удалось удалить кнопки: {e}")

    # Отправляем начальное сообщение
    sent_message = await callback.message.answer("⏳ Обработка действия...")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Отправляем callback_data как обычное сообщение с специальным маркером
            # или добавляем в metadata информацию о том, что это callback
            payload = {
                "session_id": session_id or f"temp_{user_id}",
                "user_message": f"/callback_{callback_data}",  # Специальный маркер для callback
                "metadata": {
                    **(user_metadata or {}),
                    "is_callback": True,
                    "callback_data": callback_data
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            full_text = ""
            buttons = []
            last_edit_text = ""
            first_chunk_received = False

            await callback.bot.send_chat_action(chat_id=chat_id, action="typing")

            async with client.stream(
                "POST",
                AI_CORE_URL,  # Используем тот же эндпоинт
                json=payload
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

                        if not first_chunk_received:
                            first_chunk_received = True
                            try:
                                await sent_message.edit_text(full_text + "▌")
                                last_edit_text = full_text + "▌"
                            except Exception as e:
                                logger.warning(f"Ошибка при первом редактировании: {e}")
                        else:
                            new_text = full_text + "▌"
                            if new_text != last_edit_text:
                                try:
                                    await sent_message.edit_text(new_text)
                                    last_edit_text = new_text
                                except TelegramBadRequest as e:
                                    if "message is not modified" not in str(e):
                                        logger.warning(f"Ошибка при редактировании: {e}")

                    elif etype == "buttons":
                        raw_buttons = event.get("buttons", [])
                        buttons = [
                            {"text": b["text"], "callback_data": b["callback_data"]}
                            for b in raw_buttons
                        ]
                        logger.info(f"Получено кнопок: {len(buttons)}")

                    elif etype == "end":
                        logger.info("Поток завершён, отправляем финальное сообщение")
                        break

                    if not first_chunk_received:
                        await callback.bot.send_chat_action(chat_id=chat_id, action="typing")

        reply_markup = None
        if buttons:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])]
                    for btn in buttons
                ]
            )
            reply_markup = keyboard

        final_text = full_text.strip() or "Действие выполнено."
        await sent_message.edit_text(final_text, reply_markup=reply_markup)

    except httpx.TimeoutException:
        logger.error("Таймаут при обработке callback")
        await sent_message.edit_text("⏱️ Превышено время ожидания ответа от сервера.")
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        logger.error(f"Ошибка HTTP при обработке callback: статус {status_code}")
        await sent_message.edit_text(f"Ошибка сервера (код {status_code}). Попробуйте позже.")
    except httpx.RequestError as e:
        logger.error(f"Сетевая ошибка при обработке callback: {e}")
        await sent_message.edit_text("Не удалось соединиться с сервером.")
    except asyncio.TimeoutError:
        logger.error("Таймаут асинхронной операции")
        await sent_message.edit_text("Превышено время ожидания.")
    except Exception as e:
        logger.error(f"Неизвестная ошибка при обработке callback: {e}", exc_info=True)
        try:
            await sent_message.edit_text("Произошла непредвиденная ошибка.")
        except Exception:
            pass


@router.message()
async def handle_other_messages(message: Message):
    await message.answer("Пожалуйста, отправьте текстовое сообщение.")
