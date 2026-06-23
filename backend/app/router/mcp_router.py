from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.routing import APIRouter
from pydantic import BaseModel, Field

from app.agent.mcp.config import (
    McpServerConfig,
    delete_mcp_server_config,
    delete_mcp_tool_config,
    update_mcp_server_config,
    update_mcp_tool_override,
)
from app.agent.mcp.provider import mcp_provider
from app.agent.mcp.registry import mcp_tool_registry
from app.agent.skill_registry import skill_registry
from app.core.success_response import success_response
from app.utils.auth_utils import get_current_user_id, is_admin_user, require_admin_user, security
from fastapi.security import HTTPAuthorizationCredentials

mcp_router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class McpToolUpdatePayload(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, min_length=1, max_length=1000)
    enabled: bool | None = None
    risk_level: str | None = Field(default=None, pattern="^(low|medium|high)$")
    requires_confirmation: bool | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=1800)
    max_output_chars: int | None = Field(default=None, ge=256, le=100000)


class McpServerUpdatePayload(BaseModel):
    enabled: bool | None = None
    label: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    url: str | None = Field(default=None, min_length=1, max_length=2000)


def _server_status(server: McpServerConfig) -> dict:
    last_error = mcp_provider.last_error(server.id)
    if not server.enabled:
        status = "disabled"
    elif last_error:
        status = "error"
    else:
        status = "enabled"
    return {
        "id": server.id,
        "label": server.label,
        "description": server.description,
        "enabled": server.enabled,
        "transport": server.transport,
        "url": server.url,
        "command": server.command,
        "allow_tools": list(server.allow_tools),
        "deny_tools": list(server.deny_tools),
        "default_risk_level": server.default_risk_level,
        "default_requires_confirmation": server.default_requires_confirmation,
        "timeout_seconds": server.timeout_seconds,
        "max_output_chars": server.max_output_chars,
        "status": status,
        "last_error": last_error,
    }


@mcp_router.get("/servers")
async def get_mcp_servers(_: str = Depends(get_current_user_id)):
    return success_response(data={
        "servers": [_server_status(server) for server in mcp_provider.servers()],
    })


@mcp_router.get("/tools")
async def get_mcp_tools(_: str = Depends(get_current_user_id)):
    return success_response(data={
        "tools": mcp_tool_registry.public_catalog(),
    })


@mcp_router.get("/permissions")
async def get_mcp_permissions(
    user_id: str = Depends(get_current_user_id),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    return success_response(data={
        "can_manage_mcp": await is_admin_user(user_id, credentials),
    })


@mcp_router.post("/servers/refresh")
async def refresh_mcp_servers(_: str = Depends(require_admin_user)):
    tools = await mcp_tool_registry.refresh()
    skill_registry.reload()
    return success_response(message="mcp tools refreshed", data={
        "servers": [_server_status(server) for server in mcp_provider.servers()],
        "tools": mcp_tool_registry.public_catalog(),
        "count": len(tools),
    })


@mcp_router.patch("/servers/{server_id}")
async def update_mcp_server(server_id: str, payload: McpServerUpdatePayload, _: str = Depends(require_admin_user)):
    if not any(server.id == server_id for server in mcp_provider.servers()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="mcp server not found")
    try:
        update_mcp_server_config(server_id, payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    tools = await mcp_tool_registry.refresh()
    skill_registry.reload()
    server = next((item for item in mcp_provider.servers() if item.id == server_id), None)
    return success_response(message="mcp server updated", data={
        "server": _server_status(server) if server else None,
        "count": len(tools),
    })


@mcp_router.delete("/servers/{server_id}")
async def delete_mcp_server(server_id: str, _: str = Depends(require_admin_user)):
    try:
        delete_mcp_server_config(server_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    tools = await mcp_tool_registry.refresh()
    skill_registry.reload()
    return success_response(message="mcp server removed", data={
        "servers": [_server_status(server) for server in mcp_provider.servers()],
        "tools": mcp_tool_registry.public_catalog(),
        "count": len(tools),
    })


@mcp_router.patch("/tools/{tool_id}")
async def update_mcp_tool(tool_id: str, payload: McpToolUpdatePayload, _: str = Depends(require_admin_user)):
    spec = mcp_tool_registry.get(tool_id)
    if spec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="mcp tool not found; refresh MCP tools first")

    patch = payload.model_dump(exclude_none=True)
    try:
        update_mcp_tool_override(spec.server_id, spec.name, patch)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    tools = await mcp_tool_registry.refresh()
    skill_registry.reload()
    updated = next((item for item in mcp_tool_registry.public_catalog() if item["id"] == tool_id), None)
    return success_response(message="mcp tool updated", data={
        "tool": updated,
        "count": len(tools),
    })


@mcp_router.delete("/tools/{tool_id}")
async def delete_mcp_tool(tool_id: str, _: str = Depends(require_admin_user)):
    spec = mcp_tool_registry.get(tool_id)
    if spec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="mcp tool not found; refresh MCP tools first")
    try:
        delete_mcp_tool_config(spec.server_id, spec.name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    tools = await mcp_tool_registry.refresh()
    skill_registry.reload()
    return success_response(message="mcp tool removed from project", data={
        "tools": mcp_tool_registry.public_catalog(),
        "count": len(tools),
    })
