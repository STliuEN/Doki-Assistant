from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import BaseTool

from app.agent.factory import AgentFactory


@dataclass
class _Chunk:
    content: Any


class FakeExecutor:
    """Scripted AgentExecutor replacement used by offline benchmarks."""

    def __init__(self, events: list[dict], tools: list[BaseTool] | None = None):
        self._events = events
        self._tools_by_name = {tool.name: tool for tool in tools or []}
        self.executed_tools: list[str] = []

    async def astream_events(self, inputs: dict, version: str = "v2"):
        for raw_event in self._events:
            event = self._normalize_event(raw_event)
            if event.get("event") == "call_tool":
                async for tool_event in self._call_tool(event):
                    yield tool_event
            else:
                yield event

    def _normalize_event(self, event: dict) -> dict:
        normalized = dict(event)
        data = dict(normalized.get("data") or {})
        if normalized.get("event") == "on_chat_model_stream":
            data["chunk"] = _Chunk(data.get("chunk", ""))
        elif normalized.get("event") == "on_chat_model_end":
            data["output"] = _Chunk(data.get("output", ""))
        normalized["data"] = data
        return normalized

    async def _call_tool(self, event: dict):
        name = event.get("name")
        data = event.get("data") or {}
        tool_input = data.get("input") or {}
        yield {"event": "on_tool_start", "name": name, "data": {"input": tool_input}}

        tool = self._tools_by_name.get(name)
        if tool is None:
            yield {
                "event": "on_tool_error",
                "name": name,
                "data": {"error": f"script referenced unavailable tool: {name}"},
            }
            return

        try:
            output = await tool.ainvoke(tool_input)
            self.executed_tools.append(name)
            yield {"event": "on_tool_end", "name": name, "data": {"output": output}}
        except Exception as exc:
            yield {"event": "on_tool_error", "name": name, "data": {"error": str(exc)}}

        delay_ms = data.get("delay_ms")
        if isinstance(delay_ms, int) and delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000)


class FakeAgentFactory(AgentFactory):
    """AgentFactory that returns a scripted executor instead of a real LLM agent."""

    def __init__(self, script_events: list[dict], default_system_prompt: str = "benchmark system prompt"):
        super().__init__(
            default_tools=[],
            default_middleware=[],
            default_system_prompt=default_system_prompt,
        )
        self.script_events = script_events
        self.last_executor: FakeExecutor | None = None

    def create_agent_executor(
        self,
        custom_tools: list[BaseTool] | None = None,
        custom_model: str | None = None,
        model_config=None,
        custom_system_prompt: str | None = None,
        verbose: bool = True,
        return_intermediate_steps: bool = True,
        **kwargs,
    ) -> FakeExecutor:
        executor = FakeExecutor(self.script_events, custom_tools)
        self.last_executor = executor
        return executor
