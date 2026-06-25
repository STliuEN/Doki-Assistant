"""Agent 运行时单测：预算回退、事件泵 tool_depth 屏蔽、SSE 编排落库/超时取消。

不触真实 LLM：event_pump 用 fake executor 喂预设事件序列；
sse_driver 用 fake run_agent 闭包。contextvar 由 copy_context 隔离。
"""

from __future__ import annotations

import asyncio
import contextvars
import json

import pytest

from app.agent.runtime import budget as budget_mod
from app.agent.runtime.budget import DEFAULT_RUNTIME_BUDGET, get_runtime_budget
from app.agent.runtime.event_pump import stream_agent_events
from app.agent.runtime.sse_driver import drive_sse_stream, make_thinking_callback, new_run_id


def _run(coro):
    return contextvars.copy_context().run(asyncio.run, coro)


# ---------- budget ----------

def test_get_runtime_budget_missing_file(monkeypatch, tmp_path):
    # 指向不存在的 config 目录 → 全部回退默认
    monkeypatch.setattr(budget_mod, "__file__", str(tmp_path / "x" / "y" / "budget.py"))
    assert get_runtime_budget() == DEFAULT_RUNTIME_BUDGET


def test_get_runtime_budget_invalid_values(monkeypatch, tmp_path):
    cfg = tmp_path / "app" / "config"
    cfg.mkdir(parents=True)
    (cfg / "agent.yaml").write_text(
        "runtime:\n  max_iterations: -5\n  max_tool_calls: abc\n  max_runtime_seconds: 30\n",
        encoding="utf-8",
    )
    # __file__ 需位于 tmp_path/app/agent/runtime/budget.py，parents[2] = tmp_path/app
    fake = cfg.parent / "agent" / "runtime" / "budget.py"
    fake.parent.mkdir(parents=True)
    monkeypatch.setattr(budget_mod, "__file__", str(fake))
    b = get_runtime_budget()
    assert b["max_iterations"] == DEFAULT_RUNTIME_BUDGET["max_iterations"]  # 非法负值回退
    assert b["max_tool_calls"] == DEFAULT_RUNTIME_BUDGET["max_tool_calls"]  # 非 int 回退
    assert b["max_runtime_seconds"] == 30  # 合法值采用


# ---------- event_pump ----------


class _Chunk:
    def __init__(self, content):
        self.content = content


class _FakeExecutor:
    def __init__(self, events):
        self._events = events

    async def astream_events(self, inputs, version="v2"):
        for e in self._events:
            yield e


def test_stream_agent_events_masks_tool_internal_tokens():
    """工具区间内（tool_depth>0）的 on_chat_model_stream 不应进入 full_response。"""
    events = [
        {"event": "on_chat_model_stream", "data": {"chunk": _Chunk("外部1")}},
        {"event": "on_tool_start", "name": "rag", "data": {"input": {"q": 1}}},
        {"event": "on_chat_model_stream", "data": {"chunk": _Chunk("HyDE假设文档")}},  # 屏蔽
        {"event": "on_tool_end", "name": "rag", "data": {"output": "结果"}},
        {"event": "on_chat_model_stream", "data": {"chunk": _Chunk("外部2")}},
    ]
    queue: asyncio.Queue = asyncio.Queue()
    full: list[str] = []
    thinking_events: list[dict] = []

    async def cb(d):
        thinking_events.append(d)

    budget = dict(DEFAULT_RUNTIME_BUDGET)
    _run(stream_agent_events(_FakeExecutor(events), {}, queue, cb, full, budget))

    assert "".join(full) == "外部1外部2"  # 工具内部 token 被屏蔽
    stages = [e["stage"] for e in thinking_events]
    assert "tool_start" in stages and "tool_end" in stages
    start_evt = next(e for e in thinking_events if e["stage"] == "tool_start")
    assert start_evt["details"]["tool"] == "rag"
    assert start_evt["details"]["tool_call_index"] == 1


def test_stream_agent_events_non_streaming_fallback():
    """无流式增量但有 on_chat_model_end 完整输出时，应补发为 response。"""
    events = [
        {"event": "on_chat_model_end", "data": {"output": _Chunk("完整回答")}},
    ]
    queue: asyncio.Queue = asyncio.Queue()
    full: list[str] = []

    async def cb(d):
        pass

    _run(stream_agent_events(_FakeExecutor(events), {}, queue, cb, full, dict(DEFAULT_RUNTIME_BUDGET)))
    assert "".join(full) == "完整回答"


# ---------- sse_driver ----------


def _parse_sse(chunks: list[str]) -> list[dict]:
    out = []
    for c in chunks:
        line = c.strip()
        assert line.startswith("data: ")
        out.append(json.loads(line[len("data: "):]))
    return out


async def _collect(agen) -> list[str]:
    return [item async for item in agen]


def test_drive_sse_stream_success_calls_on_success():
    """正常完成：on_success 收到最终文本，末尾 done 带 session_id。"""
    queue: asyncio.Queue = asyncio.Queue()
    full: list[str] = []
    holder = {"response": None, "error": None, "stop_reason": "completed", "run_id": "r1"}
    saved: list[str] = []

    async def run_agent():
        await queue.put({"type": "response", "content": "答"})
        full.append("答")
        holder["response"] = "答"

    async def on_success(resp):
        saved.append(resp)

    async def go():
        return await _collect(drive_sse_stream(
            "sess-1", run_agent, queue, holder, full,
            dict(DEFAULT_RUNTIME_BUDGET), __import__("time").monotonic(),
            on_success=on_success,
        ))

    events = _parse_sse(_run(go()))
    assert saved == ["答"]
    done = events[-1]
    assert done["type"] == "done" and done["session_id"] == "sess-1"


def test_drive_sse_stream_timeout_cancels_and_persists_partial():
    """超时：发 stopped 事件，取消补发文本带 session_id，partial 落库。"""
    queue: asyncio.Queue = asyncio.Queue()
    full: list[str] = []
    holder = {"response": None, "error": None, "stop_reason": "completed", "run_id": "r2"}
    saved: list[str] = []

    async def run_agent():
        full.append("部分")
        await asyncio.sleep(5)  # 超过预算，必被取消

    async def on_success(resp):
        saved.append(resp)

    budget = dict(DEFAULT_RUNTIME_BUDGET)
    budget["max_runtime_seconds"] = 0.05  # 给 run_agent 一次调度机会后即超时

    async def go():
        return await _collect(drive_sse_stream(
            "sess-2", run_agent, queue, holder, full,
            budget, __import__("time").monotonic(),
            on_success=on_success,
        ))

    events = _parse_sse(_run(go()))
    assert holder["stop_reason"] == "timeout"
    # 取消补发的 response 事件必须带 session_id（统一后的行为）
    cancel_evt = next(e for e in events if e["type"] == "response" and "已停止" in e.get("content", ""))
    assert cancel_evt["session_id"] == "sess-2"
    assert saved and saved[0].startswith("部分")
