from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field


class McpServerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1, max_length=4000)
    transport_type: Literal["sse", "http", "stdio"] = "sse"
    headers: dict[str, Any] = Field(default_factory=dict)
    query_params: dict[str, Any] = Field(default_factory=dict)


class McpServerToggle(BaseModel):
    is_active: bool


class McpCredentialsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headers: dict[str, Any] | None = None
    query_params: dict[str, Any] | None = None


def create_mcp_router(require_identity, require_mutation_access) -> APIRouter:
    router = APIRouter(prefix="/admin/api/mcp", tags=["admin-mcp"])

    @router.get("/servers")
    async def list_servers(request: Request) -> dict:
        require_identity(request)
        servers = await asyncio.to_thread(_store(request).list_servers)
        return {
            "servers": [
                {
                    "server_id": server.server_id,
                    "name": server.name,
                    "url": server.url,
                    "transport_type": server.transport_type,
                    "is_active": server.is_active,
                    "last_connected_at": (
                        server.last_connected_at.isoformat()
                        if server.last_connected_at
                        else None
                    ),
                    "error_message": server.error_message,
                    "has_secrets": bool(server.headers or server.query_params),
                }
                for server in servers
            ]
        }

    @router.post("/servers", status_code=status.HTTP_201_CREATED)
    async def create_server(request: Request, payload: McpServerCreate) -> dict:
        require_mutation_access(request, required_role="editor")
        server_id = await asyncio.to_thread(
            _store(request).add_server,
            name=payload.name,
            url=payload.url,
            transport_type=payload.transport_type,
            headers=payload.headers,
            query_params=payload.query_params,
        )
        return {"server_id": server_id}

    @router.post("/servers/{server_id}/toggle")
    async def toggle_server(
        request: Request,
        server_id: str,
        payload: McpServerToggle,
    ) -> dict:
        require_mutation_access(request, required_role="editor")
        await _require_server(request, server_id)
        await asyncio.to_thread(
            _store(request).set_active,
            server_id,
            payload.is_active,
        )
        return {"is_active": payload.is_active}

    @router.put("/servers/{server_id}/credentials")
    async def update_credentials(
        request: Request,
        server_id: str,
        payload: McpCredentialsUpdate,
    ) -> dict:
        require_mutation_access(request, required_role="admin")
        await _require_server(request, server_id)
        await asyncio.to_thread(
            _store(request).update_credentials,
            server_id,
            headers=payload.headers,
            query_params=payload.query_params,
        )
        return {"updated": True}

    @router.delete(
        "/servers/{server_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_server(request: Request, server_id: str) -> Response:
        require_mutation_access(request, required_role="editor")
        await _require_server(request, server_id)
        await asyncio.to_thread(_store(request).delete_server, server_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


def _store(request: Request):
    store = getattr(request.app.state, "mcp_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="MCP registry unavailable")
    return store


async def _require_server(request: Request, server_id: str):
    server = await asyncio.to_thread(_store(request).get_server, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    return server
