"""Регистрация плагинов для админки"""

import logging
from admin_panel.plugin_system import plugin_registry, PluginDefinition
from admin_panel.default_prompts import AGENT_SYSTEM_PROMPT_DEFAULT as AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

def register_all_plugins():
    """Регистрация всех плагинов системы"""
    
    # RAG плагин
    # Поля соответствуют возможностям модуля RAG, описанным в RAG/README.md:
    # chunking (max_chunk_chars/chunk_overlap_chars), retrieval (retrieval_mode/limit/
    # max_context_chars) и Vertex AI embedding provider (модель, регион, размерность,
    # timeout, retries).
    plugin_registry.register(
        PluginDefinition(
            plugin_id="rag",
            name="RAG System",
            description="Retrieval Augmented Generation - поиск по опубликованной памяти агента",
            version="1.0.0",
            config_schema={
                "max_chunk_chars": {
                    "type": "integer",
                    "label": "Max Chunk Chars",
                    "default": 1200,
                    "description": "Максимальный размер чанка в символах при chunking текста"
                },
                "chunk_overlap_chars": {
                    "type": "integer",
                    "label": "Chunk Overlap Chars",
                    "default": 150,
                    "description": "Overlap между соседними чанками и при разбиении больших фрагментов"
                },
                "retrieval_mode": {
                    "type": "select",
                    "label": "Retrieval Mode",
                    "options": ["semantic", "lexical", "hybrid"],
                    "default": "hybrid",
                    "description": "semantic - cosine similarity, lexical - текстовый поиск, hybrid - RRF по обоим"
                },
                "limit": {
                    "type": "integer",
                    "label": "Search Limit (Top K)",
                    "default": 8,
                    "description": "Количество результатов, возвращаемых поиском по памяти"
                },
                "max_context_chars": {
                    "type": "integer",
                    "label": "Max Context Chars",
                    "default": 12000,
                    "description": "Ограничение размера context_text, собираемого для LLM-агента"
                },
                "embedding_model": {
                    "type": "string",
                    "label": "Embedding Model",
                    "default": "gemini-embedding-001",
                    "description": "Vertex AI модель эмбеддингов (GOOGLE_EMBEDDING_MODEL)"
                },
                "embedding_location": {
                    "type": "string",
                    "label": "Embedding Location",
                    "default": "us-central1",
                    "description": "Регион Vertex AI (GOOGLE_EMBEDDING_LOCATION)"
                },
                "embedding_dimensions": {
                    "type": "integer",
                    "label": "Embedding Dimensions",
                    "default": 1536,
                    "description": "Размерность вектора; зафиксирована схемой БД pgvector, менять только вместе с новой миграцией"
                },
                "embedding_timeout": {
                    "type": "integer",
                    "label": "Embedding Timeout (sec)",
                    "default": 30,
                    "description": "Таймаут запроса к Vertex AI embedding API (GOOGLE_EMBEDDING_TIMEOUT)"
                },
                "embedding_max_retries": {
                    "type": "integer",
                    "label": "Embedding Max Retries",
                    "default": 3,
                    "description": "Число повторов с exponential backoff при transport-ошибках и 429/5xx (GOOGLE_EMBEDDING_MAX_RETRIES)"
                }
            },
            default_config={
                "max_chunk_chars": 1200,
                "chunk_overlap_chars": 150,
                "retrieval_mode": "hybrid",
                "limit": 8,
                "max_context_chars": 12000,
                "embedding_model": "gemini-embedding-001",
                "embedding_location": "us-central1",
                "embedding_dimensions": 1536,
                "embedding_timeout": 30,
                "embedding_max_retries": 3
            },
            on_config_change=lambda config: logger.info(f"RAG config updated: {config}")
        )
    )
    
    # AI Agent плагин
    # Единственная настройка - системный промпт агента (используется как значение
    # по умолчанию AGENT_SYSTEM_PROMPT из ai_core/graph/prompts.py). Остальные
    # прежние настройки (model/temperature/max_tokens) убраны по требованию.
    plugin_registry.register(
        PluginDefinition(
            plugin_id="ai_agent",
            name="AI Agent",
            description="Настройки LLM агента",
            version="1.0.0",
            config_schema={
                "system_prompt": {
                    "type": "text",
                    "label": "System Prompt",
                    "default": AGENT_SYSTEM_PROMPT,
                    "description": "Системный промпт агента гостиницы (ai_core/graph/prompts.py: AGENT_SYSTEM_PROMPT)"
                }
            },
            default_config={
                "system_prompt": AGENT_SYSTEM_PROMPT
            },
            on_config_change=lambda config: logger.info("AI Agent config updated")
        )
    )
    
    logger.info(f"✅ Registered {len(plugin_registry.list())} plugins")