from __future__ import annotations

import json
from pathlib import Path
from statistics import pstdev


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
        "cases": cases,
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
        "",
        "| Case | Status | Score | Delta | Flags | Errors |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for case in summary["cases"]:
        errors = "<br>".join(case.get("errors") or [])
        flags = ", ".join(case.get("flags") or [])
        delta = "" if case.get("score_delta") is None else case["score_delta"]
        lines.append(
            f"| {case['case_id']} | {case['status']} | {case['score']} | {delta} | {flags} | {errors} |"
        )
    lines.append("")
    return "\n".join(lines)
