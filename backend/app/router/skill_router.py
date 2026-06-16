from pathlib import Path
import re
import shutil
from typing import Any

import yaml
from fastapi import HTTPException, status
from fastapi.routing import APIRouter
from pydantic import BaseModel, Field

from app.agent.skill_registry import SKILLS_DIR, get_skill_catalog, skill_registry
from app.core.success_response import success_response

skill_router = APIRouter(prefix="/skills", tags=["skills"])

SAFE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


class SkillPayload(BaseModel):
    id: str = Field(min_length=2, max_length=64)
    label: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=500)
    tools: list[str] = []
    default: bool = True
    visibility: str = "public"
    order: int = 100
    instructions: str = Field(default="", max_length=20000)


def _validate_skill_id(skill_id: str) -> str:
    value = skill_id.strip()
    if not SAFE_ID_PATTERN.match(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="skill id must start with a lowercase letter and contain only lowercase letters, numbers, and underscores",
        )
    return value


def _skill_dir(skill_id: str) -> Path:
    return SKILLS_DIR / _validate_skill_id(skill_id)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="skill not found")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid skill.yaml")
    return data


def _read_skill_detail(skill_id: str) -> dict:
    directory = _skill_dir(skill_id)
    config_path = directory / "skill.yaml"
    instructions_path = directory / "SKILL.md"
    data = _read_yaml(config_path)
    return {
        "id": data.get("id", skill_id),
        "label": data.get("label", ""),
        "description": data.get("description", ""),
        "tools": data.get("tools", []),
        "default": bool(data.get("default", True)),
        "visibility": data.get("visibility", "public"),
        "order": int(data.get("order", 100)),
        "instructions": instructions_path.read_text(encoding="utf-8") if instructions_path.exists() else "",
    }


def _write_skill(payload: SkillPayload, existing_id: str | None = None) -> dict:
    skill_id = _validate_skill_id(payload.id)
    valid_tool_ids = {tool["id"] for tool in get_skill_catalog()["tools"]}
    invalid_tools = [tool_id for tool_id in payload.tools if tool_id not in valid_tool_ids]
    if invalid_tools:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"unknown tools: {', '.join(invalid_tools)}")

    if existing_id and existing_id != skill_id:
        old_dir = _skill_dir(existing_id)
        if old_dir.exists():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="renaming skill id is not supported")

    directory = _skill_dir(skill_id)
    directory.mkdir(parents=True, exist_ok=True)

    config = {
        "id": skill_id,
        "label": payload.label,
        "description": payload.description,
        "tools": list(dict.fromkeys(payload.tools)),
        "default": payload.default,
        "visibility": payload.visibility,
        "order": payload.order,
    }
    (directory / "skill.yaml").write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (directory / "SKILL.md").write_text(payload.instructions.strip() + "\n", encoding="utf-8")
    skill_registry.reload()
    return _read_skill_detail(skill_id)


@skill_router.get("/catalog")
async def get_skills_catalog():
    return success_response(data=get_skill_catalog())


@skill_router.get("/{skill_id}")
async def get_skill_detail(skill_id: str):
    return success_response(data=_read_skill_detail(skill_id))


@skill_router.post("")
async def create_skill(payload: SkillPayload):
    directory = _skill_dir(payload.id)
    if directory.exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="skill already exists")
    return success_response(message="skill created", data=_write_skill(payload))


@skill_router.put("/{skill_id}")
async def update_skill(skill_id: str, payload: SkillPayload):
    directory = _skill_dir(skill_id)
    if not directory.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="skill not found")
    if payload.id != skill_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="renaming skill id is not supported")
    return success_response(message="skill updated", data=_write_skill(payload, existing_id=skill_id))


@skill_router.delete("/{skill_id}")
async def delete_skill(skill_id: str):
    directory = _skill_dir(skill_id)
    if not directory.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="skill not found")
    shutil.rmtree(directory)
    skill_registry.reload()
    return success_response(message="skill deleted")
