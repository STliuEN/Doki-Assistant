"""Issue an E4 identity preflight using explicit process-bound credentials."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine


async def _run(args: argparse.Namespace) -> dict[str, object]:
    from app.db import e4_guard

    values = {name: os.environ[name] for name in e4_guard.E4_ENVIRONMENT_NAMES if name in os.environ}
    required = ("E4_DATABASE_URL", "E4_ALLOWLIST_FILE", "E4_CREDENTIAL_REF", "E4_TARGET_ID")
    if any(not values.get(name, "").strip() for name in required):
        raise e4_guard.E4GuardError("Explicit E4 database URL, allowlist, credential reference and target ID are required")
    allowlist_path = Path(values["E4_ALLOWLIST_FILE"]).resolve()
    if not allowlist_path.is_file():
        raise e4_guard.E4GuardError("The explicit E4 allowlist file must exist")
    if args.output.is_symlink():
        raise e4_guard.E4GuardError("E4 preflight output must not be a symbolic link")
    destination = args.output.resolve()
    if destination.exists() or not destination.parent.is_dir():
        raise e4_guard.E4GuardError("E4 preflight requires a new output file in an existing directory")
    database_url = values["E4_DATABASE_URL"]

    async def inspect_target(target):
        engine = create_async_engine(
            database_url,
            pool_size=1,
            max_overflow=0,
            echo=False,
            hide_parameters=True,
            connect_args={"connect_timeout": 10},
        )
        try:
            async with asyncio.timeout(20):
                async with engine.connect() as connection:
                    return await connection.run_sync(e4_guard.inspect_database_identity, target)
        finally:
            await engine.dispose()

    record = await e4_guard.issue_e4_preflight_record(
        database_url=database_url,
        allowlist=allowlist_path,
        credential_ref=values["E4_CREDENTIAL_REF"],
        target_id=values["E4_TARGET_ID"],
        approval_token=values.get("E4_APPROVAL_TOKEN") or None,
        migration_switch=values.get("E4_MIGRATION_ENABLED"),
        issuance_switch=args.issuance_switch,
        purposes=args.purposes,
        lifetime_seconds=args.lifetime_seconds,
        container_inspector=e4_guard.inspect_e4_container,
        database_inspector=inspect_target,
    )
    serialized = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with destination.open("x", encoding="utf-8") as stream:
        stream.write(serialized)
    return {
        "blocked": False,
        "output": str(destination),
        "target_id": record["target"]["id"],
        "purposes": record["purposes"],
        "expires_at": record["expires_at"],
        "scope": "resource-identity-only",
    }


def _parser() -> argparse.ArgumentParser:
    from app.db.e4_guard import E4_PREFLIGHT_MAX_LIFETIME_SECONDS

    parser = argparse.ArgumentParser(description="Issue a read-only E4 resource identity preflight without loading dotenv")
    parser.add_argument("--output", required=True, type=Path, help="New evidence file; parent directory must already exist")
    parser.add_argument("--purposes", nargs="+", required=True, help="Explicit role-bound purposes; no default write authorization")
    parser.add_argument("--issuance-switch", required=True)
    parser.add_argument("--lifetime-seconds", type=int, default=E4_PREFLIGHT_MAX_LIFETIME_SECONDS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = asyncio.run(_run(args))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "blocked": True,
                    "error": type(exc).__name__,
                    "message": "E4 preflight failed; check explicit inputs, role, identity, container health and output location.",
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    backend_root = str(Path(__file__).resolve().parents[1])
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)
    raise SystemExit(main())
