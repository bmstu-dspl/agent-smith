import asyncio
import json
import logging
import os
from datetime import datetime, timezone

import httpx
from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.chat_action import ChatActionSender
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.middleware.session_middleware import SessionMiddleware
from app.models import IncomingMessage
from app.escalation_service import EscalationService

from app.live_config import LiveTelegramSettingsProvider
from app.telegram_formatting import AgentResponseStream

router = Router()

logger = logging.getLogger(__name__)

# Глобальная переменная для сервиса эскалации
_esc_service: EscalationService = None
_settings_provider: LiveTelegramSettingsProvider | None = None


# Определяем состояния
class UserStates(StatesGroup):
    """Состояния пользователя"""
    default = State()  # Обычный режим (AI)
    with_manager = State()  # Режим общения с менеджером


def set_esc_service(service: EscalationService):
    """Установить сервис эскалации"""
    global _esc_service
    _esc_service = service
    logger.info(f"Escalation service set: {service}")


def get_esc_service():
    """Получить сервис эскалации"""
    return _esc_service


def set_settings_provider(provider: LiveTelegramSettingsProvider) -> None:
    global _settings_provider
    _settings_provider = provider


async def _get_runtime_settings():
    if _settings_provider is None:
        raise RuntimeError("Telegram settings provider is not initialized")
    return await _settings_provider.get()


def escape_markdown(text: str) -> str:
    """Экранирует специальные символы для Markdown"""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


# ==================== КОМАНДЫ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ ====================

@router.message(Command("start"))
async def cmd_start(
    message: Message,
    state: FSMContext,
    session_middleware: SessionMiddleware,
):
    """Команда /start - сброс состояния"""
    await session_middleware.rotate_session(message.from_user.id)
    await state.set_state(UserStates.default)
    await message.answer(
        "Привет! Я ИИ-помощник.\n\n"
        "Просто отправь мне сообщение, и я помогу с решением задачи.\n"
        "Если нужна помощь специалиста, отправь команду /help"
    )


@router.message(Command("new"))
async def cmd_new(
    message: Message,
    state: FSMContext,
    session_middleware: SessionMiddleware,
):
    """Start a new AI context without replaying onboarding instructions."""
    await session_middleware.rotate_session(message.from_user.id)
    await state.set_state(UserStates.default)
    await message.answer("Новый диалог начат. Чем я могу помочь?")


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext):
    """Команда для вызова менеджера"""
    esc_service = get_esc_service()
    runtime_settings = await _get_runtime_settings()
    if esc_service is not None:
        esc_service.update_manager_group_id(
            runtime_settings.manager_group_id if runtime_settings.enable_escalation else None
        )
    
    if esc_service is None:
        await message.answer(
            "Сервис поддержки временно недоступен. Попробуйте позже."
        )
        return
    
    # Проверяем, есть ли уже активная эскалация
    if message.from_user.id in esc_service.active_escalations:
        escalation = esc_service.active_escalations[message.from_user.id]
        if escalation["status"] in ["pending", "active"]:
            await message.answer("У вас уже есть активный запрос к менеджеру.")
            return
    
    # Создаем эскалацию
    success = await esc_service.escalate_to_managers(
        message,
        reason="Пользователь запросил помощь через /help"
    )
    
    if success:
        # Переключаем пользователя в режим менеджера
        await state.set_state(UserStates.with_manager)
        logger.info(f"User {message.from_user.id} switched to with_manager state")
    else:
        await state.set_state(UserStates.default)


@router.message(Command("end_help"))
async def cmd_end_help(message: Message, state: FSMContext):
    """Команда для завершения общения с менеджером"""
    esc_service = get_esc_service()
    
    if esc_service:
        # Закрываем эскалацию если она есть
        if message.from_user.id in esc_service.active_escalations:
            await esc_service.close_escalation(
                message.from_user.id, 
                "закрыт пользователем через /end_help"
            )
            await message.answer(
                "Диалог с менеджером завершен. Вы снова можете общаться с AI-помощником."
            )
        else:
            await message.answer("У вас нет активного диалога с менеджером.")
    
    await state.set_state(UserStates.default)


