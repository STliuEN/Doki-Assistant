from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, create_model

from app.agent.mcp.provider import McpToolProvider, McpToolSpec, mcp_provider


def _python_type(schema: dict[str, Any]) -> Any:
    schema_type = schema.get("type")
    if schema_type == "integer":
        return int
    if schema_type == "number":
        return float
    if schema_type == "boolean":
        return bool
    if schema_type == "array":
        return list
    if schema_type == "object":
        return dict
    return str


def schema_to_model(tool_id: str, input_schema: dict[str, Any]) -> type[BaseModel]:
    properties = input_schema.get("properties") if isinstance(input_schema, dict) else {}
    required = set(input_schema.get("required", [])) if isinstance(input_schema, dict) else set()
    if not isinstance(properties, dict) or not properties:
        # 无参数工具：返回空入参模型，避免注入并不存在的 query 字段。
        model_name = f"{tool_id.title().replace('_', '')}Input"
        return create_model(model_name)

    fields: dict[str, tuple[Any, Any]] = {}
    for name, prop_schema in properties.items():
        if not isinstance(prop_schema, dict):
            prop_schema = {}
        field_type = _python_type(prop_schema)
        description = str(prop_schema.get("description", ""))
        default = ... if name in required else prop_schema.get("default", None)
        fields[str(name)] = (field_type, Field(default=default, description=description))
    model_name = f"{tool_id.title().replace('_', '')}Input"
    return create_model(model_name, **fields)


class McpLangChainTool(BaseTool):
    model_config = {"arbitrary_types_allowed": True}

    server_id: str
    external_name: str
    provider: McpToolProvider = mcp_provider

    def _run(self, *args, **kwargs):  # pragma: no cover - project agent tools are async
        raise NotImplementedError("MCP tools only support async execution")

    async def _arun(self, *args, **kwargs) -> str:
        # LangChain 已根据 args_schema 把入参解析为 kwargs，这里只清理注入参数。
        kwargs.pop("run_manager", None)
        kwargs.pop("callbacks", None)
        kwargs.pop("config", None)
        return await self.provider.call_tool(self.server_id, self.external_name, kwargs)


def make_langchain_tool(spec: McpToolSpec) -> McpLangChainTool:
    return McpLangChainTool(
        name=f"{spec.id}_tool",
        description=spec.description,
        args_schema=schema_to_model(spec.id, spec.input_schema),
        server_id=spec.server_id,
        external_name=spec.name,
    )
