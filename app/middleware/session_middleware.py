# app/middleware/session_middleware.py
import time
import logging
import json
import uuid
from typing import Dict, Any, Callable, Awaitable, Optional
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, User

logger = logging.getLogger(__name__)

# Пытаемся импортировать Redis
try:
    from redis.asyncio import Redis
    REDIS_AVAILABLE = True
    logger.info("✅ Redis module available in SessionMiddleware")
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("⚠️ Redis module not available in SessionMiddleware, using in-memory")

class SessionMiddleware(BaseMiddleware):
    """Middleware для управления сессиями пользователей с Redis (опционально)"""
    
    # Ключи для Redis
    SESSION_KEY_PREFIX = "session:"
    USER_SESSION_KEY = "user_session:"
    SESSION_TTL = 3600 * 24 * 30  # 30 дней
    
    def __init__(self, redis: Optional['Redis'] = None):
        self.redis = redis
        self._in_memory_sessions: Dict[int, str] = {}  # Fallback при отсутствии Redis
        self._redis_available = REDIS_AVAILABLE and redis is not None
        
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Получаем пользователя
        user = self._extract_user(event)
        
        if user:
            # Получаем или создаем session_id
            session_id = await self._get_or_create_session(user.id)
            
            # Сохраняем в data для передачи хендлерам
            data['session_id'] = session_id
            data['session_middleware'] = self
            data['user_metadata'] = {
                "id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "language_code": user.language_code
            }
            
            # Обновляем время последнего обращения
            await self._update_last_seen(user.id)
        
        return await handler(event, data)
    
    def _extract_user(self, event: TelegramObject) -> Optional[User]:
        """Извлекает пользователя из события"""
        if isinstance(event, Message):
            return event.from_user
        elif hasattr(event, 'from_user'):
            return event.from_user
        elif hasattr(event, 'message') and hasattr(event.message, 'from_user'):
            return event.message.from_user
        return None
    
    async def _get_or_create_session(self, user_id: int) -> str:
        """Получает существующую сессию или создает новую"""
        if self._redis_available:
            return await self._get_or_create_session_redis(user_id)
        else:
            return self._get_or_create_session_memory(user_id)
    
    async def _get_or_create_session_redis(self, user_id: int) -> str:
        """Redis версия"""
        try:
            # Пытаемся получить существующую сессию
            session_key = f"{self.USER_SESSION_KEY}{user_id}"
            session_id = await self.redis.get(session_key)
            
            if session_id:
                session_id = session_id.decode('utf-8')
                # Продлеваем TTL сессии
                await self.redis.expire(session_key, self.SESSION_TTL)
                await self.redis.expire(
                    f"{self.SESSION_KEY_PREFIX}{session_id}", 
                    self.SESSION_TTL
                )
                return session_id
            
            return await self._create_session_redis(user_id)
            
        except Exception as e:
            logger.error(f"Redis error: {e}, falling back to in-memory")
            return self._get_or_create_session_memory(user_id)
    
    def _get_or_create_session_memory(self, user_id: int) -> str:
        """In-memory fallback"""
        session_id = self._in_memory_sessions.get(user_id)
        if not session_id:
            session_id = self._create_session_memory(user_id)
            # Ограничиваем размер in-memory хранилища
            if len(self._in_memory_sessions) > 10000:
                # Удаляем старые сессии (простая стратегия)
                keys = list(self._in_memory_sessions.keys())
                for key in keys[:1000]:
                    del self._in_memory_sessions[key]
        return session_id

    async def rotate_session(self, user_id: int) -> str:
        """Start a fresh agent context while retaining the old session records."""
        if self._redis_available:
            try:
                return await self._create_session_redis(user_id)
            except Exception as error:
                logger.error("Redis session rotation failed: %s", error)
        return self._create_session_memory(user_id)

    async def _create_session_redis(self, user_id: int) -> str:
        new_session_id = self._new_session_id(user_id)
        session_info = {
            "user_id": user_id,
            "created_at": int(time.time()),
            "session_id": new_session_id,
        }
        await self.redis.setex(
            f"{self.USER_SESSION_KEY}{user_id}",
            self.SESSION_TTL,
            new_session_id,
        )
        await self.redis.setex(
            f"{self.SESSION_KEY_PREFIX}{new_session_id}",
            self.SESSION_TTL,
            json.dumps(session_info),
        )
        logger.info("Created new session for user %s: %s", user_id, new_session_id)
        return new_session_id

    def _create_session_memory(self, user_id: int) -> str:
        session_id = self._new_session_id(user_id)
        self._in_memory_sessions[user_id] = session_id
        return session_id

    @staticmethod
    def _new_session_id(user_id: int) -> str:
        return f"user_{user_id}_{int(time.time())}_{uuid.uuid4().hex[:12]}"
    
    async def _update_last_seen(self, user_id: int):
        """Обновляет время последнего обращения"""
        if self._redis_available:
            try:
                last_seen_key = f"user_last_seen:{user_id}"
                await self.redis.setex(last_seen_key, 300, str(int(time.time())))
            except Exception as e:
                logger.debug(f"Could not update last_seen: {e}")
    
    async def get_session_info(self, session_id: str) -> Optional[Dict]:
        """Получает информацию о сессии"""
        if not self._redis_available:
            return None
        
        try:
            data = await self.redis.get(f"{self.SESSION_KEY_PREFIX}{session_id}")
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Error getting session info: {e}")
        return None
    
    async def get_user_session(self, user_id: int) -> Optional[str]:
        """Получает session_id для пользователя"""
        if self._redis_available:
            try:
                session_id = await self.redis.get(f"{self.USER_SESSION_KEY}{user_id}")
                return session_id.decode('utf-8') if session_id else None
            except Exception:
                return None
        return self._in_memory_sessions.get(user_id)
    
    async def cleanup_old_sessions(self, days_old: int = 30):
        """Очистка старых сессий (можно запускать периодически)"""
        if not self._redis_available:
            logger.info("Redis not available, skipping cleanup")
            return
        
        try:
            # Находим сессии старше указанного времени
            cutoff = int(time.time()) - (days_old * 24 * 3600)
            pattern = f"{self.SESSION_KEY_PREFIX}*"
            cursor = 0
            cleaned = 0
            
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                
                for key in keys:
                    data = await self.redis.get(key)
                    if data:
                        info = json.loads(data)
                        if info.get('created_at', 0) < cutoff:
                            await self.redis.delete(key)
                            # Удаляем также связь user->session
                            await self.redis.delete(f"{self.USER_SESSION_KEY}{info['user_id']}")
                            cleaned += 1
                
                if cursor == 0:
                    break
            
            logger.info(f"Cleaned up {cleaned} sessions older than {days_old} days")
            
        except Exception as e:
            logger.error(f"Error cleaning sessions: {e}")
