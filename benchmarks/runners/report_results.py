from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import median, pstdev


def write_reports(results: list[dict], output_dir: Path, baseline_path: Path | None = None) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    baseline = _load_baseline(baseline_path)
    summary = _build_summary(results, baseline)

    summary_json = output_dir / "summary.json"
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_md = output_dir / "summary.md"
    summary_md.write_text(_render_markdown(summary), encoding="utf-8")
    return summary


def _load_baseline(path: Path | None) -> dict:
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _build_summary(results: list[dict], baseline: dict) -> dict:
    passed = sum(1 for result in results if result["status"] == "passed")
    failed = sum(1 for result in results if result["status"] == "failed")
    errored = sum(1 for result in results if result["status"] == "error")
    scores = [float(result["score"]) for result in results]
    latencies = [int(result["latency_ms"]) for result in results]
    first_response_values = [
        int(result["first_non_empty_response_ms"])
        for result in results
        if result.get("first_non_empty_response_ms") is not None
    ]
    baseline_cases = baseline.get("cases") or {}

    cases = []
    for result in results:
        base = baseline_cases.get(result["case_id"]) or {}
        score_delta = None
        if "score" in base:
            score_delta = round(float(result["score"]) - float(base["score"]), 4)
        cases.append({**result, "baseline_score": base.get("score"), "score_delta": score_delta})

    return {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "error": errored,
        "average_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "score_stdev": round(pstdev(scores), 4) if len(scores) > 1 else 0.0,
        "hard_vetoes": sum(
            1 for result in results
            if any(str(flag).endswith("_veto") for flag in result.get("flags", []))
        ),
        "latency_ms": _distribution(latencies),
        "first_non_empty_response_ms": _distribution(first_response_values),
        "groups": _group_metrics(results),
        "cases": cases,
    }


def _distribution(values: list[int]) -> dict:
    if not values:
        return {"p50": None, "p95": None, "mean": None}
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * 0.95) - 1))
    return {
        "p50": int(median(ordered)),
        "p95": ordered[p95_index],
        "mean": round(sum(ordered) / len(ordered), 2),
    }


def _group_metrics(results: list[dict]) -> dict:
    groups: dict[str, list[dict]] = {}
    for result in results:
        groups.setdefault(str(result.get("suite") or "unknown"), []).append(result)
    return {
        name: {
            "total": len(items),
            "passed": sum(1 for item in items if item.get("status") == "passed"),
            "average_score": round(sum(float(item.get("score", 0.0)) for item in items) / len(items), 4),
            "routing_f1": round(
                sum(float((item.get("metrics") or {}).get("routing_f1", 1.0)) for item in items) / len(items),
                4,
            ),
        }
        for name, items in sorted(groups.items())
    }


def _render_markdown(summary: dict) -> str:
    lines = [
        "# Benchmark Summary",
        "",
        f"- Total: {summary['total']}",
        f"- Passed: {summary['passed']}",
        f"- Failed: {summary['failed']}",
        f"- Error: {summary['error']}",
        f"- Average score: {summary['average_score']}",
        f"- Hard vetoes: {summary['hard_vetoes']}",
        f"- Latency p50/p95: {summary['latency_ms']['p50']} / {summary['latency_ms']['p95']} ms",
        f"- First response p50/p95: {summary['first_non_empty_response_ms']['p50']} / {summary['first_non_empty_response_ms']['p95']} ms",
        "",
        "| Suite | Total | Passed | Average | Routing F1 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for suite, metrics in summary["groups"].items():
        lines.append(
            f"| {suite} | {metrics['total']} | {metrics['passed']} | "
            f"{metrics['average_score']} | {metrics['routing_f1']} |"
        )
    lines.extend([
        "",
        "| Case | Status | Score | Delta | Flags | Errors |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ])
    for case in summary["cases"]:
        errors = "<br>".join(case.get("errors") or [])
        flags = ", ".join(case.get("flags") or [])
        delta = "" if case.get("score_delta") is None else case["score_delta"]
        lines.append(
            f"| {case['case_id']} | {case['status']} | {case['score']} | {delta} | {flags} | {errors} |"
        )
    lines.append("")
    return "\n".join(lines)
