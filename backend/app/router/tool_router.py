import re
import shutil
from typing import Any

import yaml
from fastapi import Depends, HTTPException, status
from fastapi.routing import APIRouter
from pydantic import BaseModel, Field

from app.agent.skill_registry import TOOLS_DIR, skill_registry
from app.core.success_response import success_response
from app.utils.auth_utils import get_current_user_id, require_admin_user

tool_router = APIRouter(prefix="/tools", tags=["tools"])

SAFE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


class ToolPayload(BaseModel):
    id: str = Field(min_length=2, max_length=64)
    label: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=500)
    category: str = "general"
    order: int = 100
    default: bool = True
    visibility: str = "public"
    risk_level: str = Field(default="low", pattern="^(low|medium|high)$")
    requires_confirmation: bool = False
    timeout_seconds: int = Field(default=30, ge=1, le=600)
    max_output_chars: int = Field(default=4000, ge=256, le=100000)
    instructions: str = Field(default="", max_length=20000)


def _default_tool_instructions(payload: ToolPayload) -> str:
    label = payload.label.strip() or payload.id.strip()
    description = payload.description.strip() or "描述这个工具可以完成的动作。"
    return (
        f"# {label}\n\n"
        f"{description}\n\n"
        "## 使用规则\n\n"
        "- 说明这个工具适合处理什么任务。\n"
        "- 说明需要哪些输入参数。\n"
        "- 说明工具返回结果后应该如何组织回答。\n"
    )


def _validate_tool_id(tool_id: str) -> str:
    value = tool_id.strip()
    if not SAFE_ID_PATTERN.match(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tool id must start with a lowercase letter and contain only lowercase letters, numbers, and underscores",
        )
    return value


def _tool_dir(tool_id: str) -> Any:
    return TOOLS_DIR / _validate_tool_id(tool_id)


def _read_tool_detail(tool_id: str) -> dict:
    directory = _tool_dir(tool_id)
    config_path = directory / "tool.yaml"
    instructions_path = directory / "TOOL.md"
    if not config_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tool not found")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid tool config")
    return {
        "id": data.get("id", tool_id),
        "label": data.get("label", ""),
        "description": data.get("description", ""),
        "category": data.get("category", "general"),
        "order": int(data.get("order", 100)),
        "entrypoint": data.get("entrypoint", "tool:get_tool"),
        "default": bool(data.get("default", True)),
        "visibility": data.get("visibility", "public"),
        "risk_level": data.get("risk_level", "low"),
        "requires_confirmation": bool(data.get("requires_confirmation", False)),
        "timeout_seconds": int(data.get("timeout_seconds", 30)),
        "max_output_chars": int(data.get("max_output_chars", 4000)),
        "instructions": instructions_path.read_text(encoding="utf-8") if instructions_path.exists() else "",
    }


def _write_placeholder_tool(directory: Any, payload: ToolPayload, tool_id: str) -> None:
    tool_name = f"{tool_id}_tool"
    tool_description = repr(payload.description)
    tool_label = repr(payload.label)
    source = f'''from langchain_core.tools import tool


@tool("{tool_name}", description={tool_description})
async def generated_tool(query: str = "") -> str:
    """Generated placeholder tool."""
    return "工具 " + {tool_label} + " 已注册，但还没有配置具体执行逻辑。"


def get_tool():
    return generated_tool
'''
    (directory / "tool.py").write_text(source, encoding="utf-8")


def _write_tool(payload: ToolPayload, existing_id: str | None = None) -> dict:
    tool_id = _validate_tool_id(payload.id)
    if existing_id and existing_id != tool_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="renaming tool id is not supported")

    directory = _tool_dir(tool_id)
    directory.mkdir(parents=True, exist_ok=True)
    init_path = directory / "__init__.py"
    if not init_path.exists():
        init_path.write_text('"""Agent tool module."""\n', encoding="utf-8")

    config = {
        "id": tool_id,
        "label": payload.label,
        "description": payload.description,
        "category": payload.category,
        "entrypoint": "tool:get_tool",
        "default": payload.default,
        "visibility": payload.visibility,
        "risk_level": payload.risk_level,
        "requires_confirmation": payload.requires_confirmation,
        "timeout_seconds": payload.timeout_seconds,
        "max_output_chars": payload.max_output_chars,
        "order": payload.order,
    }
    (directory / "tool.yaml").write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    instructions = payload.instructions.strip() or _default_tool_instructions(payload)
    (directory / "TOOL.md").write_text(instructions.rstrip() + "\n", encoding="utf-8")
    if not (directory / "tool.py").exists():
        _write_placeholder_tool(directory, payload, tool_id)

    skill_registry.reload()
    return _read_tool_detail(tool_id)


@tool_router.get("/catalog")
async def get_tools_catalog(_: str = Depends(get_current_user_id)):
    return success_response(data={
        "tools": [_read_tool_detail(tool.id) for tool in skill_registry.tool_registry.all()],
    })


@tool_router.post("")
async def create_tool(payload: ToolPayload, _: str = Depends(require_admin_user)):
    directory = _tool_dir(payload.id)
    if directory.exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="tool already exists")
    return success_response(message="tool created", data=_write_tool(payload))


@tool_router.put("/{tool_id}")
async def update_tool(tool_id: str, payload: ToolPayload, _: str = Depends(require_admin_user)):
    directory = _tool_dir(tool_id)
    if not directory.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tool not found")
    return success_response(message="tool updated", data=_write_tool(payload, existing_id=tool_id))


@tool_router.delete("/{tool_id}")
async def delete_tool(tool_id: str, _: str = Depends(require_admin_user)):
    directory = _tool_dir(tool_id)
    if not directory.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tool not found")
    bound_skills = [skill.id for skill in skill_registry.all() if tool_id in skill.tool_ids]
    if bound_skills:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"tool is used by skills: {', '.join(bound_skills)}",
        )
    shutil.rmtree(directory)
    skill_registry.reload()
    return success_response(message="tool deleted")
