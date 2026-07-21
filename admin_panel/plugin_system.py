"""Система регистрации плагинов"""

import logging
from typing import Dict, Any, Optional, Callable, Awaitable, List
from dataclasses import dataclass, field
from .models import PluginConfig

logger = logging.getLogger(__name__)

@dataclass
class PluginDefinition:
    """Определение плагина"""
    plugin_id: str
    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    config_schema: Dict[str, Any] = field(default_factory=dict)
    default_config: Dict[str, Any] = field(default_factory=dict)
    on_config_change: Optional[Callable[[Dict], Awaitable[None]]] = None
    on_enable: Optional[Callable[[], Awaitable[None]]] = None
    on_disable: Optional[Callable[[], Awaitable[None]]] = None

class PluginRegistry:
    """Реестр зарегистрированных плагинов"""
    
    _instance = None
    _plugins: Dict[str, PluginDefinition] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def register(self, definition: PluginDefinition) -> None:
        """
        Регистрация плагина
        
        Example:
            plugin_registry.register(
                PluginDefinition(
                    plugin_id="rag",
                    name="RAG System",
                    description="Retrieval Augmented Generation",
                    config_schema={
                        "chunk_size": {"type": "integer", "default": 512},
                        "top_k": {"type": "integer", "default": 5}
                    },
                    on_config_change=lambda config: print(f"RAG updated: {config}")
                )
            )
        """
        if definition.plugin_id in self._plugins:
            logger.warning(f"Plugin {definition.plugin_id} already registered, overwriting")
        
        self._plugins[definition.plugin_id] = definition
        logger.info(f"✅ Plugin registered: {definition.plugin_id} ({definition.name})")
    
    def get(self, plugin_id: str) -> Optional[PluginDefinition]:
        """Получить определение плагина"""
        return self._plugins.get(plugin_id)
    
    def list(self) -> List[PluginDefinition]:
        """Список всех плагинов"""
        return list(self._plugins.values())
    
    def get_config_schemas(self) -> Dict[str, Dict]:
        """Получить схемы конфигураций всех плагинов"""
        return {
            pid: def_.config_schema
            for pid, def_ in self._plugins.items()
        }
    
    async def update_config(self, plugin_id: str, config: Dict) -> bool:
        """Обновить конфигурацию плагина и вызвать колбэк"""
        definition = self._plugins.get(plugin_id)
        if not definition:
            logger.error(f"Plugin {plugin_id} not found")
            return False
        
        if definition.on_config_change:
            try:
                await definition.on_config_change(config)
                logger.info(f"Plugin {plugin_id} config updated via callback")
            except Exception as e:
                logger.error(f"Plugin {plugin_id} callback error: {e}")
                return False
        
        return True
    
    async def enable_plugin(self, plugin_id: str) -> bool:
        """Включить плагин"""
        definition = self._plugins.get(plugin_id)
        if not definition:
            return False
        
        if definition.on_enable:
            try:
                await definition.on_enable()
            except Exception as e:
                logger.error(f"Error enabling plugin {plugin_id}: {e}")
                return False
        
        logger.info(f"Plugin {plugin_id} enabled")
        return True
    
    async def disable_plugin(self, plugin_id: str) -> bool:
        """Отключить плагин"""
        definition = self._plugins.get(plugin_id)
        if not definition:
            return False
        
        if definition.on_disable:
            try:
                await definition.on_disable()
            except Exception as e:
                logger.error(f"Error disabling plugin {plugin_id}: {e}")
                return False
        
        logger.info(f"Plugin {plugin_id} disabled")
        return True

# Глобальный экземпляр
plugin_registry = PluginRegistry()