@router.message(Command("test_escalation"))
async def cmd_test_escalation(message: Message):
    """Тестовая команда для проверки эскалации"""
    esc_service = get_esc_service()
    
    if esc_service is None:
        await message.answer("Escalation service is None")
        return
    
    status = f"Escalation service status:\n"
    status += f"is_initialized: {esc_service.is_initialized}\n"
    status += f"manager_group_id: {esc_service.manager_group_id}\n"
    status += f"active_escalations: {len(esc_service.active_escalations)}\n\n"
    
    # Показываем активные эскалации
    if esc_service.active_escalations:
        status += "Active requests:\n"
        for user_id, esc in esc_service.active_escalations.items():
            status += f"  • User {user_id}: {esc['status']} (thread: {esc.get('thread_id', 'None')})\n"
    
    await message.answer(status)


@router.message(Command("my_status"))
async def cmd_my_status(message: Message, state: FSMContext):
    """Показывает текущий статус пользователя"""
    current_state = await state.get_state()
    esc_service = get_esc_service()
    
    status = f"Your status:\n"
    status += f"State: {current_state or 'default'}\n\n"
    
    if esc_service and message.from_user.id in esc_service.active_escalations:
        esc = esc_service.active_escalations[message.from_user.id]
        status += f"Request to manager:\n"
        status += f"  • Status: {esc['status']}\n"
        status += f"  • Manager: {esc.get('manager_name', 'Not assigned')}\n"
        status += f"  • Thread: {esc.get('thread_id', 'Not created')}\n"
    else:
        status += "No active requests to manager."
    
    await message.answer(status)


# ==================== КОМАНДЫ ДЛЯ МЕНЕДЖЕРОВ ====================

