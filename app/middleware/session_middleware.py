from typing import Dict, Any, Callable, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from aiogram.types import User

class SessionMiddleware(BaseMiddleware):
    """Middleware для управления сессиями пользователей"""
    
    def __init__(self):
        self.sessions: Dict[int, str] = {}  # user_id -> session_id
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Получаем пользователя
        user: User = None
        
        if isinstance(event, Message):
            user = event.from_user
        elif hasattr(event, 'from_user'):
            user = event.from_user
        elif hasattr(event, 'message') and hasattr(event.message, 'from_user'):
            user = event.message.from_user
        
        if user:
            # Генерируем или получаем session_id
            session_id = self.sessions.get(user.id)
            if not session_id:
                # Здесь можно использовать более сложную генерацию session_id
                session_id = f"user_{user.id}_{int(time.time())}"
                self.sessions[user.id] = session_id
            
            data['session_id'] = session_id
            data['user_metadata'] = {
                "id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "language_code": user.language_code
            }
        
        return await handler(event, data)

import time