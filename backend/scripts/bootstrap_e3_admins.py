from __future__ import annotations

import argparse
import asyncio
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
from app.auth.audit import record_audit
from app.auth.authorization import bootstrap_admins
from app.db.e3_guard import E3GuardError, load_guard_from_environment, verify_database_fingerprint
from app.db.schema_revision import E3_DATABASE_SCHEMA_REVISION
from app.db.uow import SqlUnitOfWork


def _uuid(value: str, name: str) -> str:
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{name} must be a UUID") from exc
    return str(parsed)


async def _run(args: argparse.Namespace) -> None:
    guard = load_guard_from_environment("runtime")
    engine = create_async_engine(guard.database_url, pool_size=1, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(lambda sync: verify_database_fingerprint(sync, guard))
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != E3_DATABASE_SCHEMA_REVISION:
                raise RuntimeError("E3 administrator bootstrap requires the exact reviewed schema revision")
        async with SqlUnitOfWork(factory) as uow:
            values = await bootstrap_admins(
                uow.require_session(),
                skill_admin_id=args.skill_admin_id,
                security_admin_id=args.security_admin_id,
            )
            await record_audit(
                uow.require_session(),
                actor_type="system",
                actor_id="e3-bootstrap",
                action="role.bootstrap",
                target_type="system",
                target_id="global",
                scope_type="global",
                scope_id="global",
                result="success",
                reason="E3 administrator bootstrap",
                correlation_id=str(uuid4()),
                after={"skill_admin_id": values["skill_admin_id"], "security_admin_id": values["security_admin_id"]},
            )
            await uow.commit()
    finally:
        await engine.dispose()
    print("E3 administrator bootstrap completed")


def main() -> None:
    parser = argparse.ArgumentParser(description="One-time E3 administrator bootstrap")
    parser.add_argument("--skill-admin-id", required=True, type=lambda value: _uuid(value, "skill-admin-id"))
    parser.add_argument("--security-admin-id", required=True, type=lambda value: _uuid(value, "security-admin-id"))
    args = parser.parse_args()
    try:
        asyncio.run(_run(args))
    except E3GuardError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
