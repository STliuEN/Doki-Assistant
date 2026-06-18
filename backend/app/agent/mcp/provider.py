from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.agent.mcp.config import McpServerConfig, load_mcp_servers, make_mcp_tool_id
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class McpToolSpec:
    id: str
    server_id: str
    server_label: str
    name: str
    label: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "medium"
    requires_confirmation: bool = True
    timeout_seconds: int = 30
    max_output_chars: int = 4000
    enabled: bool = True
    read_only: bool = False

    def to_public_dict(self, server_status: str = "enabled", last_error: str | None = None) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "category": "mcp",
            "order": 1000,
            "is_default": False,
            "visibility": "public",
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
            "timeout_seconds": self.timeout_seconds,
            "max_output_chars": self.max_output_chars,
            "source": "mcp",
            "provider_id": self.server_id,
            "external_name": self.name,
            "enabled": self.enabled,
            "read_only": self.read_only,
            "server_status": server_status,
            "last_error": last_error,
        }


class McpProviderError(RuntimeError):
    """Raised when MCP discovery or invocation fails."""


class McpToolProvider:
    def __init__(self) -> None:
        self._last_errors: dict[str, str] = {}

    def servers(self) -> list[McpServerConfig]:
        return load_mcp_servers()

    def last_error(self, server_id: str) -> str | None:
        return self._last_errors.get(server_id)

    async def discover_tools(self) -> list[McpToolSpec]:
        tools: list[McpToolSpec] = []
        for server in self.servers():
            if not server.enabled:
                continue
            try:
                discovered = await self.list_tools(server)
                tools.extend(discovered)
                self._last_errors.pop(server.id, None)
            except Exception as exc:
                message = str(exc)
                self._last_errors[server.id] = message
                logger.warning(f"【MCP】发现 server {server.id} 工具失败: {message}")
        return tools

    async def list_tools(self, server: McpServerConfig) -> list[McpToolSpec]:
        raw_tools = await self._list_tools_raw(server)
        allow = set(server.allow_tools)
        deny = set(server.deny_tools)
        specs: list[McpToolSpec] = []
        for raw in raw_tools:
            name = _get_tool_name(raw)
            if not name:
                continue
            if allow and name not in allow:
                continue
            if name in deny:
                continue
            description = _get_tool_description(raw) or name
            input_schema = _get_tool_input_schema(raw)
            read_only = _get_tool_read_only(raw)
            # 只读工具无副作用，放宽二次确认要求。
            requires_confirmation = server.default_requires_confirmation and not read_only
            specs.append(McpToolSpec(
                id=make_mcp_tool_id(server.id, name),
                server_id=server.id,
                server_label=server.label,
                name=name,
                label=name,
                description=description,
                input_schema=input_schema,
                risk_level=server.default_risk_level,
                requires_confirmation=requires_confirmation,
                timeout_seconds=server.timeout_seconds,
                max_output_chars=server.max_output_chars,
                read_only=read_only,
            ))
        return specs

    async def call_tool(self, server_id: str, tool_name: str, arguments: dict[str, Any]) -> str:
        server = next((item for item in self.servers() if item.id == server_id), None)
        if server is None:
            raise McpProviderError(f"MCP server not found: {server_id}")
        if not server.enabled:
            raise McpProviderError(f"MCP server disabled: {server_id}")
        return await self._call_tool_raw(server, tool_name, arguments)

    async def close(self) -> None:
        return None

    async def _list_tools_raw(self, server: McpServerConfig) -> list[Any]:
        async with self._session(server) as session:
            result = await session.list_tools()
            return list(getattr(result, "tools", []) or [])

    async def _call_tool_raw(self, server: McpServerConfig, tool_name: str, arguments: dict[str, Any]) -> str:
        async with self._session(server) as session:
            result = await session.call_tool(tool_name, arguments=arguments)
            return normalize_mcp_result(result)

    def _session(self, server: McpServerConfig):
        if server.transport == "stdio":
            return _stdio_session(server)
        if server.transport in {"http", "streamable_http"}:
            return _streamable_http_session(server)
        if server.transport == "sse":
            return _sse_session(server)
        raise McpProviderError(f"Unsupported MCP transport: {server.transport}")


