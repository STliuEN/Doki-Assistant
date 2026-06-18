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
        ))
    return loaded
