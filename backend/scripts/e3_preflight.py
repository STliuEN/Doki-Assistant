from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Import after the direct-execution path bootstrap.
# ruff: noqa: E402
from app.db.e3_guard import issue_e3_preflight_record


async def _run(args: argparse.Namespace) -> None:
    record = await issue_e3_preflight_record(
        database_url=args.database_url,
        approval_token=args.approval_token,
        purposes=args.purposes,
        issuance_switch=args.issuance_switch,
        lifetime_seconds=args.lifetime_seconds,
    )
    destination = Path(args.output).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(destination), "target": record["target"], "purposes": record["purposes"]}))


def main() -> None:
    parser = argparse.ArgumentParser(description="Issue a short-lived E3 MySQL preflight record")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--approval-token", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--purposes", nargs="+", default=["migrate", "runtime", "import", "restore-forward"])
    parser.add_argument("--issuance-switch", required=True)
    parser.add_argument("--lifetime-seconds", default=900, type=int)
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
