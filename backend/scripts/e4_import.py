"""Execute a reviewed E4 business bundle in deterministic SQL batches.

The command is intentionally explicit: it never guesses a database URL or
credential, and it cannot perform a write without the E4 migration guard and a
fresh database identity check.  ``--dry-run`` remains offline-only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Imports follow the direct-execution bootstrap path.
# ruff: noqa: E402
from app.db.e4_guard import E4GuardError, inspect_e4_container, load_guard_from_environment, verify_database_fingerprint
from app.db.schema_revision import E4_DATABASE_SCHEMA_REVISION
from app.db.uow import SqlUnitOfWork
from app.e4.importer import (
    E4BundleValidationError,
    E4ImportBlocked,
    E4Importer,
    E4ImportError,
    build_business_dry_run,
    bundle_file_sha256,
    load_business_bundle,
)
from app.e4.payload import build_business_payload_report


async def _run(args: argparse.Namespace) -> dict[str, object]:
    bundle = load_business_bundle(args.source)
    file_digest = bundle_file_sha256(args.source)
    if args.expected_manifest_sha256 not in {bundle.snapshot_manifest_digest, file_digest}:
        raise E4BundleValidationError("expected manifest SHA-256 does not match the bundle manifest")
    if args.migration_batch_id is not None and args.migration_batch_id != bundle.migration_batch_id:
        raise E4BundleValidationError("--migration-batch-id does not match the bundle")
    if args.correlation_id is not None and str(args.correlation_id) != bundle.correlation_id:
        raise E4BundleValidationError("--correlation-id does not match the bundle")

    report = build_business_dry_run(bundle)
    payload_report = build_business_payload_report(bundle)
    if args.dry_run or payload_report["blocked"]:
        return {
            "dry_run": args.dry_run,
            "blocked": report.blocked or payload_report["blocked"],
            "migration_batch_id": bundle.migration_batch_id,
            "correlation_id": bundle.correlation_id,
            "snapshot_manifest_digest": bundle.snapshot_manifest_digest,
            "bundle_file_sha256": file_digest,
            "report_sha256": report.report_sha256,
            "counts": dict(report.counts),
            "business_validation": payload_report,
        }

    if not args.preflight:
        raise E4GuardError("E4 import requires the explicit --preflight gate")
    guard = load_guard_from_environment("migrate", container_inspector=inspect_e4_container)
    if guard.target.role != "target":
        raise E4GuardError("E4 import requires the allowlisted final target role")
    engine = create_async_engine(guard.database_url, pool_size=1, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    aggregate: dict[str, int] = {
        "imported_entities": 0,
        "skipped_entities": 0,
        "quarantined_entities": 0,
        "media_imported": 0,
    }
    blocked = False
    try:
        async with engine.connect() as connection:
            await connection.run_sync(lambda sync: verify_database_fingerprint(sync, guard))
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != E4_DATABASE_SCHEMA_REVISION:
                raise E4GuardError("E4 import requires the exact reviewed schema revision")

        total = len(bundle.entities)
        offsets = range(0, total, args.batch_size) if total else (0,)
        for offset in offsets:
            limit = min(args.batch_size, total - offset) if total else None
            final = True if total == 0 else offset + limit >= total
            async with SqlUnitOfWork(factory) as uow:
                result = await E4Importer(uow.require_session(), actor_id=bundle.actor_id).import_bundle(
                    bundle,
                    batch_size=args.batch_size,
                    resume=args.resume,
                    entity_offset=offset,
                    entity_limit=limit,
                    finalize=final,
                    include_media=offset == 0,
                )
                await uow.commit()
            aggregate["imported_entities"] += result.imported_entities
            aggregate["skipped_entities"] += result.skipped_entities
            aggregate["quarantined_entities"] = result.quarantined_entities
            aggregate["media_imported"] += result.media_imported
            if result.blocked:
                # A quarantine is persisted as a blocked batch by the
                # importer.  Do not start another chunk after that terminal
                # failure; return the evidence with a non-zero exit code.
                blocked = True
                break
    finally:
        await engine.dispose()
    return {
        "dry_run": False,
        "migration_batch_id": bundle.migration_batch_id,
        "correlation_id": bundle.correlation_id,
        "snapshot_manifest_digest": bundle.snapshot_manifest_digest,
        "bundle_file_sha256": file_digest,
        "batch_size": args.batch_size,
        "blocked": blocked,
        **aggregate,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import an explicit E4 business bundle in SQL batches")
    parser.add_argument("--source", required=True, type=Path, help="Explicit JSON business bundle")
    parser.add_argument("--expected-manifest-sha256", required=True, help="Expected snapshot manifest SHA-256")
    parser.add_argument("--migration-batch-id")
    parser.add_argument("--correlation-id", type=UUID)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true", help="Validate offline without opening the target database")
    parser.add_argument("--resume", action="store_true", help="Resume an existing partial batch; reject already imported rows otherwise")
    parser.add_argument("--preflight", action="store_true", help="Require the explicit E4 preflight guard before writing")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.batch_size <= 0 or args.batch_size > 100_000:
        print(json.dumps({"error": "batch_size must be between 1 and 100000"}, ensure_ascii=False))
        return 1
    try:
        result = asyncio.run(_run(args))
    except (E4GuardError, E4ImportBlocked, E4ImportError, OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 2 if result.get("blocked") else 0


if __name__ == "__main__":
    raise SystemExit(main())
