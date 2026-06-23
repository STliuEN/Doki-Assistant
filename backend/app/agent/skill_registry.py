from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from langchain_core.tools import BaseTool

from app.agent.mcp.adapter import make_langchain_tool
from app.agent.mcp.registry import mcp_tool_registry
from app.core.logger_handler import logger


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
    risk_level: str = "low"
    requires_confirmation: bool = False
    timeout_seconds: int = 600
    max_output_chars: int = 4000
    source: str = "local"
    provider_id: str | None = None
    external_name: str | None = None
    enabled: bool = True
    available: bool = True
    read_only: bool = False

    def to_public_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "category": self.category,
            "order": self.order,
            "is_default": self.is_default,
            "visibility": self.visibility,
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
            "timeout_seconds": self.timeout_seconds,
            "max_output_chars": self.max_output_chars,
            "instructions": self.instructions,
            "source": self.source,
            "provider_id": self.provider_id,
            "external_name": self.external_name,
            "enabled": self.enabled,
            "available": self.available,
            "read_only": self.read_only,
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
    # 被请求但最终未进入工具集的 tool_id（未注册 / 不可用 / 被禁用）。
    missing_tool_ids: list[str] = field(default_factory=list)
    # 面向模型/用户的运行提示（注入 system prompt，避免静默降级）。
    notices: list[str] = field(default_factory=list)


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


def _risk_level(data: dict[str, Any], path: Path) -> str:
    value = _optional_string(data, "risk_level", "low")
    if value not in {"low", "medium", "high"}:
        raise ValueError(f"{path} risk_level must be one of: low, medium, high")
    return value


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

    def _load_mcp_tools(self) -> dict[str, ToolDefinition]:
        loaded: dict[str, ToolDefinition] = {}
        for spec in mcp_tool_registry.all():
            tool_obj = make_langchain_tool(spec)
            loaded[spec.id] = ToolDefinition(
                id=spec.id,
                label=spec.label,
                description=spec.description,
                category="mcp",
                order=1000,
                tool=tool_obj,
                entrypoint=f"mcp:{spec.server_id}:{spec.name}",
                instructions=spec.description,
                is_default=False,
                visibility="public",
                risk_level=spec.risk_level,
                requires_confirmation=spec.requires_confirmation,
                timeout_seconds=spec.timeout_seconds,
                max_output_chars=spec.max_output_chars,
                source="mcp",
                provider_id=spec.server_id,
                external_name=spec.name,
                enabled=spec.enabled,
                available=spec.available,
                read_only=spec.read_only,
            )
        return loaded

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
                risk_level=_risk_level(data, config_path),
                requires_confirmation=_optional_bool(data, "requires_confirmation", False),
                timeout_seconds=max(1, _optional_int(data, "timeout_seconds", 600)),
                max_output_chars=max(256, _optional_int(data, "max_output_chars", 4000)),
            )
        loaded.update(self._load_mcp_tools())
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
            # MCP tools are discovered after startup. Allow skill definitions to
            # reference them before the first refresh, then resolve them once
            # mcp_tool_registry has populated the shared tool registry.
            unknown_tool_ids = [
                tool_id
                for tool_id in tool_ids
                if tool_id not in self.tool_registry.ids() and not tool_id.startswith("mcp_")
            ]
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

    def _drop_reason(self, tool_id: str) -> str:
        if tool_id not in self.tool_registry.ids():
            return "未注册（MCP 尚未发现或工具已移除）"
        tool = self.tool_registry.get(tool_id)
        if not tool.available:
            return "服务不可用（MCP server 离线或发现失败）"
        if not tool.enabled:
            return "已被禁用"
        return "未选中"

    def resolve(self, skill_ids: list[str] | None = None, tool_ids: list[str] | None = None) -> SkillResolution:
        # 区分"显式空"（调用方明确传 [] 表示本次不用任何能力）与"未指定"（None → 用默认）。
        explicit_empty = (
            (skill_ids is not None and len(skill_ids) == 0)
            and (tool_ids is None or len(tool_ids) == 0)
        )

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
        declared_by_skill: dict[str, str] = {}
        for skill_id in valid_skill_ids:
            skill = self._skills[skill_id]
            for tid in skill.tool_ids:
                declared_by_skill.setdefault(tid, skill_id)
            collected_tool_ids.extend(skill.tool_ids)
            if skill.instructions:
                skill_prompts.append(f"## Skill: {skill.label}\n\n{skill.instructions}")
        collected_tool_ids.extend(valid_tool_ids)

        selected_tool_id_set = set(collected_tool_ids)
        ordered_tool_ids = [
            tool.id
            for tool in self.tool_registry.all()
            if tool.id in selected_tool_id_set and tool.enabled and tool.available
        ]

        # B1a：诊断被丢弃的工具——不再静默，给出 tool_id、来源 skill 与原因。
        # 但 MCP 尚未首次发现时（如启动前的模块级默认装配），其工具属于"待发现"，
        # 降级为 debug，避免每次启动刷一条误导性告警。
        mcp_ready = mcp_tool_registry.has_refreshed
        kept = set(ordered_tool_ids)
        missing_tool_ids: list[str] = []
        notices: list[str] = []
        for tid in dict.fromkeys(collected_tool_ids):
            if tid in kept:
                continue
            missing_tool_ids.append(tid)
            source = declared_by_skill.get(tid)
            origin = f"，来自 skill {source}" if source else ""
            message = f"【工具装配】跳过工具 {tid}（{self._drop_reason(tid)}）{origin}"
            if tid.startswith("mcp_") and not mcp_ready:
                logger.debug(f"{message} [MCP 尚未发现，待刷新]")
            else:
                logger.warning(message)

        # 现包现用 GuardedTool，统一接管预算/确认/超时/截断；不修改 registry 单例。
        from app.agent.tool_guard import wrap_tool
        tools = [wrap_tool(self.tool_registry.get(tool_id)) for tool_id in ordered_tool_ids]

        # B1b：被选中的 skill 解析后零工具——升级为 error 日志并注入可见提示。
        # 若缺的全是"待发现"的 MCP 工具（尚未首次发现），则跳过——这只是启动期的暂态。
        mcp_pending_only = (
            not mcp_ready
            and missing_tool_ids
            and all(tid.startswith("mcp_") for tid in missing_tool_ids)
        )
        if valid_skill_ids and not tools and not mcp_pending_only:
            logger.error(
                f"【工具装配】skills {valid_skill_ids} 解析后无任何可用工具；missing={missing_tool_ids}"
            )
            notices.append(
                "当前所选能力依赖的工具暂不可用（可能是 MCP 服务未连通）。"
                "请如实告知用户该能力暂不可用并建议稍后重试，不要假装拥有或调用这些工具。"
            )

        # B2b：显式空 skill_ids 是合法的"纯对话"模式，但要让模型明确知道，避免静默。
        if explicit_empty:
            notices.append(
                "本次未启用任何能力或工具，请仅进行普通对话，不要假装拥有工具。"
            )

        return SkillResolution(
            skill_ids=valid_skill_ids,
            tool_ids=ordered_tool_ids,
            tools=tools,
            skill_prompts=skill_prompts,
            missing_tool_ids=missing_tool_ids,
            notices=notices,
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
