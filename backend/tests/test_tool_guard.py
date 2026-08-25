from __future__ import annotations

import asyncio

import pytest
from langchain_core.tools import tool

from app.agent.tool_context import (
    set_confirmed_action,
    set_current_run_binding,
    set_current_session_id,
    set_current_user_id,
    set_runtime_state,
    set_thinking_callback,
)
from app.agent.tool_guard import GuardedTool, _truncate


def _run(coroutine):
    return asyncio.run(coroutine)


def _wrapped(inner, **overrides):
    values = {
        "name": inner.name,
        "description": inner.description,
        "args_schema": inner.args_schema,
        "inner_tool": inner,
        "tool_id": "fixture",
        "timeout_seconds": 1,
        "max_output_chars": 100,
    }
    values.update(overrides)
    return GuardedTool(**values)


@pytest.fixture(autouse=True)
def _reset_tool_context():
    set_current_user_id(None)
    set_current_session_id(None)
    set_runtime_state(None)
    set_confirmed_action(False)
    set_thinking_callback(None)
    set_current_run_binding(None, None)
    yield
    set_current_user_id(None)
    set_current_session_id(None)
    set_runtime_state(None)
    set_confirmed_action(False)
    set_thinking_callback(None)
    set_current_run_binding(None, None)


def test_truncate_preserves_short_output_and_marks_long_output():
    assert _truncate("short", 5) == "short"
    assert _truncate("abcdef", 5) == "abcde\n[输出已截断，超过 5 字符]"


def test_budget_blocks_call_before_inner_tool_executes():
    calls = []

    @tool("fixture_tool")
    async def inner(value: str) -> str:
        """Fixture tool."""
        calls.append(value)
        return value

    events = []

    async def capture(event):
        events.append(event)

    set_runtime_state({"tool_calls": 1, "max_tool_calls": 1})
    set_thinking_callback(capture)
    result = _run(_wrapped(inner).ainvoke({"value": "blocked"}))

    assert calls == []
    assert "预算" in result
    assert events[0]["stage"] == "stopped"


def test_confirmation_without_user_identity_fails_closed():
    @tool("fixture_tool")
    async def inner(value: str) -> str:
        """Fixture tool."""
        return value

    result = _run(_wrapped(inner, requires_confirmation=True).ainvoke({"value": "x"}))

    assert result == "错误: 无法确定用户身份"


def test_confirmation_saves_action_emits_event_and_skips_inner(monkeypatch):
    calls = []
    saved = []
    events = []

    @tool("fixture_tool")
    async def inner(value: str) -> str:
        """Fixture tool."""
        calls.append(value)
        return value

    async def fake_save(**kwargs):
        saved.append(kwargs)
        return "pending-1"

    async def capture(event):
        events.append(event)

    monkeypatch.setattr("app.agent.tool_guard.save_pending_action", fake_save)
    set_current_user_id("user-1")
    set_current_session_id("session-1")
    set_current_run_binding("run-1", 7)
    set_thinking_callback(capture)

    result = _run(
        _wrapped(
            inner,
            requires_confirmation=True,
            risk_level="high",
            definition_digest="a" * 64,
        ).ainvoke({"value": "x"})
    )

    assert calls == []
    assert saved[0]["user_id"] == "user-1"
    assert saved[0]["session_id"] == "session-1"
    assert saved[0]["run_id"] == "run-1"
    assert saved[0]["registry_revision"] == 7
    assert saved[0]["tool_digest"] == "a" * 64
    assert saved[0]["provider_config_digest"] is None
    assert events[0]["type"] == "waiting_confirmation"
    assert events[0]["details"]["pending_action_id"] == "pending-1"
    assert "未执行" in result


def test_confirmation_without_run_binding_fails_closed():
    @tool("fixture_tool")
    async def inner(value: str) -> str:
        """Fixture tool."""
        return value

    set_current_user_id("user-1")
    result = _run(
        _wrapped(
            inner,
            requires_confirmation=True,
            definition_digest="a" * 64,
        ).ainvoke({"value": "x"})
    )

    assert "运行授权快照" in result


def test_confirmed_action_executes_inner_tool():
    calls = []

    @tool("fixture_tool")
    async def inner(value: str) -> str:
        """Fixture tool."""
        calls.append(value)
        return f"done:{value}"

    set_confirmed_action(True)
    result = _run(_wrapped(inner, requires_confirmation=True).ainvoke({"value": "x"}))

    assert result == "done:x"
    assert calls == ["x"]


def test_timeout_returns_safe_message_and_emits_tool_error():
    events = []

    @tool("fixture_tool")
    async def inner(value: str) -> str:
        """Fixture tool."""
        await asyncio.sleep(0.02)
        return value

    async def capture(event):
        events.append(event)

    set_thinking_callback(capture)
    result = _run(_wrapped(inner, timeout_seconds=0).ainvoke({"value": "x"}))

    assert "执行超时" in result
    assert events[0]["stage"] == "tool_error"
    assert events[0]["details"]["error"] == "timeout"


def test_output_is_truncated_after_successful_execution():
    @tool("fixture_tool")
    async def inner(value: str) -> str:
        """Fixture tool."""
        return value * 10

    result = _run(_wrapped(inner, max_output_chars=5).ainvoke({"value": "x"}))

    assert result.startswith("xxxxx")
    assert "输出已截断" in result
