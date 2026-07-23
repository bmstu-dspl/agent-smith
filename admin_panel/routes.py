"""Дополнительные API endpoints для админки"""

import asyncio
import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any

from .storage import AdminStorage
from .plugin_system import plugin_registry
from .models import BotConfig, PluginConfig, McpServerCreate, McpServerCredentialsUpdate, McpServerToggle

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


def _get_mcp_store(request: Request):
    store = getattr(request.app.state, "mcp_store", None)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="MCP registry unavailable: Postgres or MCP_SECRETS_ENCRYPTION_KEY is not configured",
        )
    return store


@router.get("/mcp-servers")
async def list_mcp_servers(request: Request):
    """Список всех MCP-серверов"""
    store = _get_mcp_store(request)
    servers = await asyncio.to_thread(store.list_servers)
    return {
        "status": "success",
        "servers": [
            {
                "server_id": s.server_id,
                "name": s.name,
                "transport_type": s.transport_type,
                "url": s.url,
                "is_active": s.is_active,
                "last_connected_at": s.last_connected_at.isoformat() if s.last_connected_at else None,
                "error_message": s.error_message,
                "has_secrets": bool(s.headers or s.query_params),
            }
            for s in servers
        ],
    }


@router.post("/mcp-servers")
async def add_mcp_server(request: Request, data: McpServerCreate):
    """Добавить новый MCP-сервер"""
    store = _get_mcp_store(request)
    try:
        server_id = await asyncio.to_thread(
            store.add_server,
            name=data.name,
            url=data.url,
            transport_type=data.transport_type.value,
            headers=data.headers,
            query_params=data.query_params,
        )
    except Exception as e:
        logger.error(f"Error adding MCP server: {e}")
        return JSONResponse({"status": "error", "error": "Failed to add server"}, status_code=400)

    return {"status": "success", "message": "MCP server added", "server_id": server_id}


@router.post("/mcp-servers/{server_id}/toggle")
async def toggle_mcp_server(request: Request, server_id: str, data: McpServerToggle):
    """Включить/отключить MCP-сервер"""
    store = _get_mcp_store(request)
    server = await asyncio.to_thread(store.get_server, server_id)
    if not server:
        return JSONResponse({"status": "error", "error": "Server not found"}, status_code=404)

    await asyncio.to_thread(store.set_active, server_id, data.is_active)
    return {"status": "success", "message": f"Server {'enabled' if data.is_active else 'disabled'}"}


@router.post("/mcp-servers/{server_id}/credentials")
async def update_mcp_server_credentials(request: Request, server_id: str, data: McpServerCredentialsUpdate):
    """Обновить headers/query_params сервера (например, при ротации токена).
    Поле, оставленное пустым (None), не меняется."""
    store = _get_mcp_store(request)
    server = await asyncio.to_thread(store.get_server, server_id)
    if not server:
        return JSONResponse({"status": "error", "error": "Server not found"}, status_code=404)

    await asyncio.to_thread(
        store.update_credentials,
        server_id,
        headers=data.headers,
        query_params=data.query_params,
    )
    return {"status": "success", "message": "Credentials updated"}


@router.delete("/mcp-servers/{server_id}")
async def delete_mcp_server(request: Request, server_id: str):
    """Удалить MCP-сервер из реестра"""
    store = _get_mcp_store(request)
    server = await asyncio.to_thread(store.get_server, server_id)
    if not server:
        return JSONResponse({"status": "error", "error": "Server not found"}, status_code=404)

    await asyncio.to_thread(store.delete_server, server_id)
    return {"status": "success", "message": "Server deleted"}