@router.message(Command("close_ticket"))
async def cmd_close_ticket(message: Message):
    """Закрывает текущий тикет (только для менеджеров в треде)"""
    # Проверяем, что сообщение в треде
    if not message.message_thread_id:
        await message.reply("Эта команда доступна только в тредах.")
        return
    
    esc_service = get_esc_service()
    if esc_service is None:
        await message.reply("Сервис недоступен.")
        return
    
    thread_id = message.message_thread_id
    user_id = esc_service.thread_users.get(thread_id)
    
    if not user_id:
        await message.reply(f"Тред {thread_id} не привязан к пользователю.")
        return
    
    if user_id not in esc_service.active_escalations:
        await message.reply("Запрос уже закрыт.")
        return
    
    # Закрываем запрос
    await esc_service.close_escalation(
        user_id, 
        f"закрыт менеджером {message.from_user.full_name}"
    )
    
    await message.reply(f"Диалог с пользователем {user_id} закрыт.")
    
    # Уведомляем пользователя
    escalation = esc_service.active_escalations.get(user_id)
    if escalation:
        try:
            await esc_service.bot.send_message(
                chat_id=escalation["user_chat_id"],
                text="Диалог с менеджером завершен."
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя: {e}")


@router.message(Command("tickets_status"))
async def cmd_tickets_status(message: Message):
    """Показывает статус всех запросов (только для менеджеров)"""
    esc_service = get_esc_service()
    if esc_service is None:
        await message.reply("Сервис недоступен.")
        return
    
    status = await esc_service.get_manager_status()
    await message.reply(status)


@router.message(Command("check_links"))
async def cmd_check_links(message: Message):
    """Проверяет текущие связи между тредами и пользователями (для отладки)"""
    esc_service = get_esc_service()
    if esc_service is None:
        await message.reply("Сервис недоступен.")
        return
    
    status = "Current links:\n\n"
    status += "user_threads:\n"
    if esc_service.user_threads:
        for user_id, thread_id in esc_service.user_threads.items():
            status += f"  • User {user_id} -> Thread {thread_id}\n"
    else:
        status += "  • (empty)\n"
    
    status += "\nthread_users:\n"
    if esc_service.thread_users:
        for thread_id, user_id in esc_service.thread_users.items():
            status += f"  • Thread {thread_id} -> User {user_id}\n"
    else:
        status += "  • (empty)\n"
    
    status += f"\nTotal links: {len(esc_service.thread_users)}"
    
    await message.reply(status)


@router.message(Command("get_group_id"))
async def cmd_get_group_id(message: Message):
    """Получить ID текущей группы (только для администраторов)"""
    if message.chat.type in ["group", "supergroup"]:
        chat_id = message.chat.id
        chat_title = message.chat.title or "Без названия"
        
        await message.answer(
            f"Group info:\n"
            f"Name: {chat_title}\n"
            f"ID: {chat_id}\n\n"
            f"Save this ID in Admin panel → Telegram settings → Management group ID"
        )
    else:
        await message.answer("This command works only in groups.")


# ==================== ОБРАБОТЧИК СООБЩЕНИЙ ИЗ ГРУППЫ МЕНЕДЖЕРОВ ====================

@router.message(F.chat.type.in_({"group", "supergroup"}))
async def handle_manager_message(message: Message):
    """
    Обрабатывает сообщения от менеджеров в группе.
    - Сообщения в тредах пересылаются пользователям
    - Сообщения в общем чате игнорируются (кроме команд)
    """
    runtime_settings = await _get_runtime_settings()
    if message.chat.id != runtime_settings.manager_group_id:
        return

    # Игнорируем команды
    if message.text and message.text.startswith('/'):
        return
    
    # Игнорируем сообщения от самого бота
    bot_id = (await message.bot.me()).id
    if message.from_user and message.from_user.id == bot_id:
        logger.info(f"Игнорируем сообщение от бота в треде {message.message_thread_id}")
        return
    
    # Проверяем, что сообщение в треде
    if not message.message_thread_id:
        await message.reply(
            "Это сообщение не в треде.\n"
            "Чтобы ответить пользователю, напишите сообщение в его треде.\n"
            "Чтобы создать тред, нажмите 'Принять запрос' в общем чате."
        )
        return
    
    esc_service = get_esc_service()
    if esc_service is None:
        await message.reply("Сервис недоступен.")
        return
    
    # Отладочная информация
    logger.info(f"Получено сообщение из треда {message.message_thread_id}")
    logger.info(f"Текущие связи thread_users: {esc_service.thread_users}")
    
    # Пересылаем сообщение пользователю
    await esc_service.forward_message_to_user(message)


# ==================== ОБРАБОТЧИКИ СООБЩЕНИЙ ОТ ПОЛЬЗОВАТЕЛЕЙ ====================

# Обработчик сообщений от пользователей в режиме с менеджером
@router.message(UserStates.with_manager, F.text)
async def handle_user_with_manager(
    message: Message, 
    state: FSMContext,
    session_id: str = None, 
    user_metadata: dict = None
):
    """Обрабатывает сообщения от пользователя, когда он в режиме с менеджером"""
    esc_service = get_esc_service()
    
    if esc_service is None:
        await message.answer("Сервис недоступен. Переключаю в обычный режим.")
        await state.set_state(UserStates.default)
        return
    
    user_id = message.from_user.id
    
    # Проверяем, есть ли активная эскалация
    if user_id not in esc_service.active_escalations:
        await message.answer(
            "У вас нет активного диалога с менеджером. Переключаю в обычный режим."
        )
        await state.set_state(UserStates.default)
        return
    
    escalation = esc_service.active_escalations[user_id]
    
    if escalation["status"] != "active":
        if escalation["status"] == "pending":
            await message.answer(
                "Ваш запрос еще не принят менеджером. Ожидайте ответа.\n"
                "Если хотите отменить запрос, используйте /end_help"
            )
            return
        elif escalation["status"] == "closed":
            await message.answer(
                "Ваш диалог с менеджером завершен. Переключаю в обычный режим."
            )
            await state.set_state(UserStates.default)
            return
    
    # Пересылаем сообщение менеджеру (без лишних уведомлений)
    try:
        thread_id = escalation.get("thread_id")
        safe_name = escape_markdown(escalation['user_full_name'])
        
        if thread_id:
            # Отправляем в тред
            await message.bot.send_message(
                chat_id=esc_service.manager_group_id,
                message_thread_id=thread_id,
                text=f"{safe_name}:\n{message.text}"
            )
            logger.info(f"Сообщение от пользователя {user_id} переслано менеджеру в тред {thread_id}")
        else:
            # Если треда нет
            await message.bot.send_message(
                chat_id=esc_service.manager_group_id,
                text=f"{safe_name}:\n{message.text}\n\n"
                     f"Тред не создан! Менеджер должен принять запрос."
            )
            logger.warning(f"Нет треда для пользователя {user_id}")
        
    except Exception as e:
        logger.error(f"Ошибка при пересылке сообщения менеджеру: {e}")
        await message.answer("Не удалось отправить сообщение менеджеру. Попробуйте позже.")


# Обработчик сообщений от пользователей в обычном режиме (AI)
@router.message(UserStates.default, F.text)
async def handle_user_default(
    message: Message, 
    state: FSMContext,
    session_id: str = None, 
    user_metadata: dict = None
):
    """Обрабатывает сообщения от пользователя в обычном режиме (AI)"""
    
    # Обработка AI-агентом
    incoming = IncomingMessage(
        session_id=session_id or f"temp_{message.from_user.id}",
        user_message=message.text,
        metadata=user_metadata or {},
        timestamp=datetime.now(timezone.utc)
    )

    response_stream = AgentResponseStream(
        bot=message.bot,
        chat_id=message.chat.id,
        draft_id=message.message_id,
        message_thread_id=message.message_thread_id,
    )
    full_text = ""
    buttons = []

    try:
        async with ChatActionSender.typing(
            chat_id=message.chat.id,
            bot=message.bot,
            message_thread_id=message.message_thread_id,
            interval=4.0,
        ):
            await response_stream.start()
            runtime_settings = await _get_runtime_settings()
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    runtime_settings.ai_agent_url.rstrip("/") + "/agent/process",
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
                            await response_stream.update(full_text)

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
            await response_stream.finalize(
                final_text,
                reply_markup=reply_markup,
            )

    except httpx.HTTPStatusError as e:
        logger.error(f"Ошибка HTTP {e.response.status_code}")
        await response_stream.finalize("Ошибка AI-ядра. Попробуйте позже.")
    except httpx.RequestError as e:
        logger.error(f"Сетевая ошибка: {e}")
        await response_stream.finalize("Не удалось соединиться с AI-ядром.")
    except Exception as e:
        logger.error(f"Неизвестная ошибка: {e}", exc_info=True)
        try:
            await response_stream.finalize("Произошла непредвиденная ошибка.")
        except Exception:
            pass


# ==================== ОБРАБОТЧИКИ CALLBACK ====================

@router.callback_query(F.data.startswith("take_ticket_"))
async def handle_take_ticket(callback: CallbackQuery, state: FSMContext):
    """Обработчик принятия запроса менеджером"""
    esc_service = get_esc_service()
    if esc_service is None:
        await callback.answer("Сервис недоступен")
        return
    
    user_id = int(callback.data.split("_")[2])
    logger.info(f"Менеджер {callback.from_user.id} принимает запрос от пользователя {user_id}")
    
    success = await esc_service.take_ticket(callback, user_id)
    
    if success:
        # Переключаем пользователя в режим с менеджером
        await state.set_state(UserStates.with_manager)
        logger.info(f"User {user_id} switched to with_manager state by manager")
        
        # Отправляем уведомление в тред
        escalation = esc_service.active_escalations.get(user_id)
        if escalation and escalation.get("thread_id"):
            try:
                safe_name = escape_markdown(escalation['user_full_name'])
                await callback.bot.send_message(
                    chat_id=esc_service.manager_group_id,
                    message_thread_id=escalation["thread_id"],
                    text=(
                        f"Начинаем общение с пользователем {safe_name}.\n\n"
                        f"Инструкция:\n"
                        f"- Все сообщения в этом треде будут пересылаться пользователю.\n"
                        f"- Для завершения диалога используйте /close_ticket\n"
                        f"- Для просмотра всех запросов используйте /tickets_status"
                    )
                )
                logger.info(f"Отправлено приветствие в тред {escalation['thread_id']}")
            except Exception as e:
                logger.error(f"Ошибка при отправке приветствия в тред: {e}")
        
        await callback.answer("Запрос принят, тред создан")
    else:
        await callback.answer("Не удалось принять запрос")


@router.callback_query(F.data.startswith("reject_ticket_"))
async def handle_reject_ticket(callback: CallbackQuery):
    """Обработчик отклонения запроса менеджером"""
    esc_service = get_esc_service()
    if esc_service is None:
        await callback.answer("Сервис недоступен")
        return
    
    user_id = int(callback.data.split("_")[2])
    logger.info(f"Менеджер {callback.from_user.id} отклоняет запрос от пользователя {user_id}")
    
    await esc_service.reject_ticket(callback, user_id)


@router.callback_query(F.data)
async def handle_callback_query(
    callback: CallbackQuery, 
    state: FSMContext,
    session_id: str = None, 
    user_metadata: dict = None
):
    """Универсальный обработчик нажатий на кнопки (не из эскалации)"""
    # Проверяем, не является ли это callback от эскалации (уже обработано выше)
    if callback.data.startswith("take_ticket_") or callback.data.startswith("reject_ticket_"):
        return
    
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

    response_stream = AgentResponseStream(
        bot=callback.bot,
        chat_id=chat_id,
        message_thread_id=callback.message.message_thread_id,
    )

    try:
        runtime_settings = await _get_runtime_settings()
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "session_id": session_id or f"temp_{user_id}",
                "user_message": callback_data,
                "message_type": "callback",
                "metadata": {
                    **(user_metadata or {}),
                    "callback_data": callback_data,
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            full_text = ""
            buttons = []

            async with ChatActionSender.typing(
                chat_id=chat_id,
                bot=callback.bot,
                message_thread_id=callback.message.message_thread_id,
                interval=4.0,
            ):
                await response_stream.start()
                async with client.stream(
                    "POST",
                    runtime_settings.ai_agent_url.rstrip("/") + "/agent/process",
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
                            await response_stream.update(full_text)

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

                final_text = full_text.strip() or "Действие выполнено."
                await response_stream.finalize(
                    final_text,
                    reply_markup=reply_markup,
                )

    except httpx.TimeoutException:
        logger.error("Таймаут при обработке callback")
        await response_stream.finalize("Превышено время ожидания ответа от сервера.")
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        logger.error(f"Ошибка HTTP при обработке callback: статус {status_code}")
        await response_stream.finalize(f"Ошибка сервера (код {status_code}). Попробуйте позже.")
    except httpx.RequestError as e:
        logger.error(f"Сетевая ошибка при обработке callback: {e}")
        await response_stream.finalize("Не удалось соединиться с сервером.")
    except asyncio.TimeoutError:
        logger.error("Таймаут асинхронной операции")
        await response_stream.finalize("Превышено время ожидания.")
    except Exception as e:
        logger.error(f"Неизвестная ошибка при обработке callback: {e}", exc_info=True)
        try:
            await response_stream.finalize("Произошла непредвиденная ошибка.")
        except Exception:
            pass


# ==================== ОБРАБОТЧИК ДЛЯ ОСТАЛЬНЫХ СООБЩЕНИЙ ====================

@router.message()
async def handle_other_messages(message: Message, state: FSMContext):
    """Обрабатывает все остальные сообщения (не текст)"""
    if message.chat.type == "private":
        current_state = await state.get_state()
        if current_state == UserStates.with_manager:
            await message.answer("Пожалуйста, отправьте текстовое сообщение менеджеру.")
        else:
            await message.answer("Пожалуйста, отправьте текстовое сообщение.")
