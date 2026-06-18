from __future__ import annotations

from fastapi import Depends
from fastapi.routing import APIRouter

from app.agent.mcp.config import McpServerConfig
from app.agent.mcp.provider import mcp_provider
from app.agent.mcp.registry import mcp_tool_registry
from app.agent.skill_registry import skill_registry
from app.core.success_response import success_response
from app.utils.auth_utils import get_current_user_id, require_admin_user

mcp_router = APIRouter(prefix="/api/mcp", tags=["mcp"])


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


@mcp_router.post("/servers/refresh")
async def refresh_mcp_servers(_: str = Depends(require_admin_user)):
    tools = await mcp_tool_registry.refresh()
    skill_registry.reload()
    return success_response(message="mcp tools refreshed", data={
        "servers": [_server_status(server) for server in mcp_provider.servers()],
        "tools": mcp_tool_registry.public_catalog(),
        "count": len(tools),
    })
