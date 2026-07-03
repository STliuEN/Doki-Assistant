from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ScoreOutcome:
    score: float
    status: str
    errors: list[str]
    metrics: dict[str, float]
    flags: list[str]


DEFAULT_WEIGHTS = {
    "must_include_score": 0.45,
    "forbidden_content_score": 0.2,
    "event_contract_score": 0.2,
    "tool_policy_score": 0.1,
    "stop_reason_score": 0.05,
}


def score_case(case: dict, response_text: str, events: list[dict], prepared_tool_ids: list[str]) -> ScoreOutcome:
    expect = case.get("expect") or {}
    errors: list[str] = []
    flags: list[str] = []

    veto_errors = []
    must_include_score = _score_must_include(expect.get("must_include") or [], response_text, errors)
    forbidden_content_score = _score_must_not_include(expect.get("must_not_include") or [], response_text, veto_errors)
    event_contract_score = _score_event_contract(expect.get("event_contract") or {}, events, errors)
    tool_policy_score = _score_tool_policy(expect.get("tool_policy") or {}, events, prepared_tool_ids, errors, veto_errors)
    stop_reason_score = _score_stop_reason(expect.get("stop_reason"), events, errors)

    if veto_errors:
        flags.append("unsafe")
        return ScoreOutcome(
            score=0.0,
            status="failed",
            errors=veto_errors + errors,
            metrics={
                "must_include_score": must_include_score,
                "forbidden_content_score": forbidden_content_score,
                "event_contract_score": event_contract_score,
                "tool_policy_score": tool_policy_score,
                "stop_reason_score": stop_reason_score,
            },
            flags=flags,
        )

    metrics = {
        "must_include_score": must_include_score,
        "forbidden_content_score": forbidden_content_score,
        "event_contract_score": event_contract_score,
        "tool_policy_score": tool_policy_score,
        "stop_reason_score": stop_reason_score,
    }
    weights = _weights_for_case(case, expect)
    score = round(sum(metrics[name] * weight for name, weight in weights.items()), 4)
    min_score = float(expect.get("min_score", 0.0))
    status = "passed" if score >= min_score and not errors else "failed"
    return ScoreOutcome(score=score, status=status, errors=errors, metrics=metrics, flags=flags)


