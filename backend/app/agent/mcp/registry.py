from __future__ import annotations

from app.agent.mcp.provider import McpToolSpec, mcp_provider


class McpToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, McpToolSpec] = {}

    def all(self) -> list[McpToolSpec]:
        return sorted(self._tools.values(), key=lambda item: (item.server_id, item.name))

    def ids(self) -> set[str]:
        return set(self._tools)

    def get(self, tool_id: str) -> McpToolSpec | None:
        return self._tools.get(tool_id)

    async def refresh(self) -> list[McpToolSpec]:
        specs = await mcp_provider.discover_tools()
        self._tools = {spec.id: spec for spec in specs if spec.enabled}
        return self.all()

    def clear(self) -> None:
        self._tools = {}

    def public_catalog(self) -> list[dict]:
        items: list[dict] = []
        for spec in self.all():
            last_error = mcp_provider.last_error(spec.server_id)
            status = "error" if last_error else "enabled"
            items.append(spec.to_public_dict(server_status=status, last_error=last_error))
        return items


mcp_tool_registry = McpToolRegistry()
