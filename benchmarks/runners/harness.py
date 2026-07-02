from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
for path in (str(REPO_ROOT), str(BACKEND_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.agent import streaming
from app.agent.tool_guard import GuardedTool
from app.services import agent_run_service

from benchmarks.runners.fake_factory import FakeAgentFactory
from benchmarks.runners.score_cases import score_case


class InMemorySessionManager:
    def __init__(self):
        self.messages: list[dict] = []
        self.updated_messages: list[dict] = []

    @staticmethod
    def estimate_tokens(text: str) -> int:
        return max(1, len(text) // 2)

    def trim_history(self, history: list[tuple[str, str]], context_settings=None) -> list[tuple[str, str]]:
        return history

    def should_use_summary(self, history: list[tuple[str, str]], context_settings=None) -> bool:
        return False

    async def get_session(self, session_id: str, user_id: str) -> dict:
        return {"history": []}

    async def get_context(self, session_id: str, user_id: str, context_settings=None) -> list[tuple[str, str]]:
        return []

    async def get_context_with_summary(self, session_id: str, user_id: str, context_settings=None) -> dict:
        return {"summary": "", "history": [], "used_summary": False, "total_turns": 0}

    async def get_session_metadata(self, session_id: str, user_id: str) -> dict:
        return {}

    async def update_session_summary(
        self,
        session_id: str,
        user_id: str,
        summary: str,
        summary_message_id: int | None,
        estimated_tokens: int,
    ) -> None:
        return None

    async def add_message(self, session_id: str, user_id: str, user_message: str, assistant_message: str):
        self.messages.append({
            "session_id": session_id,
            "user_id": user_id,
            "user": user_message,
            "assistant": assistant_message,
        })

    async def get_regenerate_payload(self, session_id: str, user_id: str, assistant_message_id: int) -> dict:
        return {"query": "", "history": [], "message_id": assistant_message_id}

    async def update_message_content(self, session_id: str, user_id: str, message_id: int, content: str) -> dict:
        payload = {"id": message_id, "role": "assistant", "content": content}
        self.updated_messages.append(payload)
        return payload


@contextlib.contextmanager
def offline_patches(case: dict):
    import app.agent.tool_guard as tool_guard
    import app.services as services_mod

    original_route_skills = agent_run_service.route_skills
    original_mcp_registry = agent_run_service.mcp_tool_registry
    original_session_manager = services_mod.database_session_manager
    original_save_pending_action = tool_guard.save_pending_action

    async def fake_route_skills(query: str, candidates: list[str]) -> list[str]:
        explicit = (case.get("input") or {}).get("routed_skill_ids")
        if explicit is not None:
            return list(explicit)
        return list(candidates)

    class FakeMcpRegistry:
        async def ensure_fresh(self) -> bool:
            return False

    pending_counter = {"value": 0}

    async def fake_save_pending_action(**kwargs):
        pending_counter["value"] += 1
        return f"bench-pending-{pending_counter['value']}"

    agent_run_service.route_skills = fake_route_skills
    agent_run_service.mcp_tool_registry = FakeMcpRegistry()
    services_mod.database_session_manager = InMemorySessionManager()
    tool_guard.save_pending_action = fake_save_pending_action

    try:
        yield
    finally:
        agent_run_service.route_skills = original_route_skills
        agent_run_service.mcp_tool_registry = original_mcp_registry
        services_mod.database_session_manager = original_session_manager
        tool_guard.save_pending_action = original_save_pending_action


def load_cases(cases_dir: Path) -> list[dict]:
    cases: list[dict] = []
    for path in sorted(cases_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        raw_cases = data.get("cases", [])
        if not isinstance(raw_cases, list):
            raise ValueError(f"{path} field 'cases' must be a list")
        for case in raw_cases:
            validate_case(case, path)
            case["_case_file"] = str(path)
            cases.append(case)
    return cases


def validate_case(case: dict, path: Path | str = "<memory>") -> None:
    required = ["id", "suite", "title", "mode", "input", "fixtures", "expect", "tags"]
    missing = [field for field in required if field not in case]
    if missing:
        raise ValueError(f"{path} case missing required fields: {', '.join(missing)}")
    if case["mode"] not in {"offline", "online"}:
        raise ValueError(f"{path} case {case['id']} has unsupported mode: {case['mode']}")
    if not isinstance(case["input"], dict) or not case["input"].get("query"):
        raise ValueError(f"{path} case {case['id']} requires input.query")
    if not isinstance(case["fixtures"], dict) or not case["fixtures"].get("model_script"):
        raise ValueError(f"{path} case {case['id']} requires fixtures.model_script")
    if not isinstance(case["tags"], list):
        raise ValueError(f"{path} case {case['id']} requires tags list")


def select_cases(cases: list[dict], suite: str | None, case_id: str | None, offline_only: bool) -> list[dict]:
    selected = []
    for case in cases:
        if case_id and case["id"] != case_id:
            continue
        if suite:
            if suite == "smoke":
                if "smoke" not in case.get("tags", []):
                    continue
            elif case.get("suite") != suite:
                continue
        if offline_only and case.get("mode") != "offline":
            continue
        selected.append(case)
    return selected


async def run_case(case: dict, output_dir: Path, repeat_index: int = 0) -> dict:
    run_id = str(uuid4())
    session_id = f"bench-{run_id}"
    user_id = f"bench-{run_id}"
    start = time.monotonic()
    trace_events: list[dict] = []
    sse_events: list[dict] = []

    try:
        validate_case(case)
        script = _load_model_script(case)
        with offline_patches(case):
            input_data = case["input"]
            plan = await agent_run_service.prepare_agent_run(
                db=None,
                user_id=user_id,
                query=input_data["query"],
                model_config_id=input_data.get("model_config_id"),
                prompt_type=input_data.get("prompt_type"),
                skill_ids=input_data.get("skill_ids"),
                tool_ids=input_data.get("tool_ids"),
            )
            fake_factory = FakeAgentFactory(script, default_system_prompt=plan.system_prompt)
            async for chunk in streaming.get_agent_stream_response(
                input_data["query"],
                session_id,
                user_id,
                model_config=plan.model_config,
                custom_tools=plan.tools,
                context_settings=_namespace(input_data.get("context")),
                rag_retrieval_settings=_namespace(input_data.get("rag_retrieval")),
                factory=fake_factory,
                custom_system_prompt=plan.system_prompt,
            ):
                for event in _parse_sse_chunk(chunk):
                    sse_events.append(event)
                    trace_events.append(_to_trace_event(event, run_id, case["id"], session_id, start))

        response_text = "".join(event.get("content", "") for event in sse_events if event.get("type") == "response")
        prepared_tool_ids = [_tool_id(tool) for tool in plan.tools]
        score = score_case(case, response_text, sse_events, prepared_tool_ids)
        latency_ms = int((time.monotonic() - start) * 1000)
        trace_path = _write_trace(output_dir, run_id, trace_events)
        return {
            "run_id": run_id,
            "case_id": case["id"],
            "suite": case["suite"],
            "status": score.status,
            "score": score.score,
            "latency_ms": latency_ms,
            "first_non_empty_response_ms": _first_non_empty_response_ms(trace_events),
            "tool_calls": sum(1 for event in sse_events if event.get("stage") == "tool_start"),
            "model": "offline-scripted",
            "prompt_type": case["input"].get("prompt_type") or "main_prompt",
            "skill_ids": list(case["input"].get("skill_ids") or []),
            "tool_ids": prepared_tool_ids,
            "stop_reason": _stop_reason(sse_events),
            "errors": score.errors,
            "metrics": score.metrics,
            "flags": score.flags,
            "trace_path": str(trace_path),
            "repeat_index": repeat_index,
        }
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        trace_path = _write_trace(output_dir, run_id, trace_events)
        return {
            "run_id": run_id,
            "case_id": case.get("id", "<unknown>"),
            "suite": case.get("suite", "<unknown>"),
            "status": "error",
            "score": 0.0,
            "latency_ms": latency_ms,
            "first_non_empty_response_ms": _first_non_empty_response_ms(trace_events),
            "tool_calls": 0,
            "model": "offline-scripted",
            "prompt_type": (case.get("input") or {}).get("prompt_type") or "main_prompt",
            "skill_ids": list((case.get("input") or {}).get("skill_ids") or []),
            "tool_ids": [],
            "stop_reason": "error",
            "errors": [str(exc)],
            "metrics": {},
            "flags": ["error"],
            "trace_path": str(trace_path),
            "repeat_index": repeat_index,
        }


def run_case_sync(case: dict, output_dir: Path, repeat_index: int = 0) -> dict:
    return asyncio.run(run_case(case, output_dir, repeat_index))


def _load_model_script(case: dict) -> list[dict]:
    script_path = REPO_ROOT / "benchmarks" / case["fixtures"]["model_script"]
    data = json.loads(script_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{script_path} must contain a JSON event list")
    return data


def _parse_sse_chunk(chunk: str) -> list[dict]:
    events = []
    for line in chunk.splitlines():
        if not line.startswith("data: "):
            continue
        events.append(json.loads(line[len("data: "):]))
    return events


def _to_trace_event(event: dict, run_id: str, case_id: str, session_id: str, start: float) -> dict:
    details = event.get("details") or {}
    elapsed_ms = details.get("elapsed_ms")
    if elapsed_ms is None:
        elapsed_ms = int((time.monotonic() - start) * 1000)
    return {
        "run_id": run_id,
        "case_id": case_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_ms": elapsed_ms,
        "stage": event.get("stage") or event.get("type"),
        "event_type": event.get("type"),
        "tool": _normalize_tool_id(details.get("tool")),
        "duration_ms": details.get("duration_ms"),
        "input_preview": details.get("input_preview"),
        "output_preview": details.get("output_preview"),
        "error_type": details.get("error_type") or details.get("error"),
        "session_id": event.get("session_id") or details.get("session_id") or session_id,
        "content": event.get("content"),
    }


def _write_trace(output_dir: Path, run_id: str, trace_events: list[dict]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_path = output_dir / f"{run_id}.trace.jsonl"
    with trace_path.open("w", encoding="utf-8") as file:
        for event in trace_events:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")
    return trace_path


def _first_non_empty_response_ms(trace_events: list[dict]) -> int | None:
    for event in trace_events:
        if event["event_type"] == "response" and event.get("content"):
            return int(event["elapsed_ms"])
    return None


def _stop_reason(events: list[dict]) -> str:
    done = next((event for event in reversed(events) if event.get("type") == "thinking" and event.get("stage") == "done"), None)
    return (((done or {}).get("details") or {}).get("stop_reason")) or "completed"


def _namespace(value: Any):
    if value is None:
        return None
    if isinstance(value, dict):
        return SimpleNamespace(**{key: _namespace(item) for key, item in value.items()})
    if isinstance(value, list):
        return [_namespace(item) for item in value]
    return value


def _tool_id(tool) -> str:
    value = getattr(tool, "tool_id", None)
    if value:
        return value
    return _normalize_tool_id(getattr(tool, "name", ""))


def _normalize_tool_id(value: Any) -> str:
    if not value:
        return ""
    text = str(value)
    return text[:-5] if text.endswith("_tool") else text
