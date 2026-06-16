from typing import Any

import yaml
from fastapi import HTTPException, status
from fastapi.routing import APIRouter
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.agent import agent_tools
from app.agent.skill_registry import TOOLS_DIR, skill_registry
from app.core.success_response import success_response

tool_router = APIRouter(prefix="/tools", tags=["tools"])

TOOL_CONFIG_PATH = TOOLS_DIR / "builtin.yaml"


class ToolPayload(BaseModel):
    id: str = Field(min_length=2, max_length=64)
    label: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=500)
    category: str = "general"
    symbol: str = Field(min_length=1, max_length=120)
    order: int = 100


def _read_tool_config() -> list[dict[str, Any]]:
    data = yaml.safe_load(TOOL_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    tools = data.get("tools", [])
    if not isinstance(tools, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid tools config")
    return tools


def _write_tool_config(tools: list[dict[str, Any]]) -> None:
    TOOL_CONFIG_PATH.write_text(
        yaml.safe_dump({"tools": tools}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    skill_registry.reload()


def _available_symbols() -> list[str]:
    symbols: list[str] = []
    for name in dir(agent_tools):
        value = getattr(agent_tools, name)
        if isinstance(value, BaseTool):
            symbols.append(name)
    return sorted(symbols)


def _validate_symbol(symbol: str) -> None:
    if symbol not in _available_symbols():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"unknown tool symbol: {symbol}")


@tool_router.get("/catalog")
async def get_tools_catalog():
    return success_response(data={
        "tools": _read_tool_config(),
        "symbols": _available_symbols(),
    })


@tool_router.post("")
async def create_tool(payload: ToolPayload):
    _validate_symbol(payload.symbol)
    tools = _read_tool_config()
    if any(item.get("id") == payload.id for item in tools):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="tool already exists")
    tools.append(payload.model_dump())
    _write_tool_config(tools)
    return success_response(message="tool created", data=payload.model_dump())


@tool_router.put("/{tool_id}")
async def update_tool(tool_id: str, payload: ToolPayload):
    _validate_symbol(payload.symbol)
    if payload.id != tool_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="renaming tool id is not supported")
    tools = _read_tool_config()
    for index, item in enumerate(tools):
        if item.get("id") == tool_id:
            tools[index] = payload.model_dump()
            _write_tool_config(tools)
            return success_response(message="tool updated", data=payload.model_dump())
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tool not found")


@tool_router.delete("/{tool_id}")
async def delete_tool(tool_id: str):
    tools = _read_tool_config()
    next_tools = [item for item in tools if item.get("id") != tool_id]
    if len(next_tools) == len(tools):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tool not found")
    _write_tool_config(next_tools)
    return success_response(message="tool deleted")
