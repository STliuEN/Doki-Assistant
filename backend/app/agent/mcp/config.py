from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


CONFIG_PATH = Path(__file__).parents[2] / "config" / "mcp.yaml"
VALID_RISK_LEVELS = {"low", "medium", "high"}


@dataclass(frozen=True)
class McpServerConfig:
    id: str
    label: str
    description: str = ""
    enabled: bool = False
    transport: str = "stdio"
    command: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    allow_tools: tuple[str, ...] = ()
    deny_tools: tuple[str, ...] = ()
    default_risk_level: str = "medium"
    default_requires_confirmation: bool = True
    timeout_seconds: int = 30
    max_output_chars: int = 4000
    tool_overrides: dict[str, "McpToolOverride"] = field(default_factory=dict)


@dataclass(frozen=True)
class McpToolOverride:
    label: str | None = None
    description: str | None = None
    enabled: bool | None = None
    risk_level: str | None = None
    requires_confirmation: bool | None = None
    timeout_seconds: int | None = None
    max_output_chars: int | None = None


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _int_value(value: Any, default: int, minimum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, number)


def _optional_int_override(value: Any, minimum: int) -> int | None:
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return max(minimum, number)


def _optional_string_override(value: Any, max_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    return text[:max_length]


def _load_tool_overrides(value: Any) -> dict[str, McpToolOverride]:
    if not isinstance(value, dict):
        return {}
    overrides: dict[str, McpToolOverride] = {}
    for tool_name, item in value.items():
        if not isinstance(item, dict):
            continue
        name = str(tool_name).strip()
        if not name:
            continue
        risk_level = item.get("risk_level")
        risk_level = str(risk_level).strip() if risk_level is not None else None
        if risk_level is not None and risk_level not in VALID_RISK_LEVELS:
            risk_level = None
        overrides[name] = McpToolOverride(
            label=_optional_string_override(item.get("label"), 80),
            description=_optional_string_override(item.get("description"), 1000),
            enabled=item.get("enabled") if isinstance(item.get("enabled"), bool) else None,
            risk_level=risk_level,
            requires_confirmation=item.get("requires_confirmation") if isinstance(item.get("requires_confirmation"), bool) else None,
            timeout_seconds=_optional_int_override(item.get("timeout_seconds"), 1),
            max_output_chars=_optional_int_override(item.get("max_output_chars"), 256),
        )
    return overrides


def make_mcp_tool_id(server_id: str, tool_name: str) -> str:
    raw = f"mcp_{server_id}_{tool_name}".lower()
    normalized = "".join(char if char.isalnum() else "_" for char in raw)
    compact = "_".join(part for part in normalized.split("_") if part)
    return compact[:64] or "mcp_tool"


def load_mcp_servers(config_path: Path = CONFIG_PATH) -> list[McpServerConfig]:
    if not config_path.exists():
        return []
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    servers = data.get("servers", []) if isinstance(data, dict) else []
    if not isinstance(servers, list):
        return []

    loaded: list[McpServerConfig] = []
    seen_ids: set[str] = set()
    for item in servers:
        if not isinstance(item, dict):
            continue
        server_id = str(item.get("id", "")).strip()
        if not server_id or server_id in seen_ids:
            continue
        seen_ids.add(server_id)
        risk_level = str(item.get("default_risk_level", "medium")).strip()
        if risk_level not in VALID_RISK_LEVELS:
            risk_level = "medium"
        loaded.append(McpServerConfig(
            id=server_id,
            label=str(item.get("label", server_id)).strip() or server_id,
            description=str(item.get("description", "")).strip(),
            enabled=bool(item.get("enabled", False)),
            transport=str(item.get("transport", "stdio")).strip() or "stdio",
            command=str(item["command"]).strip() if item.get("command") else None,
            args=_string_tuple(item.get("args")),
            env=_string_dict(item.get("env")),
            url=str(item["url"]).strip() if item.get("url") else None,
            allow_tools=_string_tuple(item.get("allow_tools")),
            deny_tools=_string_tuple(item.get("deny_tools")),
            default_risk_level=risk_level,
            default_requires_confirmation=bool(item.get("default_requires_confirmation", True)),
            timeout_seconds=_int_value(item.get("timeout_seconds"), 30, 1),
            max_output_chars=_int_value(item.get("max_output_chars"), 4000, 256),
            tool_overrides=_load_tool_overrides(item.get("tool_overrides")),
        ))
    return loaded


def update_mcp_tool_override(
    server_id: str,
    tool_name: str,
    patch: dict[str, Any],
    config_path: Path = CONFIG_PATH,
) -> None:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    if not isinstance(data, dict):
        data = {}
    servers = data.get("servers")
    if not isinstance(servers, list):
        servers = []
        data["servers"] = servers

    target = None
    for item in servers:
        if isinstance(item, dict) and str(item.get("id", "")).strip() == server_id:
            target = item
            break
    if target is None:
        raise KeyError(f"MCP server not found: {server_id}")

    allow_tools = _string_tuple(target.get("allow_tools"))
    deny_tools = _string_tuple(target.get("deny_tools"))
    if allow_tools and tool_name not in allow_tools:
        raise KeyError(f"MCP tool not allowed by server config: {tool_name}")
    if tool_name in deny_tools:
        raise KeyError(f"MCP tool denied by server config: {tool_name}")

    overrides = target.get("tool_overrides")
    if not isinstance(overrides, dict):
        overrides = {}
        target["tool_overrides"] = overrides
    current = overrides.get(tool_name)
    if not isinstance(current, dict):
        current = {}
        overrides[tool_name] = current

    allowed_keys = {
        "label",
        "description",
        "enabled",
        "risk_level",
        "requires_confirmation",
        "timeout_seconds",
        "max_output_chars",
    }
    for key, value in patch.items():
        if key in allowed_keys:
            current[key] = value

    config_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def update_mcp_server_config(
    server_id: str,
    patch: dict[str, Any],
    config_path: Path = CONFIG_PATH,
) -> None:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    if not isinstance(data, dict):
        data = {}
    servers = data.get("servers")
    if not isinstance(servers, list):
        servers = []
        data["servers"] = servers

    target = None
    for item in servers:
        if isinstance(item, dict) and str(item.get("id", "")).strip() == server_id:
            target = item
            break
    if target is None:
        raise KeyError(f"MCP server not found: {server_id}")

    transport = str(target.get("transport", "stdio")).strip() or "stdio"
    for key, value in patch.items():
        if key == "enabled":
            target[key] = bool(value)
        elif key == "label":
            text = str(value).strip()
            if not text:
                raise ValueError("MCP server label must not be empty")
            target[key] = text[:80]
        elif key == "description":
            target[key] = str(value).strip()[:500]
        elif key == "url":
            if transport == "stdio":
                raise ValueError("MCP stdio server does not use url/ip")
            text = str(value).strip()
            if not text.startswith(("http://", "https://")):
                raise ValueError("MCP server url must start with http:// or https://")
            target[key] = text[:2000]

    config_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def delete_mcp_tool_config(
    server_id: str,
    tool_name: str,
    config_path: Path = CONFIG_PATH,
) -> None:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    if not isinstance(data, dict):
        data = {}
    servers = data.get("servers")
    if not isinstance(servers, list):
        raise KeyError(f"MCP server not found: {server_id}")

    target = None
    for item in servers:
        if isinstance(item, dict) and str(item.get("id", "")).strip() == server_id:
            target = item
            break
    if target is None:
        raise KeyError(f"MCP server not found: {server_id}")

    deny_tools = list(_string_tuple(target.get("deny_tools")))
    if tool_name not in deny_tools:
        deny_tools.append(tool_name)
    target["deny_tools"] = deny_tools

    overrides = target.get("tool_overrides")
    if isinstance(overrides, dict):
        overrides.pop(tool_name, None)
        if not overrides:
            target.pop("tool_overrides", None)

    config_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def delete_mcp_server_config(
    server_id: str,
    config_path: Path = CONFIG_PATH,
) -> None:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    if not isinstance(data, dict):
        data = {}
    servers = data.get("servers")
    if not isinstance(servers, list):
        raise KeyError(f"MCP server not found: {server_id}")

    kept = [
        item
        for item in servers
        if not (isinstance(item, dict) and str(item.get("id", "")).strip() == server_id)
    ]
    if len(kept) == len(servers):
        raise KeyError(f"MCP server not found: {server_id}")
    data["servers"] = kept

    config_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
