from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
for path in (str(REPO_ROOT), str(BACKEND_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

@contextlib.contextmanager
def _benchmark_file_logging(run_dir: Path):
    from app.core.logger_handler import DEFAULT_LOGGING_FORMAT, logger

    original_file_handlers = [
        handler for handler in logger.handlers if isinstance(handler, logging.FileHandler)
    ]
    for handler in original_file_handlers:
        logger.removeHandler(handler)

    run_dir.mkdir(parents=True, exist_ok=True)
    benchmark_handler = logging.FileHandler(run_dir / "benchmark.log", encoding="utf-8")
    benchmark_handler.setLevel(logging.DEBUG)
    benchmark_handler.setFormatter(DEFAULT_LOGGING_FORMAT)
    logger.addHandler(benchmark_handler)
    try:
        yield
    finally:
        logger.removeHandler(benchmark_handler)
        benchmark_handler.close()
        for handler in original_file_handlers:
            logger.addHandler(handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Doki assistant benchmarks.")
    parser.add_argument("--suite", help="Suite name, or 'smoke' to run smoke-tagged cases.")
    parser.add_argument("--case-id", help="Run exactly one case id.")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--offline", action="store_true", help="Only run offline cases.")
    parser.add_argument("--mode", choices=("offline", "integration", "online"))
    parser.add_argument("--tag", help="Only run cases containing this tag.")
    parser.add_argument("--variant", choices=("manual", "auto"))
    parser.add_argument("--include-negative", action="store_true", help="Include negative scorer fixtures.")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "benchmarks" / "results"))
    parser.add_argument("--fail-under", type=float, default=None)
    parser.add_argument("--fail-on-veto", action="store_true")
    args = parser.parse_args(argv)

    run_dir = Path(args.output_dir) / time.strftime("%Y%m%d-%H%M%S")
    original_log_dir = os.environ.get("DOKI_LOG_DIR")
    os.environ["DOKI_LOG_DIR"] = str(run_dir)
    try:
        from benchmarks.runners.harness import load_cases, run_case_sync, select_cases
        from benchmarks.runners.report_results import write_reports
    finally:
        if original_log_dir is None:
            os.environ.pop("DOKI_LOG_DIR", None)
        else:
            os.environ["DOKI_LOG_DIR"] = original_log_dir

    cases = load_cases(REPO_ROOT / "benchmarks" / "cases")
    mode = "offline" if args.offline else args.mode
    selected = select_cases(
        cases,
        args.suite,
        args.case_id,
        args.offline,
        include_negative=args.include_negative,
        mode=mode,
        tag=args.tag,
        variant=args.variant,
    )
    if not selected:
        print("No benchmark cases selected.", file=sys.stderr)
        return 2

    results = []
    with _benchmark_file_logging(run_dir):
        for repeat_index in range(max(1, args.repeat)):
            for case in selected:
                result = run_case_sync(case, run_dir, repeat_index=repeat_index)
                results.append(result)
                print(json.dumps({
                    "case_id": result["case_id"],
                    "status": result["status"],
                    "score": result["score"],
                    "latency_ms": result["latency_ms"],
                }, ensure_ascii=False))

    baseline_path = REPO_ROOT / "benchmarks" / "baselines" / "smoke.baseline.json"
    summary = write_reports(results, run_dir, baseline_path=baseline_path)
    print(f"Summary: {run_dir / 'summary.md'}")

    failed = [result for result in results if result["status"] not in {"passed", "skipped"}]
    vetoed = [result for result in results if any(flag.endswith("_veto") for flag in result.get("flags", []))]
    if args.fail_on_veto and vetoed:
        print(f"Benchmark hard-vetoed cases: {len(vetoed)}", file=sys.stderr)
        return 1
    if args.fail_under is not None and summary["average_score"] < args.fail_under:
        print(
            f"Benchmark average score {summary['average_score']} is below --fail-under {args.fail_under}",
            file=sys.stderr,
        )
        return 1
    if failed:
        print(f"Benchmark failed cases: {len(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
