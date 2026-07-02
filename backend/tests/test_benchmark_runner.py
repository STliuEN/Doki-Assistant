from __future__ import annotations

import contextvars

from benchmarks.runners.harness import REPO_ROOT, load_cases, run_case_sync, select_cases


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


def test_benchmark_runner_negative_case_fails_without_error(tmp_path):
    cases = load_cases(REPO_ROOT / "benchmarks" / "cases")
    selected = select_cases(cases, suite=None, case_id="agent_basic.must_not_include_001", offline_only=True)
    assert len(selected) == 1

    result = _run_case(selected[0], tmp_path)

    assert result["status"] == "failed"
    assert result["score"] == 0.0
    assert any("forbidden content" in error for error in result["errors"])
