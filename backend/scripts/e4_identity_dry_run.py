"""Run the explicit, read-only E4 identity mapping dry-run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.e4.identity import IdentityDryRunError, build_identity_dry_run, write_identity_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a redacted, offline-only E4 identity dry-run report")
    parser.add_argument("--input", required=True, type=Path, help="Explicit JSON source snapshot")
    parser.add_argument("--output", required=True, type=Path, help="New JSON report path")
    args = parser.parse_args(argv)
    try:
        report = build_identity_dry_run(args.input)
        destination = write_identity_report(report, args.output)
    except (IdentityDryRunError, OSError, ValueError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {
                "blocked": report.blocked,
                "output": str(destination),
                "report_sha256": report.report_sha256,
                "counts": dict(report.counts),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 2 if report.blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
