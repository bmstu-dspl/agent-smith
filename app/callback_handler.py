import logging
from typing import Dict, Any
from aiogram.types import CallbackQuery
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)

class CallbackHandler:
    """Универсальный обработчик callback запросов"""
    
    def __init__(self, bot):
        self.bot = bot
        self.CALLBACK_URL = "http://ai_agent:8000/agent/process"
    async def handle(self, callback: CallbackQuery) -> Dict[str, Any]:
        """
        Обрабатывает любой callback запрос
        """
        # 1. Убираем часики
        await callback.answer()
        
        # 2. Убираем клавиатуру
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception as e:
            logger.warning(f"Не удалось убрать клавиатуру: {e}")
        
        # 3. Парсим данные
        callback_data = callback.data
        user_id = callback.from_user.id
        
        # 4. Отправляем на сервер
        await self.send_to_server(callback_data, user_id)
        
        # 5. Отвечаем пользователю
        await callback.message.answer(
            f"Вы нажали: {callback_data}\n"
            "Запрос обрабатывается..."
        )
        
        return {
            "success": True,
            "callback_data": callback_data,
            "user_id": user_id
        }
    
    async def send_to_server(self, callback_data: str, user_id: int):
        """Отправка на сервер"""
        try:
            payload = {
                "session_id": f"temp_{user_id}",
                "user_message": callback_data,
                "message_type": "callback",
                "metadata": {"user_id": user_id},
                "timestamp": datetime.utcnow().isoformat(),
            }
            
            async with httpx.AsyncClient() as client:
                await client.post(self.CALLBACK_URL, json=payload)
                logger.info(f"Callback отправлен: {callback_data}")
                
        except Exception as e:
            logger.error(f"Ошибка: {e}")
