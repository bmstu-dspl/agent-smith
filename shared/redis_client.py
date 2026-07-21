"""Единое управление Redis для всех сервисов"""

import logging
import os
from typing import Optional, Union, Any

logger = logging.getLogger(__name__)

# Пытаемся импортировать Redis
try:
    from redis.asyncio import Redis
    REDIS_AVAILABLE = True
    logger.info("✅ Redis module available")
except ImportError as e:
    REDIS_AVAILABLE = False
    logger.warning(f"⚠️ Redis not available: {e}")
    
    # Заглушка для Redis
    class Redis:
        def __init__(self, *args, **kwargs):
            pass
        
        async def ping(self):
            return False
        
        async def get(self, key):
            return None
        
        async def set(self, key, value, *args, **kwargs):
            pass
        
        async def setex(self, key, time, value):
            pass
        
        async def delete(self, *keys):
            pass
        
        async def expire(self, key, time):
            pass
        
        async def close(self):
            pass
        
        def from_url(self, url, **kwargs):
            return self

class RedisClient:
    """Синглтон для Redis подключения"""
    
    _instance: Optional['RedisClient'] = None
    _redis: Optional[Redis] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def initialize(self, url: str, max_connections: int = 20):
        """Инициализация Redis"""
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available, using in-memory fallback")
            self._redis = Redis()
            return self._redis
        
        if self._redis is None or not await self._is_connected():
            try:
                self._redis = Redis.from_url(
                    url,
                    decode_responses=False,
                    max_connections=max_connections
                )
                await self._redis.ping()
                logger.info(f"✅ Redis connected: {url}")
            except Exception as e:
                logger.error(f"❌ Redis connection failed: {e}")
                # Создаем заглушку
                self._redis = Redis()
        return self._redis
    
    async def _is_connected(self) -> bool:
        """Проверить соединение с Redis"""
        if not REDIS_AVAILABLE or self._redis is None:
            return False
        try:
            await self._redis.ping()
            return True
        except Exception:
            return False
    
    async def get_client(self) -> Optional[Redis]:
        """Получить клиент Redis"""
        if self._redis is None and REDIS_AVAILABLE:
            url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            await self.initialize(url)
        return self._redis
    
    async def close(self):
        """Закрыть соединение"""
        if self._redis and REDIS_AVAILABLE:
            try:
                if hasattr(self._redis, 'close'):
                    await self._redis.close()
                self._redis = None
                logger.info("Redis connection closed")
            except Exception as e:
                logger.error(f"Error closing Redis: {e}")

# Глобальный экземпляр
redis_client = RedisClient()

async def get_redis_client() -> Optional[Redis]:
    """Получить клиент Redis (инициализирует при первом вызове)"""
    url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    return await redis_client.initialize(url)