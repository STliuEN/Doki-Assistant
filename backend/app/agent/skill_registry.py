from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from langchain_core.tools import BaseTool


SKILLS_DIR = Path(__file__).parent / "skills"
TOOLS_DIR = Path(__file__).parent / "tools"


@dataclass(frozen=True)
class ToolDefinition:
    id: str
    label: str
    description: str
    category: str
    order: int
    tool: BaseTool
    entrypoint: str
    instructions: str = ""
    is_default: bool = True
    visibility: str = "public"

    def to_public_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "category": self.category,
            "order": self.order,
            "is_default": self.is_default,
            "visibility": self.visibility,
        }


@dataclass(frozen=True)
class SkillDefinition:
    id: str
    label: str
    description: str
    tool_ids: tuple[str, ...]
    instructions: str
    directory: Path
    is_default: bool = True
    order: int = 100
    visibility: str = "public"

    def to_public_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "tool_ids": list(self.tool_ids),
            "is_default": self.is_default,
            "visibility": self.visibility,
        }


@dataclass(frozen=True)
class SkillResolution:
    skill_ids: list[str]
    tool_ids: list[str]
    tools: list[BaseTool]
    skill_prompts: list[str]


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def _require_string(data: dict[str, Any], key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} requires non-empty string field: {key}")
    return value.strip()


def _optional_string(data: dict[str, Any], key: str, default: str) -> str:
    value = data.get(key, default)
    return value.strip() if isinstance(value, str) and value.strip() else default


def _optional_int(data: dict[str, Any], key: str, default: int) -> int:
    value = data.get(key, default)
    return value if isinstance(value, int) else default


