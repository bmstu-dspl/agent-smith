import logging
from aiogram import Router, types, F
from aiogram.types import Message
from aiogram.filters import Command

from app.models import IncomingMessage
from app.services.ai_agent import ai_agent
from app.middleware.session_middleware import SessionMiddleware

router = Router()

# Регистрируем middleware
router.message.middleware(SessionMiddleware())

logger = logging.getLogger(__name__)

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    await message.answer(
        "Привет!\n\n"
        "Просто отправь мне любое сообщение, и я передам его AI агенту.\n"
    )

@router.message(F.text)
async def handle_message(message: Message, session_id: str = None, user_metadata: dict = None):
    """Обработчик всех текстовых сообщений"""
    
    # Создаем объект IncomingMessage
    incoming_message = IncomingMessage(
        session_id=session_id or f"temp_{message.from_user.id}",
        user_message=message.text,
        metadata=user_metadata or {}
    )
    
    # Логируем получение сообщения
    logger.info(f"Получено сообщение от пользователя {message.from_user.id}: {message.text}")
    
    # Отправляем сообщение AI агенту
    try:
        # Обрабатываем сообщение агентом
        agent_response = await ai_agent.process_message(incoming_message)
        
        # Отвечаем пользователю
        await message.answer(
            f"Сообщение передано AI агенту.\n"
            f"Ответ агента: {agent_response.get('message', 'принял сообщение')}\n"
            f"ID сессии: {incoming_message.session_id}"
        )
        
        logger.info(f"Сообщение обработано агентом. Session ID: {incoming_message.session_id}")
        
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения агентом: {e}")
        await message.answer("Произошла ошибка. Попробуйте позже.")

@router.message()
async def handle_other_messages(message: Message):
    """Обработчик всех остальных сообщений"""
    await message.answer("Пожалуйста, отправьте текстовое сообщение.")