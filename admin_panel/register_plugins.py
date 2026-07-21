"""Регистрация плагинов для админки"""

import logging
from admin_panel.plugin_system import plugin_registry, PluginDefinition

logger = logging.getLogger(__name__)

def register_all_plugins():
    """Регистрация всех плагинов системы"""
    
    # RAG плагин
    plugin_registry.register(
        PluginDefinition(
            plugin_id="rag",
            name="RAG System",
            description="Retrieval Augmented Generation - поиск по документам",
            version="1.0.0",
            config_schema={
                "chunk_size": {
                    "type": "integer",
                    "label": "Chunk Size",
                    "default": 512,
                    "description": "Размер чанка для индексации"
                },
                "top_k": {
                    "type": "integer",
                    "label": "Top K",
                    "default": 5,
                    "description": "Количество возвращаемых результатов"
                },
                "embedding_model": {
                    "type": "string",
                    "label": "Embedding Model",
                    "default": "text-embedding-3-small",
                    "description": "Модель для генерации эмбеддингов"
                }
            },
            default_config={
                "chunk_size": 512,
                "top_k": 5,
                "embedding_model": "text-embedding-3-small"
            },
            on_config_change=lambda config: logger.info(f"RAG config updated: {config}")
        )
    )
    
    # AI Agent плагин
    plugin_registry.register(
        PluginDefinition(
            plugin_id="ai_agent",
            name="AI Agent",
            description="Настройки LLM агента",
            version="1.0.0",
            config_schema={
                "model": {
                    "type": "string",
                    "label": "Model",
                    "default": "gemini-2.5-flash",
                    "description": "Модель LLM"
                },
                "temperature": {
                    "type": "number",
                    "label": "Temperature",
                    "default": 0.2,
                    "description": "Температура генерации"
                },
                "max_tokens": {
                    "type": "integer",
                    "label": "Max Tokens",
                    "default": 4096,
                    "description": "Максимальное количество токенов"
                }
            },
            default_config={
                "model": "gemini-2.5-flash",
                "temperature": 0.2,
                "max_tokens": 4096
            },
            on_config_change=lambda config: logger.info(f"AI Agent config updated: {config}")
        )
    )
    
    logger.info(f"✅ Registered {len(plugin_registry.list())} plugins")