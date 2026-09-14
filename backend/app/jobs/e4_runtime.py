"""Guarded application runner for E4 and the explicitly enabled E5 projection."""

import os
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.e4_process_environment import E4_PROCESS_ENVIRONMENT
from app.db.business_authority import BusinessSession
from app.db.e4_guard import E4MigrationGuard, inspect_e4_container, load_guard_from_environment, verify_database_fingerprint
from app.db.schema_revision import DATABASE_SCHEMA_REVISION
from app.jobs.business_handlers import business_handlers
from app.jobs.config import JobRuntimeConfig
from app.jobs.runner import SqlJobRunner


@dataclass
class E4RunnerRuntime:
    runner: SqlJobRunner
    engine: AsyncEngine
    guard: E4MigrationGuard

    async def start(self):
        async with self.engine.connect() as connection:
            await connection.run_sync(lambda sync: verify_database_fingerprint(sync, self.guard))
            expected = DATABASE_SCHEMA_REVISION
            if tuple((await connection.execute(text("SELECT version_num FROM alembic_version"))).scalars()) != (expected,):
                raise RuntimeError("runtime runner schema revision mismatch")
        await self.runner.start()


def build_e4_runner(*, environ=None):
    values = E4_PROCESS_ENVIRONMENT if environ is None else environ
    if not values.get("E4_MIGRATION_ENABLED") or values.get("E4_RUNNER_ENABLED", "true").lower() not in {"true", "1", "yes"}:
        return None
    guard = load_guard_from_environment("runtime", environ=values, container_inspector=inspect_e4_container)
    if guard.target.role != "target":
        raise RuntimeError("E4 business runner requires the target role")
    engine = create_async_engine(guard.database_url, pool_size=3, max_overflow=0, hide_parameters=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, sync_session_class=BusinessSession)
    projector = None
    if os.getenv("E5_RAG_ENABLED", "false").lower() in {"1", "true", "yes", "on"}:
        from app.rag.projection.service import E5ProjectionService
        e5_service = E5ProjectionService(factory)

        async def projector(_session, _job_type, payload, context):
            return await e5_service.rebuild(_session, str(payload["owner_id"]), context)
    return E4RunnerRuntime(
        SqlJobRunner(
            factory,
            config=JobRuntimeConfig.from_environment(values),
            registry=business_handlers(factory, projector=projector),
            lock_name="doki-e4-business-runner",
            claim_registered_only=True,
        ),
        engine,
        guard,
    )
