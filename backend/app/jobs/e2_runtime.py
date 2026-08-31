from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.db.e2_guard import E2GuardError, E2MigrationGuard, load_guard_from_environment, verify_database_fingerprint
from app.jobs.config import JobRuntimeConfig
from app.jobs.runner import SqlJobRunner, default_job_handlers, runner_enabled_from_environment

E2_RUNNER_POOL_SIZE = SqlJobRunner.CONCURRENCY + 1


@dataclass(frozen=True, slots=True)
class E2RunnerRuntime:
    """An isolated E2 engine and runner, never backed by the business engine."""

    runner: SqlJobRunner
    engine: AsyncEngine
    guard: E2MigrationGuard

    async def verify_target(self) -> None:
        """Verify server/database session facts before consuming any job."""

        async with self.engine.connect() as connection:
            await connection.run_sync(lambda sync: verify_database_fingerprint(sync, self.guard))

    async def start(self) -> None:
        """Verify the approved target before the runner can claim a job."""

        await self.verify_target()
        await self.runner.start()


def process_e2_environment() -> dict[str, str]:
    """Capture only explicit E2 process variables before any dotenv loading."""

    names = {
        "E2_RUNNER_ENABLED",
        "E2_MIGRATION_ENABLED",
        "E2_DATABASE_URL",
        "E2_APPROVAL_TOKEN",
        "E2_PREFLIGHT_FILE",
        "JOB_LEASE_SECONDS",
        "JOB_HEARTBEAT_SECONDS",
        "JOB_POLL_SECONDS",
        "JOB_SHUTDOWN_DRAIN_SECONDS",
        "JOB_MAX_ATTEMPTS",
        "JOB_GLOBAL_BACKPRESSURE",
        "JOB_OWNER_TYPE_BACKPRESSURE",
    }
    return {name: os.environ[name] for name in names if name in os.environ}


def build_e2_runner(
    *,
    environ: Mapping[str, str] | None = None,
    inspector: Callable[[str], Mapping[str, object]] | None = None,
) -> E2RunnerRuntime | None:
    """Build the runner only after the explicit E2 target guard succeeds.

    A false switch is inert and creates no engine.  A true switch without a
    valid preflight is an error rather than a fallback to the application
    database.
    """

    values = environ if environ is not None else process_e2_environment()
    if not runner_enabled_from_environment(values):
        return None
    try:
        guard_kwargs = {"environ": values}
        if inspector is not None:
            guard_kwargs["inspector"] = inspector
        guard = load_guard_from_environment("runner", **guard_kwargs)
    except E2GuardError as exc:
        raise RuntimeError(f"E2 runner refused to start: {exc}") from exc
    if guard.target.role != "source":
        raise RuntimeError("E2 runner refused to start: runner target must be the approved source database")
    # GET_LOCK owns one connection for the process lifetime.  The second
    # connection is required for the single-concurrency runner to claim and
    # transition jobs without waiting on its own advisory lock.
    engine = create_async_engine(
        guard.database_url,
        pool_size=E2_RUNNER_POOL_SIZE,
        max_overflow=0,
        echo=False,
    )
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return E2RunnerRuntime(
        runner=SqlJobRunner(
            factory,
            config=JobRuntimeConfig.from_environment(values),
            registry=default_job_handlers(),
            enabled=True,
        ),
        engine=engine,
        guard=guard,
    )
