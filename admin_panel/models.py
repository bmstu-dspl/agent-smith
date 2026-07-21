"""Pydantic модели для админки"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List
from enum import Enum

class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class BotConfig(BaseModel):
    """Конфигурация бота"""
    token: str = Field(..., description="Токен Telegram бота")
    webhook_host: str = Field(..., description="Публичный URL для вебхука")
    webhook_path: Optional[str] = Field(None, description="Путь вебхука (генерируется автоматически)")
    manager_group_id: Optional[int] = Field(None, description="ID группы менеджеров")
    ai_agent_url: str = Field(default="http://ai_agent:8000", description="URL AI агента")
    log_level: LogLevel = Field(default=LogLevel.INFO, description="Уровень логирования")
    port: int = Field(default=8080, description="Порт бота")
    
    # Функциональные флаги
    enable_rag: bool = Field(default=True, description="Включить RAG")
    enable_escalation: bool = Field(default=True, description="Включить эскалацию")
    enable_redis_fsm: bool = Field(default=True, description="Использовать Redis для FSM")
    
    @field_validator("manager_group_id")
    @classmethod
    def validate_group_id(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v >= 0:
            raise ValueError("Group ID must be negative for supergroups")
        return v
    
    @property
    def webhook_url(self) -> str:
        """Полный URL вебхука"""
        return f"{self.webhook_host}/webhook/{self.token}"
    
    class Config:
        json_schema_extra = {
            "example": {
                "token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
                "webhook_host": "https://your-domain.ngrok-free.dev",
                "manager_group_id": -1001234567890,
                "ai_agent_url": "http://ai_agent:8000",
                "log_level": "INFO",
                "port": 8080,
                "enable_rag": True,
                "enable_escalation": True,
                "enable_redis_fsm": True,
            }
        }

class PluginConfig(BaseModel):
    """Конфигурация плагина"""
    plugin_id: str = Field(..., description="Уникальный ID плагина")
    name: str = Field(..., description="Название плагина")
    description: str = Field(default="", description="Описание")
    enabled: bool = Field(default=True, description="Включен")
    config: Dict[str, Any] = Field(default_factory=dict, description="Настройки плагина")
    
    # Метаданные
    version: str = Field(default="1.0.0", description="Версия")
    author: str = Field(default="", description="Автор")
    created_at: Optional[str] = Field(None, description="Дата создания")
    updated_at: Optional[str] = Field(None, description="Дата обновления")

class PluginSchema(BaseModel):
    """Схема конфигурации плагина (для автоматической генерации формы)"""
    plugin_id: str
    name: str
    description: str
    fields: List[Dict[str, Any]] = Field(default_factory=list, description="Поля конфигурации")
    
    class Config:
        json_schema_extra = {
            "example": {
                "plugin_id": "rag",
                "name": "RAG System",
                "description": "Настройки поиска по документам",
                "fields": [
                    {"name": "chunk_size", "type": "integer", "label": "Размер чанка", "default": 512},
                    {"name": "top_k", "type": "integer", "label": "Количество результатов", "default": 5},
                    {"name": "embedding_model", "type": "string", "label": "Модель эмбеддингов", "default": "text-embedding-3-small"},
                ]
            }
        }