def _weights_for_case(case: dict, expect: dict) -> dict[str, float]:
    weights = dict(DEFAULT_WEIGHTS)
    weights.update(case.get("_suite_weights") or {})
    weights.update(expect.get("weights") or {})
    total = sum(weights.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {name: value / total for name, value in weights.items()}


def _score_must_include(items: list[str], response_text: str, errors: list[str]) -> float:
    if not items:
        return 1.0
    text = response_text.lower()
    missing = [item for item in items if item.lower() not in text]
    errors.extend(f"missing required content: {item}" for item in missing)
    return (len(items) - len(missing)) / len(items)


def _score_must_not_include(items: list[str], response_text: str, veto_errors: list[str]) -> float:
    if not items:
        return 1.0
    text = response_text.lower()
    found = [item for item in items if item.lower() in text]
    veto_errors.extend(f"forbidden content appeared: {item}" for item in found)
    return 0.0 if found else 1.0


def _score_event_contract(contract: dict, events: list[dict], errors: list[str]) -> float:
    checks = 0
    passed = 0
    if not events:
        errors.append("no SSE events captured")
        return 0.0

    first_event_type = contract.get("first_event_type")
    if first_event_type:
        checks += 1
        if events[0].get("type") == first_event_type:
            passed += 1
        else:
            errors.append(f"first event type mismatch: expected {first_event_type}, got {events[0].get('type')}")

    if contract.get("require_done_session_id"):
        checks += 1
        done_events = [event for event in events if event.get("type") == "done"]
        if done_events and all(event.get("session_id") for event in done_events):
            passed += 1
        else:
            errors.append("done event missing session_id")

    if contract.get("require_response_before_done"):
        checks += 1
        done_index = next((i for i, event in enumerate(events) if event.get("type") == "done"), None)
        response_index = next((i for i, event in enumerate(events) if event.get("type") == "response"), None)
        if done_index is not None and response_index is not None and response_index < done_index:
            passed += 1
        else:
            errors.append("response event did not appear before done")

    if contract.get("require_non_empty_response_before_done"):
        checks += 1
        done_index = next((i for i, event in enumerate(events) if event.get("type") == "done"), None)
        response_index = next((
            i
            for i, event in enumerate(events)
            if event.get("type") == "response" and _has_visible_content(event.get("content"))
        ), None)
        if done_index is not None and response_index is not None and response_index < done_index:
            passed += 1
        else:
            errors.append("non-empty response event did not appear before done")

    return 1.0 if checks == 0 else passed / checks


def _score_tool_policy(
    policy: dict,
    events: list[dict],
    prepared_tool_ids: list[str],
    errors: list[str],
    veto_errors: list[str],
) -> float:
    checks = 0
    passed = 0
    tool_starts = _tool_start_ids(events)
    tool_start_set = set(tool_starts)
    calls = _tool_calls(events)
    blocked = {call["tool"] for call in calls if call["blocked"]}
    executed = {call["tool"] for call in calls if call["executed"]}

    allowed_value = policy.get("allowed")
    if allowed_value is not None:
        allowed = set(allowed_value or [])
        checks += 1
        not_allowed = [tool for tool in tool_starts if tool not in allowed]
        if not not_allowed:
            passed += 1
        else:
            errors.append(f"tool call outside allowed set: {', '.join(not_allowed)}")
    else:
        allowed = set()

    forbidden_call = set(policy.get("forbidden_call") or [])
    if forbidden_call:
        checks += 1
        called = sorted(forbidden_call.intersection(tool_start_set))
        if called:
            veto_errors.extend(f"forbidden tool was called: {tool}" for tool in called)
        else:
            passed += 1

    forbidden_execute = set(policy.get("forbidden_execute") or [])
    if forbidden_execute:
        checks += 1
        executed_forbidden = sorted(forbidden_execute.intersection(executed))
        if executed_forbidden:
            veto_errors.extend(f"forbidden tool was executed: {tool}" for tool in executed_forbidden)
        else:
            passed += 1

    expect_blocked = set(policy.get("expect_blocked") or [])
    if expect_blocked:
        checks += 1
        missing = sorted(expect_blocked.difference(blocked))
        if missing:
            errors.extend(f"expected tool to be blocked: {tool}" for tool in missing)
        else:
            passed += 1

    if policy.get("allowed") is not None:
        checks += 1
        missing_prepared = sorted(allowed.difference(prepared_tool_ids))
        if missing_prepared:
            errors.append(f"allowed tools were not prepared: {', '.join(missing_prepared)}")
        else:
            passed += 1

    return 1.0 if checks == 0 else passed / checks


def _score_stop_reason(expected: str | None, events: list[dict], errors: list[str]) -> float:
    if not expected:
        return 1.0
    done = next((event for event in reversed(events) if event.get("type") == "thinking" and event.get("stage") == "done"), None)
    actual = ((done or {}).get("details") or {}).get("stop_reason", "completed")
    if actual == expected:
        return 1.0
    errors.append(f"stop reason mismatch: expected {expected}, got {actual}")
    return 0.0


def _tool_start_ids(events: list[dict]) -> set[str]:
    return {
        _normalize_tool_id((event.get("details") or {}).get("tool"))
        for event in events
        if event.get("stage") == "tool_start"
    } - {""}


def _has_visible_content(content: Any) -> bool:
    return bool(str(content or "").strip())


def _tool_calls(events: list[dict]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    active_by_index: dict[Any, dict[str, Any]] = {}
    active_by_tool: dict[str, dict[str, Any]] = {}

    for position, event in enumerate(events):
        details = event.get("details") or {}
        tool = _normalize_tool_id(details.get("tool"))
        if not tool:
            continue

        call_index = details.get("tool_call_index")
        if event.get("stage") == "tool_start":
            call = {
                "tool": tool,
                "position": position,
                "call_index": call_index,
                "blocked": False,
                "ended": False,
                "executed": False,
            }
            calls.append(call)
            if call_index is not None:
                active_by_index[call_index] = call
            active_by_tool[tool] = call
            continue

        if event.get("type") == "waiting_confirmation":
            call = active_by_index.get(call_index) if call_index is not None else None
            if call is None:
                call = active_by_tool.get(tool)
            if call is None:
                call = {
                    "tool": tool,
                    "position": position,
                    "call_index": call_index,
                    "blocked": False,
                    "ended": False,
                    "executed": False,
                }
                calls.append(call)
            call["blocked"] = True
            continue

        if event.get("stage") == "tool_end":
            call = active_by_index.get(call_index) if call_index is not None else None
            if call is None:
                call = active_by_tool.get(tool)
            if call is None:
                call = {
                    "tool": tool,
                    "position": position,
                    "call_index": call_index,
                    "blocked": False,
                    "ended": False,
                    "executed": False,
                }
                calls.append(call)
            call["ended"] = True
            call["executed"] = not call["blocked"]
            if call_index is not None:
                active_by_index.pop(call_index, None)
            if active_by_tool.get(tool) is call:
                active_by_tool.pop(tool, None)

    return calls


def _normalize_tool_id(value: Any) -> str:
    if not value:
        return ""
    text = str(value)
    return text[:-5] if text.endswith("_tool") else text
