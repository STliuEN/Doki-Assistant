from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Imports follow the direct-execution path bootstrap.
# ruff: noqa: E402
from app.auth.migration import (
    build_migration_plan,
    import_migration_plan,
    load_source_dump,
    source_digest,
    validate_migration_plan,
)
from app.db.e3_guard import E3GuardError, load_guard_from_environment, verify_database_fingerprint
from app.db.schema_revision import E3_DATABASE_SCHEMA_REVISION
from app.db.uow import SqlUnitOfWork


async def _run(args: argparse.Namespace) -> None:
    guard = load_guard_from_environment("import")
    source_path = Path(args.source).resolve(strict=True)
    actual_digest = source_digest(source_path)
    if actual_digest != args.expected_sha256:
        raise ValueError("Source dump SHA-256 does not match --expected-sha256")
    users = load_source_dump(source_path)
    plan = build_migration_plan(
        users,
        migration_batch_id=args.migration_batch_id,
        source_digest_value=actual_digest,
    )

    engine = create_async_engine(guard.database_url, pool_size=1, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(lambda sync: verify_database_fingerprint(sync, guard))
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != E3_DATABASE_SCHEMA_REVISION:
                raise RuntimeError("E3 user import requires the exact reviewed schema revision")
        async with SqlUnitOfWork(factory) as uow:
            if args.dry_run:
                await validate_migration_plan(uow.require_session(), plan)
                inserted = 0
                await uow.rollback()
            else:
                inserted = await import_migration_plan(
                    uow.require_session(),
                    plan,
                    correlation_id=str(args.correlation_id or uuid4()),
                )
                await uow.commit()
    finally:
        await engine.dispose()

    print(
        json.dumps(
            {
                "dry_run": args.dry_run,
                "migration_batch_id": plan.migration_batch_id,
                "source_sha256": plan.source_digest,
                "source_user_count": len(plan.users),
                "inserted_user_count": inserted,
            },
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate or atomically import an approved Django user dump into E3")
    parser.add_argument("--source", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--migration-batch-id", required=True)
    parser.add_argument("--correlation-id", type=UUID)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(_run(args))
    except (E3GuardError, OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