def _optional_bool(data: dict[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    return value if isinstance(value, bool) else default


def _optional_string_list(data: dict[str, Any], key: str, path: Path) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{path} field {key} must be a list of strings")
    return tuple(dict.fromkeys(item.strip() for item in value))


class ToolRegistry:
    def __init__(self, tools_dir: Path = TOOLS_DIR):
        self.tools_dir = tools_dir
        self._tools = self._load_tools()

    def _load_tool_from_entrypoint(self, tool_dir: Path, entrypoint: str) -> BaseTool:
        if ":" not in entrypoint:
            raise ValueError(f"{tool_dir / 'tool.yaml'} entrypoint must use module:function")
        module_name, factory_name = entrypoint.split(":", 1)
        module_path = f"app.agent.tools.{tool_dir.name}.{module_name}"
        importlib.invalidate_caches()
        if module_path in sys.modules:
            module = importlib.reload(sys.modules[module_path])
        else:
            module = importlib.import_module(module_path)
        factory = getattr(module, factory_name, None)
        if factory is None or not callable(factory):
            raise ValueError(f"{tool_dir / 'tool.yaml'} references invalid entrypoint: {entrypoint}")
        tool_obj = factory()
        if not isinstance(tool_obj, BaseTool):
            raise ValueError(f"{tool_dir / 'tool.yaml'} entrypoint must return a LangChain BaseTool")
        return tool_obj

    def _load_tools(self) -> dict[str, ToolDefinition]:
        loaded: dict[str, ToolDefinition] = {}
        for tool_dir in sorted(path for path in self.tools_dir.iterdir() if path.is_dir()):
            config_path = tool_dir / "tool.yaml"
            instructions_path = tool_dir / "TOOL.md"
            if not config_path.exists():
                continue

            data = _read_yaml(config_path)
            tool_id = _require_string(data, "id", config_path)
            if tool_id != tool_dir.name:
                raise ValueError(f"{config_path} id must match tool directory name: {tool_dir.name}")
            entrypoint = _require_string(data, "entrypoint", config_path)
            # TOOL.md 是工具给模型看的描述的唯一来源，必须存在且非空
            if not instructions_path.exists():
                raise ValueError(f"{tool_dir} requires TOOL.md (the only source of the tool description)")
            instructions = instructions_path.read_text(encoding="utf-8").strip()
            if not instructions:
                raise ValueError(f"{instructions_path} must not be empty")

            # 用 TOOL.md 覆盖工具的 description，py 里的占位描述/docstring 不再生效
            tool_obj = self._load_tool_from_entrypoint(tool_dir, entrypoint)
            try:
                tool_obj.description = instructions
            except (AttributeError, ValueError):
                tool_obj = tool_obj.model_copy(update={"description": instructions})

            loaded[tool_id] = ToolDefinition(
                id=tool_id,
                label=_require_string(data, "label", config_path),
                description=_require_string(data, "description", config_path),
                category=_optional_string(data, "category", "general"),
                order=_optional_int(data, "order", 100),
                tool=tool_obj,
                entrypoint=entrypoint,
                instructions=instructions,
                is_default=_optional_bool(data, "default", True),
                visibility=_optional_string(data, "visibility", "public"),
            )
        return loaded

    def all(self) -> list[ToolDefinition]:
        return sorted(self._tools.values(), key=lambda item: (item.order, item.id))

    def ids(self) -> set[str]:
        return set(self._tools)

    def get(self, tool_id: str) -> ToolDefinition:
        return self._tools[tool_id]

    def public_catalog(self) -> list[dict]:
        return [tool.to_public_dict() for tool in self.all()]

    def reload(self) -> None:
        self._tools = self._load_tools()


class SkillRegistry:
    def __init__(self, skills_dir: Path = SKILLS_DIR, tool_registry: ToolRegistry | None = None):
        self.skills_dir = skills_dir
        self.tool_registry = tool_registry or ToolRegistry()
        self._skills = self._load_skills()

    def _load_skills(self) -> dict[str, SkillDefinition]:
        loaded: dict[str, SkillDefinition] = {}
        for skill_dir in sorted(path for path in self.skills_dir.iterdir() if path.is_dir()):
            config_path = skill_dir / "skill.yaml"
            instructions_path = skill_dir / "SKILL.md"
            if not config_path.exists():
                continue
            if not instructions_path.exists():
                raise ValueError(f"{skill_dir} requires SKILL.md")

            data = _read_yaml(config_path)
            skill_id = _require_string(data, "id", config_path)
            tool_ids = _optional_string_list(data, "tools", config_path)
            unknown_tool_ids = [tool_id for tool_id in tool_ids if tool_id not in self.tool_registry.ids()]
            if unknown_tool_ids:
                raise ValueError(f"{config_path} references unknown tools: {', '.join(unknown_tool_ids)}")

            loaded[skill_id] = SkillDefinition(
                id=skill_id,
                label=_require_string(data, "label", config_path),
                description=_require_string(data, "description", config_path),
                tool_ids=tool_ids,
                instructions=instructions_path.read_text(encoding="utf-8").strip(),
                directory=skill_dir,
                is_default=_optional_bool(data, "default", True),
                order=_optional_int(data, "order", 100),
                visibility=_optional_string(data, "visibility", "public"),
            )
        return loaded

    def all(self) -> list[SkillDefinition]:
        return sorted(self._skills.values(), key=lambda item: (item.order, item.id))

    def get(self, skill_id: str) -> SkillDefinition | None:
        return self._skills.get(skill_id)

    def reload(self) -> None:
        self.tool_registry.reload()
        self._skills = self._load_skills()

    def default_skill_ids(self) -> list[str]:
        return [skill.id for skill in self.all() if skill.is_default]

    def default_tool_ids(self) -> list[str]:
        return self.resolve(self.default_skill_ids(), []).tool_ids

    def public_catalog(self) -> dict:
        return {
            "skills": [skill.to_public_dict() for skill in self.all()],
            "tools": self.tool_registry.public_catalog(),
            "default_skill_ids": self.default_skill_ids(),
            "default_tool_ids": self.default_tool_ids(),
        }

    def _validate_ids(self, ids: list[str] | None, allowed_ids: set[str], kind: str) -> list[str] | None:
        if ids is None:
            return None

        unique_ids = list(dict.fromkeys(ids))
        invalid_ids = [item_id for item_id in unique_ids if item_id not in allowed_ids]
        if invalid_ids:
            raise ValueError(f"Unsupported {kind}: {', '.join(invalid_ids)}")
        return unique_ids

    def resolve(self, skill_ids: list[str] | None = None, tool_ids: list[str] | None = None) -> SkillResolution:
        selected_skill_ids = skill_ids
        selected_tool_ids = tool_ids
        if selected_skill_ids is None and selected_tool_ids is None:
            selected_skill_ids = self.default_skill_ids()

        selected_skill_ids = selected_skill_ids or []
        selected_tool_ids = selected_tool_ids or []

        valid_skill_ids = self._validate_ids(selected_skill_ids, set(self._skills), "skill_ids") or []
        valid_tool_ids = self._validate_ids(selected_tool_ids, self.tool_registry.ids(), "tool_ids") or []

        collected_tool_ids: list[str] = []
        skill_prompts: list[str] = []
        for skill_id in valid_skill_ids:
            skill = self._skills[skill_id]
            collected_tool_ids.extend(skill.tool_ids)
            if skill.instructions:
                skill_prompts.append(f"## Skill: {skill.label}\n\n{skill.instructions}")
        collected_tool_ids.extend(valid_tool_ids)

        selected_tool_id_set = set(collected_tool_ids)
        ordered_tool_ids = [tool.id for tool in self.tool_registry.all() if tool.id in selected_tool_id_set]
        tools = [self.tool_registry.get(tool_id).tool for tool_id in ordered_tool_ids]
        return SkillResolution(
            skill_ids=valid_skill_ids,
            tool_ids=ordered_tool_ids,
            tools=tools,
            skill_prompts=skill_prompts,
        )


tool_registry = ToolRegistry()
skill_registry = SkillRegistry(tool_registry=tool_registry)


def get_skill_catalog() -> dict:
    return skill_registry.public_catalog()


def get_default_tools() -> list[BaseTool]:
    return skill_registry.resolve().tools


def resolve_skills(skill_ids: list[str] | None = None, tool_ids: list[str] | None = None) -> SkillResolution:
    return skill_registry.resolve(skill_ids, tool_ids)


def resolve_tools(skill_ids: list[str] | None = None, tool_ids: list[str] | None = None) -> list[BaseTool]:
    return resolve_skills(skill_ids, tool_ids).tools