class _stdio_session:
    def __init__(self, server: McpServerConfig) -> None:
        self.server = server
        self._stdio_cm = None
        self._session_cm = None
        self._session = None

    async def __aenter__(self):
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:
            raise McpProviderError("Python package 'mcp' is required for MCP stdio support") from exc
        if not self.server.command:
            raise McpProviderError(f"MCP stdio server {self.server.id} requires command")
        params = StdioServerParameters(command=self.server.command, args=list(self.server.args), env=self.server.env or None)
        self._stdio_cm = stdio_client(params)
        read, write = await self._stdio_cm.__aenter__()
        self._session_cm = ClientSession(read, write)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        if self._session_cm is not None:
            await self._session_cm.__aexit__(exc_type, exc, tb)
        if self._stdio_cm is not None:
            await self._stdio_cm.__aexit__(exc_type, exc, tb)


class _streamable_http_session:
    def __init__(self, server: McpServerConfig) -> None:
        self.server = server
        self._http_cm = None
        self._session_cm = None
        self._session = None

    async def __aenter__(self):
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError as exc:
            raise McpProviderError("Python package 'mcp' is required for MCP HTTP support") from exc
        if not self.server.url:
            raise McpProviderError(f"MCP HTTP server {self.server.id} requires url")
        self._http_cm = streamablehttp_client(self.server.url)
        read, write, _ = await self._http_cm.__aenter__()
        self._session_cm = ClientSession(read, write)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        if self._session_cm is not None:
            await self._session_cm.__aexit__(exc_type, exc, tb)
        if self._http_cm is not None:
            await self._http_cm.__aexit__(exc_type, exc, tb)


class _sse_session:
    def __init__(self, server: McpServerConfig) -> None:
        self.server = server
        self._sse_cm = None
        self._session_cm = None
        self._session = None

    async def __aenter__(self):
        try:
            from mcp import ClientSession
            from mcp.client.sse import sse_client
        except ImportError as exc:
            raise McpProviderError("Python package 'mcp' is required for MCP SSE support") from exc
        if not self.server.url:
            raise McpProviderError(f"MCP SSE server {self.server.id} requires url")
        self._sse_cm = sse_client(self.server.url)
        read, write = await self._sse_cm.__aenter__()
        self._session_cm = ClientSession(read, write)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        if self._session_cm is not None:
            await self._session_cm.__aexit__(exc_type, exc, tb)
        if self._sse_cm is not None:
            await self._sse_cm.__aexit__(exc_type, exc, tb)


def _get_tool_name(raw: Any) -> str:
    if isinstance(raw, dict):
        return str(raw.get("name", "")).strip()
    return str(getattr(raw, "name", "")).strip()


def _get_tool_description(raw: Any) -> str:
    if isinstance(raw, dict):
        return str(raw.get("description", "")).strip()
    return str(getattr(raw, "description", "") or "").strip()


def _get_tool_input_schema(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        value = raw.get("inputSchema") or raw.get("input_schema") or {}
    else:
        value = getattr(raw, "inputSchema", None) or getattr(raw, "input_schema", None) or {}
    return value if isinstance(value, dict) else {}


def _get_tool_read_only(raw: Any) -> bool:
    """读取 MCP 工具的 annotations.readOnlyHint（不存在时默认 False）。"""
    if isinstance(raw, dict):
        annotations = raw.get("annotations")
    else:
        annotations = getattr(raw, "annotations", None)
    if annotations is None:
        return False
    if isinstance(annotations, dict):
        return bool(annotations.get("readOnlyHint", False))
    return bool(getattr(annotations, "readOnlyHint", False))


def normalize_mcp_result(result: Any) -> str:
    content = getattr(result, "content", None)
    if content is None and isinstance(result, dict):
        content = result.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            text = getattr(item, "text", None)
            if text is None and isinstance(item, dict):
                text = item.get("text")
            parts.append(str(text) if text is not None else json.dumps(item, ensure_ascii=False, default=str))
        return "\n".join(parts)
    if content is not None:
        return str(content)
    return json.dumps(result, ensure_ascii=False, default=str)


mcp_provider = McpToolProvider()
