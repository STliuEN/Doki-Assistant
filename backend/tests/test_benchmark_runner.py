from __future__ import annotations

import contextvars

import pytest

from benchmarks.runners.harness import (
    REPO_ROOT,
    _first_non_empty_response_ms,
    load_cases,
    run_case_sync,
    select_cases,
    validate_case,
)


def _run_case(case, output_dir):
    return contextvars.copy_context().run(run_case_sync, case, output_dir)


def test_benchmark_runner_runs_single_offline_case(tmp_path):
    cases = load_cases(REPO_ROOT / "benchmarks" / "cases")
    selected = select_cases(cases, suite=None, case_id="agent_basic.plain_text_001", offline_only=True)
    assert len(selected) == 1

    result = _run_case(selected[0], tmp_path)

    assert result["status"] == "passed"
    assert result["score"] >= 0.9
    assert result["trace_path"]
    assert result["first_non_empty_response_ms"] is not None


def test_benchmark_runner_uses_fixture_backed_memory_tool(tmp_path, monkeypatch):
    import app.agent.tools.list_memories.tool as list_memories_tool_mod

    class ForbiddenAsyncSessionLocal:
        def __call__(self):
            raise AssertionError("real AsyncSessionLocal should not be used by smoke benchmark")

    monkeypatch.setattr(list_memories_tool_mod, "AsyncSessionLocal", ForbiddenAsyncSessionLocal())
    cases = load_cases(REPO_ROOT / "benchmarks" / "cases")
    selected = select_cases(cases, suite=None, case_id="skill_routing.explicit_tool_ids_001", offline_only=True)
    assert len(selected) == 1

    result = _run_case(selected[0], tmp_path)

    assert result["status"] == "passed"
    assert result["tool_calls"] == 1
    assert result["score"] >= 0.9


def test_benchmark_runner_negative_case_fails_without_error(tmp_path):
    cases = load_cases(REPO_ROOT / "benchmarks" / "cases")
    selected = select_cases(
        cases,
        suite=None,
        case_id="agent_basic.must_not_include_001",
        offline_only=True,
        include_negative=True,
    )
    assert len(selected) == 1

    result = _run_case(selected[0], tmp_path)

    assert result["status"] == "failed"
    assert result["score"] == 0.0
    assert any("forbidden content" in error for error in result["errors"])


def test_benchmark_runner_excludes_negative_cases_by_default():
    cases = load_cases(REPO_ROOT / "benchmarks" / "cases")

    selected = select_cases(cases, suite=None, case_id=None, offline_only=True)

    assert selected
    assert all("negative" not in case.get("tags", []) for case in selected)
    assert "agent_basic.must_not_include_001" not in {case["id"] for case in selected}


def test_benchmark_runner_can_include_negative_cases():
    cases = load_cases(REPO_ROOT / "benchmarks" / "cases")

    selected = select_cases(cases, suite=None, case_id=None, offline_only=True, include_negative=True)

    assert "agent_basic.must_not_include_001" in {case["id"] for case in selected}


def test_benchmark_case_schema_rejects_unknown_tool_policy_key():
    case = _valid_case()
    case["expect"]["tool_policy"] = {
        "allowed": [],
        "forbidden": ["delete_memory"],
    }

    with pytest.raises(ValueError, match="expect.tool_policy"):
        validate_case(case)


def test_benchmark_case_schema_rejects_unknown_event_contract_key():
    case = _valid_case()
    case["expect"]["event_contract"] = {
        "require_done_session_id": True,
        "require_done_session": True,
    }

    with pytest.raises(ValueError, match="expect.event_contract"):
        validate_case(case)


def test_benchmark_case_schema_rejects_empty_query_and_script_path():
    empty_query = _valid_case()
    empty_query["input"]["query"] = ""
    with pytest.raises(ValueError, match="input.query"):
        validate_case(empty_query)

    empty_script = _valid_case()
    empty_script["fixtures"]["model_script"] = ""
    with pytest.raises(ValueError, match="fixtures.model_script"):
        validate_case(empty_script)


def test_first_non_empty_response_ms_ignores_whitespace_content():
    events = [
        {"event_type": "response", "content": " \n\t", "elapsed_ms": 10},
        {"event_type": "response", "content": "visible", "elapsed_ms": 25},
    ]

    assert _first_non_empty_response_ms(events) == 25


def _valid_case():
    return {
        "id": "agent_basic.invalid_policy_001",
        "suite": "agent_basic",
        "title": "Invalid policy field",
        "mode": "offline",
        "input": {"query": "hello"},
        "fixtures": {"model_script": "fixtures/scripts/agent_basic_plain_text_001.json"},
        "expect": {
            "tool_policy": {
                "allowed": [],
                "forbidden_call": [],
            }
        },
        "tags": ["smoke"],
    }
