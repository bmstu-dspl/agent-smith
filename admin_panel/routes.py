"""Дополнительные API endpoints для админки"""

import logging
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Dict, Any

from .storage import AdminStorage
from .plugin_system import plugin_registry
from .models import BotConfig, PluginConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/api", tags=["admin-api"])

class TogglePluginRequest(BaseModel):
    enabled: bool

class PluginConfigRequest(BaseModel):
    config: Dict[str, Any]

@router.post("/bot-config")
async def save_bot_config(request: Request, config: BotConfig):
    """API для сохранения конфигурации бота"""
    storage: AdminStorage = request.app.state.admin_storage
    success = await storage.save_bot_config(config)
    if success:
        return {"status": "success", "message": "Configuration saved"}
    return {"status": "error", "error": "Failed to save"}

@router.post("/plugins/{plugin_id}/toggle")
async def toggle_plugin(request: Request, plugin_id: str, data: TogglePluginRequest):
    """Включение/отключение плагина"""
    storage: AdminStorage = request.app.state.admin_storage
    
    # Получаем текущую конфигурацию
    saved = await storage.get_plugin_config(plugin_id)
    definition = plugin_registry.get(plugin_id)
    
    if not definition:
        return {"status": "error", "error": f"Plugin {plugin_id} not registered"}
    
    # Создаем или обновляем конфигурацию
    if saved:
        saved.enabled = data.enabled
        config_data = saved.model_dump()
    else:
        config_data = {
            "plugin_id": plugin_id,
            "name": definition.name,
            "description": definition.description,
            "enabled": data.enabled,
            "config": definition.default_config,
            "version": definition.version,
        }
    
    await storage.save_plugin_config(plugin_id, PluginConfig(**config_data))
    
    # Вызываем колбэки
    if data.enabled:
        await plugin_registry.enable_plugin(plugin_id)
    else:
        await plugin_registry.disable_plugin(plugin_id)
    
    return {"status": "success", "message": f"Plugin {plugin_id} {'enabled' if data.enabled else 'disabled'}"}

@router.post("/plugins/{plugin_id}/config")
async def save_plugin_config(request: Request, plugin_id: str, data: Dict[str, Any]):
    """Сохранить конфигурацию плагина"""
    storage: AdminStorage = request.app.state.admin_storage
    definition = plugin_registry.get(plugin_id)
    
    if not definition:
        return {"status": "error", "error": f"Plugin {plugin_id} not registered"}
    
    # Получаем текущую конфигурацию
    saved = await storage.get_plugin_config(plugin_id)
    
    if saved:
        saved.config = data
        config_data = saved.model_dump()
    else:
        config_data = {
            "plugin_id": plugin_id,
            "name": definition.name,
            "description": definition.description,
            "enabled": True,
            "config": data,
            "version": definition.version,
        }
    
    await storage.save_plugin_config(plugin_id, PluginConfig(**config_data))
    await plugin_registry.update_config(plugin_id, data)
    
    return {"status": "success", "message": "Configuration saved"}