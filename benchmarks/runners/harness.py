from __future__ import annotations

import asyncio
import contextlib
import json
import socket
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
CASE_SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "case.schema.json"
SUITE_CONFIG_PATH = REPO_ROOT / "benchmarks" / "suites.yaml"
for path in (str(REPO_ROOT), str(BACKEND_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.agent import streaming
from app.agent.tool_guard import GuardedTool
from app.services import agent_run_service

from benchmarks.runners.fake_factory import FakeAgentFactory
from benchmarks.runners.score_cases import score_case

_CASE_SCHEMA_VALIDATOR: Draft202012Validator | None = None
_SUITE_WEIGHTS: dict[str, dict[str, float]] | None = None


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


class FixtureAsyncSessionLocal:
    def __init__(self, counter: dict[str, int]):
        self.counter = counter

    def __call__(self):
        self.counter["sessions"] = self.counter.get("sessions", 0) + 1
        return self

    async def __aenter__(self):
        return SimpleNamespace()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FixtureMemoryService:
    def __init__(self, memories: list[dict]):
        self.memories = list(memories)

    async def get_today_memories(self, db, user_id: str) -> list[dict]:
        return [item for item in self.memories if item.get("status", "active") == "active"]

    async def list_memories(
        self,
        db,
        user_id: str,
        type: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        items = self.memories
        if type:
            items = [item for item in items if item.get("type") == type]
        if status:
            items = [item for item in items if item.get("status") == status]
        return list(items)

    async def get_memory_dict(self, db, user_id: str, memory_id: str) -> dict | None:
        return next((item for item in self.memories if item.get("id") == memory_id), None)


@contextlib.contextmanager
def offline_patches(case: dict):
    import app.agent.tool_guard as tool_guard
    import app.agent.tools.get_memory.tool as get_memory_tool_mod
    import app.agent.tools.list_memories.tool as list_memories_tool_mod
    import app.services as services_mod

    original_route_skills = agent_run_service.route_skills
    original_mcp_registry = agent_run_service.mcp_tool_registry
    original_session_manager = services_mod.database_session_manager
    original_save_pending_action = tool_guard.save_pending_action
    original_list_memories_session = list_memories_tool_mod.AsyncSessionLocal
    original_list_memories_service = list_memories_tool_mod.memory_service
    original_get_memory_session = get_memory_tool_mod.AsyncSessionLocal
    original_get_memory_service = get_memory_tool_mod.memory_service
    original_create_connection = socket.create_connection
    original_asyncio_open_connection = asyncio.open_connection

    async def fake_route_skills(query: str, candidates: list[str]) -> list[str]:
        explicit = (case.get("input") or {}).get("routed_skill_ids")
        if explicit is not None:
            return list(explicit)
        return list(candidates)

    class FakeMcpRegistry:
        async def ensure_fresh(self) -> bool:
            return False

    pending_counter = {"value": 0}
    pending_actions: list[dict] = []

    async def fake_save_pending_action(**kwargs):
        pending_counter["value"] += 1
        action_id = f"bench-pending-{pending_counter['value']}"
        pending_actions.append({"id": action_id, **kwargs})
        return action_id

    tool_data = (case.get("fixtures") or {}).get("tool_data") or {}
    memory_service = FixtureMemoryService(tool_data.get("memories") or [])
    session_counter: dict[str, int] = {}
    fixture_session_factory = FixtureAsyncSessionLocal(session_counter)

    routing_mode = (((case.get("fixtures") or {}).get("routing") or {}).get("mode") or "scripted")
    if routing_mode == "scripted":
        agent_run_service.route_skills = fake_route_skills
    agent_run_service.mcp_tool_registry = FakeMcpRegistry()
    services_mod.database_session_manager = InMemorySessionManager()
    tool_guard.save_pending_action = fake_save_pending_action
    list_memories_tool_mod.AsyncSessionLocal = fixture_session_factory
    list_memories_tool_mod.memory_service = memory_service
    get_memory_tool_mod.AsyncSessionLocal = fixture_session_factory
    get_memory_tool_mod.memory_service = memory_service

    fixture_state = (case.get("fixtures") or {}).get("state") or {}
    observation = {
        "created_messages": services_mod.database_session_manager.messages,
        "updated_messages": services_mod.database_session_manager.updated_messages,
        "pending_actions": pending_actions,
        "cross_user_accesses": list(fixture_state.get("cross_user_accesses") or []),
        "external_accesses": list(fixture_state.get("external_accesses") or []),
    }

    def blocked_create_connection(address, *args, **kwargs):
        observation["external_accesses"].append(str(address))
        raise RuntimeError(f"offline benchmark blocked external connection: {address}")

    async def blocked_open_connection(host=None, port=None, *args, **kwargs):
        address = f"{host}:{port}"
        observation["external_accesses"].append(address)
        raise RuntimeError(f"offline benchmark blocked external connection: {address}")

    socket.create_connection = blocked_create_connection
    asyncio.open_connection = blocked_open_connection

    try:
        yield observation
    finally:
        agent_run_service.route_skills = original_route_skills
        agent_run_service.mcp_tool_registry = original_mcp_registry
        services_mod.database_session_manager = original_session_manager
        tool_guard.save_pending_action = original_save_pending_action
        list_memories_tool_mod.AsyncSessionLocal = original_list_memories_session
        list_memories_tool_mod.memory_service = original_list_memories_service
        get_memory_tool_mod.AsyncSessionLocal = original_get_memory_session
        get_memory_tool_mod.memory_service = original_get_memory_service
        socket.create_connection = original_create_connection
        asyncio.open_connection = original_asyncio_open_connection


def load_cases(cases_dir: Path) -> list[dict]:
    cases: list[dict] = []
    case_ids: set[str] = set()
    suite_weights = _load_suite_weights()
    for path in sorted(cases_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{path} must contain a YAML mapping")
        unknown_top_level = sorted(set(data) - {"cases", "matrices"})
        if unknown_top_level:
            raise ValueError(f"{path} has unknown top-level fields: {', '.join(unknown_top_level)}")
        raw_cases_value = data.get("cases", [])
        if not isinstance(raw_cases_value, list):
            raise ValueError(f"{path} field 'cases' must be a list")
        raw_cases = list(raw_cases_value)
        raw_cases.extend(_expand_case_matrices(data.get("matrices", []), path))
        for case in raw_cases:
            validate_case(case, path)
            if case["id"] in case_ids:
                raise ValueError(f"duplicate benchmark case id: {case['id']}")
            case_ids.add(case["id"])
            if case.get("suite") in suite_weights:
                case["_suite_weights"] = suite_weights[case["suite"]]
            case["_case_file"] = str(path)
            cases.append(case)
    return cases


def _expand_case_matrices(raw_matrices: Any, path: Path) -> list[dict]:
    if not isinstance(raw_matrices, list):
        raise ValueError(f"{path} field 'matrices' must be a list")
    expanded: list[dict] = []
    for index, matrix in enumerate(raw_matrices):
        label = f"{path} matrices[{index}]"
        if not isinstance(matrix, dict):
            raise ValueError(f"{label} must be an object")
        unknown = sorted(set(matrix) - {"id_prefix", "defaults", "rows"})
        if unknown:
            raise ValueError(f"{label} has unknown fields: {', '.join(unknown)}")
        id_prefix = matrix.get("id_prefix")
        defaults = matrix.get("defaults")
        rows = matrix.get("rows")
        if not isinstance(id_prefix, str) or not id_prefix.strip():
            raise ValueError(f"{label}.id_prefix must be a non-empty string")
        if not isinstance(defaults, dict):
            raise ValueError(f"{label}.defaults must be an object")
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"{label}.rows must be a non-empty list")
        for row_index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"{label}.rows[{row_index}] must be an object")
            row_id = row.get("id")
            if not isinstance(row_id, str) or not row_id.strip():
                raise ValueError(f"{label}.rows[{row_index}].id must be a non-empty string")
            merged = _deep_merge(defaults, {key: value for key, value in row.items() if key != "id"})
            merged["id"] = f"{id_prefix}.{row_id}"
            expanded.append(merged)
    return expanded


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_suite_weights() -> dict[str, dict[str, float]]:
    global _SUITE_WEIGHTS
    if _SUITE_WEIGHTS is not None:
        return _SUITE_WEIGHTS
    if not SUITE_CONFIG_PATH.exists():
        _SUITE_WEIGHTS = {}
        return _SUITE_WEIGHTS

    data = yaml.safe_load(SUITE_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    suites = data.get("suites", {})
    if not isinstance(suites, dict):
        raise ValueError(f"{SUITE_CONFIG_PATH} field 'suites' must be an object")

    suite_weights: dict[str, dict[str, float]] = {}
    for suite, config in suites.items():
        if not isinstance(config, dict) or not isinstance(config.get("weights"), dict):
            raise ValueError(f"{SUITE_CONFIG_PATH} suite {suite} requires weights object")
        suite_weights[str(suite)] = _validate_weight_map(config["weights"], f"{SUITE_CONFIG_PATH} suite {suite}.weights")
    _SUITE_WEIGHTS = suite_weights
    return suite_weights


def _validate_weight_map(weights: dict, label: str) -> dict[str, float]:
    expected = {
        "must_include_score",
        "forbidden_content_score",
        "event_contract_score",
        "tool_policy_score",
        "stop_reason_score",
        "routing_contract_score",
        "state_contract_score",
        "efficiency_score",
    }
    unknown = sorted(set(weights) - expected)
    missing = sorted(expected - set(weights))
    if unknown:
        raise ValueError(f"{label} has unknown weight keys: {', '.join(unknown)}")
    if missing:
        raise ValueError(f"{label} missing weight keys: {', '.join(missing)}")

    normalized: dict[str, float] = {}
    for key, value in weights.items():
        if not isinstance(value, int | float) or value < 0:
            raise ValueError(f"{label}.{key} must be a non-negative number")
        normalized[key] = float(value)
    if sum(normalized.values()) <= 0:
        raise ValueError(f"{label} must contain at least one positive weight")
    return normalized


def _case_schema_validator() -> Draft202012Validator:
    global _CASE_SCHEMA_VALIDATOR
    if _CASE_SCHEMA_VALIDATOR is not None:
        return _CASE_SCHEMA_VALIDATOR
    schema = json.loads(CASE_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    _CASE_SCHEMA_VALIDATOR = Draft202012Validator(schema)
    return _CASE_SCHEMA_VALIDATOR


def validate_case(case: dict, path: Path | str = "<memory>") -> None:
    if not isinstance(case, dict):
        raise ValueError(f"{path} case must be an object")

    public_case = {key: value for key, value in case.items() if not key.startswith("_")}
    errors = sorted(_case_schema_validator().iter_errors(public_case), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "<case>"
        case_id = public_case.get("id", "<unknown>")
        raise ValueError(f"{path} case {case_id} invalid at {location}: {error.message}")


def select_cases(
    cases: list[dict],
    suite: str | None,
    case_id: str | None,
    offline_only: bool,
    include_negative: bool = False,
    *,
    mode: str | None = None,
    tag: str | None = None,
    variant: str | None = None,
) -> list[dict]:
    selected = []
    for case in cases:
        if case_id and case["id"] != case_id:
            continue
        if not include_negative and "negative" in case.get("tags", []):
            continue
        if suite:
            if suite == "smoke":
                if "smoke" not in case.get("tags", []):
                    continue
            elif case.get("suite") != suite:
                continue
        if offline_only and case.get("mode") != "offline":
            continue
        if mode and case.get("mode") != mode:
            continue
        if tag and tag not in case.get("tags", []):
            continue
        if variant and case.get("variant") != variant:
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
        with offline_patches(case) as state_observation:
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
        score = score_case(
            case,
            response_text,
            sse_events,
            prepared_tool_ids,
            prepared_skill_ids=plan.skill_ids,
            state_observation=state_observation,
        )
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
            "skill_ids": list(plan.skill_ids),
            "candidate_skill_ids": list(case["input"].get("skill_ids") or []),
            "tool_ids": prepared_tool_ids,
            "variant": case.get("variant"),
            "stop_reason": _stop_reason(sse_events),
            "errors": score.errors,
            "metrics": score.metrics,
            "flags": score.flags,
            "trace_path": str(trace_path),
            "repeat_index": repeat_index,
            "state_observation": state_observation,
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
            "candidate_skill_ids": list((case.get("input") or {}).get("skill_ids") or []),
            "tool_ids": [],
            "variant": case.get("variant"),
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
        if event["event_type"] == "response" and _has_visible_content(event.get("content")):
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


def _has_visible_content(content: Any) -> bool:
    return bool(str(content or "").strip())
