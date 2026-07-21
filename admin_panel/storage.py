"""Хранилище для админки (обертка над shared.ConfigStorage)"""

import logging
from typing import Optional, Dict, Any, List
from shared.config_storage import ConfigStorage
from .models import BotConfig, PluginConfig

logger = logging.getLogger(__name__)

class AdminStorage:
    """Адаптер для работы с конфигурациями из админки"""
    
    def __init__(self, storage: ConfigStorage):
        self._storage = storage
    
    async def get_bot_config(self) -> BotConfig:
        """Получить конфигурацию бота"""
        data = await self._storage.get_bot_config()
        # Если данных нет - возвращаем значения по умолчанию
        if not data:
            return BotConfig(
                token="",
                webhook_host="",
                ai_agent_url="http://ai_agent:8000",
            )
        return BotConfig(**data)
    
    async def save_bot_config(self, config: BotConfig) -> bool:
        """Сохранить конфигурацию бота"""
        return await self._storage.save_bot_config(config.model_dump())
    
    async def get_plugin_config(self, plugin_id: str) -> Optional[PluginConfig]:
        """Получить конфигурацию плагина"""
        data = await self._storage.get_plugin_config(plugin_id)
        if data:
            return PluginConfig(**data)
        return None
    
    async def save_plugin_config(self, config: PluginConfig) -> bool:
        """Сохранить конфигурацию плагина"""
        return await self._storage.save_plugin_config(
            config.plugin_id,
            config.model_dump()
        )
    
    async def list_plugins(self) -> List[PluginConfig]:
        """Получить все плагины"""
        plugins = []
        for data in await self._storage.list_plugins():
            try:
                plugins.append(PluginConfig(**data))
            except Exception as e:
                logger.warning(f"Invalid plugin data: {e}")
        return plugins
    
    async def delete_plugin(self, plugin_id: str) -> bool:
        """Удалить плагин"""
        return await self._storage.delete_plugin(plugin_id)