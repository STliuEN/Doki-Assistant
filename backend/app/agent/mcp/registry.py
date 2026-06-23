from __future__ import annotations

import asyncio
import time
from dataclasses import replace

from app.agent.mcp.provider import McpToolSpec, mcp_provider

# 处于错误态时，最多每隔这么多秒在请求路径上尝试一次重发现（自愈探针）。
# 健康态下不会触发，所以稳态零额外开销。
_ERROR_RETRY_TTL_SECONDS = 30.0


class McpToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, McpToolSpec] = {}
        self._lock = asyncio.Lock()
        self._last_refresh: float | None = None

    def all(self) -> list[McpToolSpec]:
        return sorted(self._tools.values(), key=lambda item: (item.server_id, item.name))

    def ids(self) -> set[str]:
        return set(self._tools)

    @property
    def has_refreshed(self) -> bool:
        """是否已至少发现过一次。未发现前，MCP 工具属于"待发现"而非"缺失/损坏"。"""
        return self._last_refresh is not None

    def get(self, tool_id: str) -> McpToolSpec | None:
        return self._tools.get(tool_id)

    async def refresh(self) -> list[McpToolSpec]:
        """显式刷新（启动、管理端操作）。始终重新发现。"""
        async with self._lock:
            return await self._discover_locked()

    async def ensure_fresh(self) -> bool:
        """惰性重发现：仅在从未发现过、或存在错误态 server 且超过重试间隔时才真正发现。
        返回是否实际刷新过（调用方据此决定是否 reload skill_registry）。"""
        if not self._needs_refresh():
            return False
        async with self._lock:
            # 双检：可能已有并发请求在锁内完成了刷新。
            if not self._needs_refresh():
                return False
            await self._discover_locked()
            return True

    def _needs_refresh(self) -> bool:
        if self._last_refresh is None:
            return True
        if mcp_provider.has_errors() and (time.monotonic() - self._last_refresh) >= _ERROR_RETRY_TTL_SECONDS:
            return True
        return False

    async def _discover_locked(self) -> list[McpToolSpec]:
        specs = await mcp_provider.discover_tools()
        merged: dict[str, McpToolSpec] = {spec.id: spec for spec in specs}
        fresh_server_ids = {spec.server_id for spec in specs}

        # 失败保留：对本轮发现失败的启用 server，保留上次已知的 spec 并标记 available=False，
        # 这样 UI 仍能看到工具+错误，而 LangChain 工具也得以保留以便恢复后立即可用。
        failed_server_ids = mcp_provider.error_server_ids() - fresh_server_ids
        if failed_server_ids:
            for spec in self._tools.values():
                if spec.server_id in failed_server_ids and spec.id not in merged:
                    merged[spec.id] = replace(spec, available=False)

        self._tools = merged
        self._last_refresh = time.monotonic()
        return self.all()

    def clear(self) -> None:
        self._tools = {}

    def public_catalog(self) -> list[dict]:
        items: list[dict] = []
        for spec in self.all():
            last_error = mcp_provider.last_error(spec.server_id)
            status = "error" if (last_error or not spec.available) else "enabled"
            items.append(spec.to_public_dict(server_status=status, last_error=last_error))
        return items


mcp_tool_registry = McpToolRegistry()
