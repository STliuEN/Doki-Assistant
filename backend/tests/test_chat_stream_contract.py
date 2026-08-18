from __future__ import annotations

import asyncio
import json
import time

from app.agent.runtime.budget import DEFAULT_RUNTIME_BUDGET
from app.agent.runtime.sse_driver import drive_sse_stream
from app.schemas.sse import SSE_SCHEMA_VERSION


def _run(coro):
    return asyncio.run(coro)


async def _collect(agen) -> list[str]:
    return [item async for item in agen]


def _parse_sse(chunks: list[str]) -> list[dict]:
    events = []
    for chunk in chunks:
        for line in chunk.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    return events


def test_done_has_session_id_on_agent_error():
    queue: asyncio.Queue = asyncio.Queue()
    holder = {"response": None, "error": None, "stop_reason": "completed", "run_id": "r-error"}

    async def run_agent():
        holder["error"] = "boom"

    async def on_success(response):
        raise AssertionError("on_success should not run for error responses")

    async def go():
        return await _collect(drive_sse_stream(
            "sess-error",
            run_agent,
            queue,
            holder,
            [],
            dict(DEFAULT_RUNTIME_BUDGET),
            time.monotonic(),
            on_success=on_success,
        ))

    events = _parse_sse(_run(go()))
    assert events[-1] == {
        "schema_version": SSE_SCHEMA_VERSION,
        "type": "done",
        "session_id": "sess-error",
    }


def test_done_has_session_id_on_driver_exception():
    queue: asyncio.Queue = asyncio.Queue()
    holder = {"response": "answer", "error": None, "stop_reason": "completed", "run_id": "r-driver-error"}

    async def run_agent():
        return None

    async def on_success(response):
        raise RuntimeError("persist failed")

    async def go():
        return await _collect(drive_sse_stream(
            "sess-driver-error",
            run_agent,
            queue,
            holder,
            ["answer"],
            dict(DEFAULT_RUNTIME_BUDGET),
            time.monotonic(),
            on_success=on_success,
        ))

    events = _parse_sse(_run(go()))
    assert events[-2]["type"] == "error"
    assert events[-1] == {
        "schema_version": SSE_SCHEMA_VERSION,
        "type": "done",
        "session_id": "sess-driver-error",
    }
