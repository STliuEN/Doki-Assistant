from __future__ import annotations

from dataclasses import replace

from langchain_core.tools import tool

from app.agent.skill_registry import ToolDefinition, ToolRegistry


@tool("fixture_tool")
async def _fixture_tool(value: str) -> str:
    """Fixture tool."""
    return value


def _definition(tool_id: str, *, visibility: str) -> ToolDefinition:
    return ToolDefinition(
        id=tool_id,
        label=tool_id,
        description=f"{tool_id} description",
        category="test",
        order=1,
        tool=_fixture_tool,
        entrypoint="tests.test_tool_catalog_visibility:_fixture_tool",
        visibility=visibility,
    )


def test_public_tool_catalog_hides_private_definitions() -> None:
    registry = object.__new__(ToolRegistry)
    public = _definition("public-tool", visibility="public")
    private = replace(public, id="private-tool", label="private-tool", visibility="private")
    registry._tools = {public.id: public, private.id: private}

    assert [item["id"] for item in registry.public_catalog()] == ["public-tool"]
    assert [item["id"] for item in registry.public_catalog(include_private=True)] == [
        "private-tool",
        "public-tool",
    ]
