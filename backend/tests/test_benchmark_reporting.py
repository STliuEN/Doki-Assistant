from __future__ import annotations

import json

from benchmarks.runners.report_results import _build_summary, write_reports


def _result(case_id, *, suite="agent_basic", score=1.0, status="passed", latency=10, first=5, flags=None, f1=1.0):
    return {
        "run_id": f"run-{case_id}",
        "case_id": case_id,
        "suite": suite,
        "status": status,
        "score": score,
        "latency_ms": latency,
        "first_non_empty_response_ms": first,
        "tool_calls": 0,
        "stop_reason": "completed",
        "errors": [],
        "flags": flags or [],
        "metrics": {"routing_f1": f1},
        "trace_path": f"{case_id}.jsonl",
    }


def test_summary_reports_latency_distribution_and_suite_groups():
    summary = _build_summary([
        _result("a", latency=10, first=2, f1=1.0),
        _result("b", latency=30, first=6, f1=0.5),
    ], {})

    assert summary["latency_ms"] == {"p50": 20, "p95": 30, "mean": 20.0}
    assert summary["first_non_empty_response_ms"]["p50"] == 4
    assert summary["groups"]["agent_basic"]["routing_f1"] == 0.75


def test_summary_counts_hard_veto_flags():
    summary = _build_summary([
        _result("safe"),
        _result("unsafe", status="failed", score=0.0, flags=["safety_veto"]),
    ], {})

    assert summary["hard_vetoes"] == 1
    assert summary["failed"] == 1


def test_write_reports_emits_json_and_markdown(tmp_path):
    summary = write_reports([_result("a")], tmp_path)

    assert json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))["total"] == 1
    markdown = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "Hard vetoes: 0" in markdown
    assert "| agent_basic | 1 | 1 |" in markdown
    assert summary["total"] == 1
