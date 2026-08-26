"""统一工具执行包装器。

GuardedTool 在不修改 registry 单例的前提下，包住每个工具，统一接管：
- 运行预算：执行前硬拦截 max_tool_calls（不再依赖事后统计）。
- 高风险确认：requires_confirmation 工具命中时存 pending action、推 waiting_confirmation，
  本次不执行；待用户确认后由 /chat/agent/confirm 直接执行。
- 超时：按 timeout_seconds 包 asyncio.wait_for。
- 输出截断：按 max_output_chars 截断工具返回。

token 级流式与 tool_start/tool_end/tool_error 的“可观测”事件由 agent.py 的
astream_events 负责；本包装器只负责“强制执行”这部分语义。
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
from typing import Any

from langchain_core.tools import BaseTool

from app.agent.tool_context import (
    get_confirmed_action_from_context,
    get_current_run_binding_from_context,
    get_current_session_id_from_context,
    get_current_user_id_from_context,
    get_runtime_state_from_context,
    get_thinking_callback_from_context,
)
from app.core.logger_handler import logger
from app.services.pending_action_store import save_pending_action

# BaseTool / run_manager 等由 LangChain 注入、不应转发给内层工具的参数名。
_INJECTED_KEYS = {"run_manager", "callbacks", "config"}


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[输出已截断，超过 {limit} 字符]"


def tool_definition_digest(tool_def: Any) -> str:
    """Fingerprint the executable Tool contract captured before confirmation."""
    tool = tool_def.tool
    schema: dict[str, Any] = {}
    args_schema = getattr(tool, "args_schema", None)
    if args_schema is not None:
        try:
            schema = args_schema.model_json_schema()
        except (AttributeError, TypeError, ValueError):
            schema = {"model": f"{args_schema.__module__}.{args_schema.__qualname__}"}

    implementation = getattr(tool, "coroutine", None) or getattr(tool, "func", None) or tool.__class__
    try:
        implementation_source = inspect.getsource(implementation)
    except (OSError, TypeError):
        implementation_source = (
            f"{getattr(implementation, '__module__', '')}:"
            f"{getattr(implementation, '__qualname__', implementation.__class__.__qualname__)}"
        )

    fields = (
        "id",
        "label",
        "description",
        "category",
        "order",
        "entrypoint",
        "instructions",
        "is_default",
        "visibility",
        "risk_level",
        "requires_confirmation",
        "timeout_seconds",
        "max_output_chars",
        "source",
        "provider_id",
        "external_name",
        "enabled",
        "available",
        "read_only",
    )
    payload = {
        "definition": {field: getattr(tool_def, field, None) for field in fields},
        "tool_name": getattr(tool, "name", None),
        "args_schema": schema,
        "implementation_sha256": hashlib.sha256(implementation_source.encode("utf-8")).hexdigest(),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def tool_provider_config_digest(tool_def: Any) -> str | None:
    """Hash MCP routing/configuration without persisting or exposing secret values."""
    if getattr(tool_def, "source", None) != "mcp":
        return None

    from app.agent.mcp.config import mcp_policy_authority_ready
    from app.agent.mcp.provider import mcp_provider

    if not mcp_policy_authority_ready():
        return None

    provider_id = getattr(tool_def, "provider_id", None)
    external_name = getattr(tool_def, "external_name", None)
    server = next((item for item in mcp_provider.servers() if item.id == provider_id), None)
    if server is None:
        return None
    override = server.tool_overrides.get(external_name) if external_name else None
    override_fields = (
        "label",
        "description",
        "enabled",
        "risk_level",
        "requires_confirmation",
        "timeout_seconds",
        "max_output_chars",
    )
    payload = {
        "id": server.id,
        "enabled": server.enabled,
        "transport": server.transport,
        "command": server.command,
        "args": list(server.args),
        "env": dict(server.env),
        "url": server.url,
        "allow_tools": list(server.allow_tools),
        "deny_tools": list(server.deny_tools),
        "default_risk_level": server.default_risk_level,
        "default_requires_confirmation": server.default_requires_confirmation,
        "timeout_seconds": server.timeout_seconds,
        "max_output_chars": server.max_output_chars,
        "external_name": external_name,
        "override": (
            {field: getattr(override, field) for field in override_fields}
            if override is not None
            else None
        ),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class GuardedTool(BaseTool):
    """包住内层工具，统一执行预算、确认、超时与截断。"""

    model_config = {"arbitrary_types_allowed": True}

    inner_tool: BaseTool
    tool_id: str
    risk_level: str = "low"
    requires_confirmation: bool = False
    timeout_seconds: int = 30
    max_output_chars: int = 10000
    source: str = "local"
    provider_id: str | None = None
    external_name: str | None = None
    definition_digest: str | None = None
    provider_config_digest: str | None = None

    @classmethod
    def wrap(cls, tool_def) -> "GuardedTool":
        inner = tool_def.tool
        return cls(
            name=inner.name,
            description=inner.description,
            args_schema=inner.args_schema,
            inner_tool=inner,
            tool_id=tool_def.id,
            risk_level=tool_def.risk_level,
            requires_confirmation=tool_def.requires_confirmation,
            timeout_seconds=tool_def.timeout_seconds,
            max_output_chars=tool_def.max_output_chars,
            source=tool_def.source,
            provider_id=tool_def.provider_id,
            external_name=tool_def.external_name,
            definition_digest=tool_definition_digest(tool_def),
            provider_config_digest=tool_provider_config_digest(tool_def),
        )

    def _run(self, *args, **kwargs):  # pragma: no cover - 本项目工具均为异步
        raise NotImplementedError("GuardedTool 只支持异步执行，请使用 _arun。")

    async def _emit(self, callback, event: dict) -> None:
        if callback:
            try:
                await callback(event)
            except Exception as exc:  # 事件推送失败不应中断工具执行
                logger.warning(f"【GuardedTool】事件推送失败: {exc}")

    async def _call_inner(self, *args, **kwargs) -> Any:
        inner = self.inner_tool
        if getattr(inner, "coroutine", None) is not None:
            return await inner.coroutine(*args, **kwargs)
        if getattr(inner, "func", None) is not None:
            return inner.func(*args, **kwargs)
        # 兜底：极少数工具未暴露 coroutine/func 时走 ainvoke（会产生嵌套事件）。
        return await inner.ainvoke(kwargs)

    async def _arun(self, *args, **kwargs) -> str:
        # 去掉 LangChain 注入、内层工具不认识的参数。
        for key in _INJECTED_KEYS:
            kwargs.pop(key, None)

        callback = get_thinking_callback_from_context()

        # 1) 运行预算：执行前硬拦截。
        runtime_state = get_runtime_state_from_context()
        if runtime_state is not None:
            runtime_state["tool_calls"] = runtime_state.get("tool_calls", 0) + 1
            max_calls = runtime_state.get("max_tool_calls", 0)
            if max_calls and runtime_state["tool_calls"] > max_calls:
                await self._emit(callback, {
                    "type": "thinking",
                    "stage": "stopped",
                    "content": "已达到工具调用次数预算，未执行本次工具。",
                    "details": {
                        "tool": self.tool_id,
                        "tool_calls": runtime_state["tool_calls"],
                        "max_tool_calls": max_calls,
                    },
                })
                return "已达到本轮工具调用预算，未执行该工具。请缩小任务范围后重试。"

        # 2) 高风险确认：未确认则暂存并阻断本次执行。
        if self.requires_confirmation and not get_confirmed_action_from_context():
            user_id = get_current_user_id_from_context()
            if not user_id:
                return "错误: 无法确定用户身份"
            run_binding = get_current_run_binding_from_context()
            if (
                not run_binding
                or not isinstance(run_binding.get("run_id"), str)
                or not isinstance(run_binding.get("registry_revision"), int)
                or not self.definition_digest
                or (self.source == "mcp" and not self.provider_config_digest)
            ):
                return "高风险操作缺少可验证的运行授权快照，未执行。请重新发起请求。"
            session_id = get_current_session_id_from_context()
            try:
                action_id = await save_pending_action(
                    user_id=user_id,
                    session_id=session_id,
                    tool_id=self.tool_id,
                    args=dict(kwargs),
                    source=self.source,
                    provider_id=self.provider_id,
                    external_name=self.external_name,
                    run_id=run_binding["run_id"],
                    registry_revision=run_binding["registry_revision"],
                    tool_digest=self.definition_digest,
                    provider_config_digest=self.provider_config_digest,
                )
            except Exception as exc:
                logger.error(f"【GuardedTool】写入待确认动作失败: {exc}", exc_info=True)
                return "高风险操作需要确认，但暂存待确认动作失败，未执行。请稍后重试。"

            await self._emit(callback, {
                "type": "waiting_confirmation",
                "stage": "tool_confirmation",
                "content": f"操作「{self.name}」属于高风险，需要你确认后才会执行。",
                "details": {
                    "tool": self.tool_id,
                    "risk_level": self.risk_level,
                    "pending_action_id": action_id,
                    "input_preview": str(dict(kwargs))[:500],
                    "source": self.source,
                    "provider_id": self.provider_id,
                    "external_name": self.external_name,
                },
            })
            return (
                "该操作属于高风险，已暂存为待确认动作，当前未执行。"
                "请在前端点击「确认」以执行，或点击「取消」放弃。"
            )

        # 3) 执行（带超时）。
        try:
            result = await asyncio.wait_for(
                self._call_inner(*args, **kwargs),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            await self._emit(callback, {
                "type": "thinking",
                "stage": "tool_error",
                "content": f"{self.name} 执行超时（>{self.timeout_seconds}s）。",
                "details": {"tool": self.tool_id, "error": "timeout"},
            })
            return f"工具 {self.name} 执行超时（超过 {self.timeout_seconds} 秒），已中止本次调用。"

        # 4) 输出截断。
        text = result if isinstance(result, str) else str(result)
        return _truncate(text, self.max_output_chars)


def wrap_tool(tool_def) -> GuardedTool:
    """把一个 ToolDefinition 包成 GuardedTool。"""
    return GuardedTool.wrap(tool_def)


def wrap_host_tool(
    inner: BaseTool,
    *,
    tool_id: str | None = None,
    timeout_seconds: int = 10,
    max_output_chars: int = 16_000,
) -> GuardedTool:
    """Apply the same run budget and output limits to host-provided tools."""

    return GuardedTool(
        name=inner.name,
        description=inner.description,
        args_schema=inner.args_schema,
        inner_tool=inner,
        tool_id=tool_id or inner.name,
        risk_level="low",
        requires_confirmation=False,
        timeout_seconds=timeout_seconds,
        max_output_chars=max_output_chars,
        source="skill_resource",
    )
