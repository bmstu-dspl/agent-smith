"""Хранилище конфигураций (используется и ботом, и админкой)"""

import json
import logging
from typing import Optional, Dict, Any, List
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

class ConfigStorage:
    """Централизованное хранилище конфигураций в Redis"""
    
    BOT_CONFIG_KEY = "bot:config"
    PLUGINS_PREFIX = "plugin:"
    
    def __init__(self, redis: Redis):
        self.redis = redis
    
    async def get_bot_config(self) -> Dict[str, Any]:
        """Получить конфигурацию бота"""
        try:
            data = await self.redis.get(self.BOT_CONFIG_KEY)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Error loading bot config: {e}")
        return {}
    
    async def save_bot_config(self, config: Dict[str, Any]) -> bool:
        """Сохранить конфигурацию бота"""
        try:
            await self.redis.set(
                self.BOT_CONFIG_KEY,
                json.dumps(config),
                ex=86400 * 30  # 30 дней
            )
            logger.info("Bot config saved")
            return True
        except Exception as e:
            logger.error(f"Error saving bot config: {e}")
            return False
    
    async def get_plugin_config(self, plugin_id: str) -> Optional[Dict[str, Any]]:
        """Получить конфигурацию плагина"""
        try:
            data = await self.redis.get(f"{self.PLUGINS_PREFIX}{plugin_id}")
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Error loading plugin config for {plugin_id}: {e}")
        return None
    
    async def save_plugin_config(self, plugin_id: str, config: Dict[str, Any]) -> bool:
        """Сохранить конфигурацию плагина"""
        try:
            await self.redis.set(
                f"{self.PLUGINS_PREFIX}{plugin_id}",
                json.dumps(config),
                ex=86400 * 30
            )
            logger.info(f"Plugin config saved: {plugin_id}")
            return True
        except Exception as e:
            logger.error(f"Error saving plugin config for {plugin_id}: {e}")
            return False
    
    async def list_plugins(self) -> List[Dict[str, Any]]:
        """Получить все плагины"""
        plugins = []
        try:
            pattern = f"{self.PLUGINS_PREFIX}*"
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                for key in keys:
                    data = await self.redis.get(key)
                    if data:
                        try:
                            plugins.append(json.loads(data))
                        except Exception as e:
                            logger.warning(f"Invalid plugin config for {key}: {e}")
                if cursor == 0:
                    break
        except Exception as e:
            logger.error(f"Error listing plugins: {e}")
        return plugins
    
    async def delete_plugin(self, plugin_id: str) -> bool:
        """Удалить плагин"""
        try:
            await self.redis.delete(f"{self.PLUGINS_PREFIX}{plugin_id}")
            logger.info(f"Plugin deleted: {plugin_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting plugin {plugin_id}: {e}")
            return False