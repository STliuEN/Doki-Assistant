from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.uow import SqlUnitOfWork
from app.jobs.config import JobRuntimeConfig
from app.jobs.repository import JobRepository
from app.jobs.runner import (
    JobHandlerError,
    JobHandlerRegistry,
    SqlJobRunner,
)
from app.models.chat_history import Base
from app.models.job_domain import AuditEvent, Job, JobAttempt

JOB_TABLES = (Job.__table__, JobAttempt.__table__, AuditEvent.__table__)
AVAILABLE_NOW = datetime(2020, 1, 1, tzinfo=UTC)


def _run(coro):
    return asyncio.run(coro)


@asynccontextmanager
async def _session_factory(database_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=JOB_TABLES))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _config(**overrides) -> JobRuntimeConfig:
    values = {
        "lease_seconds": 1,
        "heartbeat_seconds": 0.05,
        "poll_seconds": 0.01,
        "shutdown_drain_seconds": 1,
        "max_attempts": 2,
        "retry_delays_seconds": (1,),
        "global_backpressure": 100,
        "owner_type_backpressure": 100,
    }
    values.update(overrides)
    return JobRuntimeConfig(**values)


async def _enqueue(factory, *, job_type: str, value: str = "payload", config: JobRuntimeConfig | None = None):
    async with SqlUnitOfWork(factory) as uow:
        repository = JobRepository(uow.require_session(), config)
        result = await repository.enqueue(
            job_type=job_type,
            owner_scope_type="synthetic",
            owner_scope_id="runner-test",
            idempotency_key=f"{job_type}-{value}",
            payload={"schema_version": 1, "value": value},
            payload_schema_version=1,
            available_at=AVAILABLE_NOW,
        )
        await uow.commit()
        return result.job.id


def test_disabled_runner_is_inert() -> None:
    def forbidden_factory():
        raise AssertionError("disabled runner must not open a SQL session")

    async def scenario():
        runner = SqlJobRunner(forbidden_factory, enabled=False)
        await runner.start()
        await runner.stop()
        assert runner.status()["status"] == "disabled"
        assert runner.status()["enabled"] is False
        assert runner.status()["concurrency"] == 1

    _run(scenario())


def test_runner_executes_echo_and_records_success(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "echo.db") as factory:
            job_id = await _enqueue(factory, job_type="e2.echo", value="hello")
            runner = SqlJobRunner(factory, config=_config(), lease_owner="runner-echo")

            assert await runner.run_once() is True
            assert await runner.run_once() is False

            async with factory() as session:
                job = await session.get(Job, job_id)
                attempt = await session.scalar(select(JobAttempt).where(JobAttempt.job_id == job_id))
                assert job is not None
                assert job.status == "succeeded"
                assert job.result_json == {
                    "schema_version": 1,
                    "echo": {"schema_version": 1, "value": "hello"},
                }
                assert attempt is not None and attempt.outcome == "succeeded"

            status = runner.status()
            assert status["succeeded_count"] == 1
            assert status["failed_count"] == 0
            assert status["active_job_id"] is None

    _run(scenario())


def test_unknown_job_type_is_dead_lettered_and_counted(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "unknown.db") as factory:
            job_id = await _enqueue(factory, job_type="e2.unknown", config=_config())
            runner = SqlJobRunner(factory, config=_config(), lease_owner="runner-unknown")

            assert await runner.run_once() is True

            async with factory() as session:
                job = await session.get(Job, job_id)
                assert job is not None and job.status == "dead_letter"
                assert job.error_code == "unknown_job_type"

            assert runner.status()["failed_count"] == 1

    _run(scenario())


def test_handler_failure_uses_retry_policy(tmp_path) -> None:
    async def scenario():
        config = _config()
        registry = JobHandlerRegistry()

        async def fail_handler(_payload, _context):
            raise JobHandlerError("synthetic_failure", "retry me")

        registry.register("e2.fail", fail_handler)
        async with _session_factory(tmp_path / "failure.db") as factory:
            job_id = await _enqueue(factory, job_type="e2.fail", config=config)
            runner = SqlJobRunner(factory, config=config, registry=registry, lease_owner="runner-failure")

            assert await runner.run_once() is True

            async with factory() as session:
                job = await session.get(Job, job_id)
                attempt = await session.scalar(select(JobAttempt).where(JobAttempt.job_id == job_id))
                assert job is not None and job.status == "retry_wait"
                assert job.error_code == "synthetic_failure"
                assert attempt is not None and attempt.outcome == "retry_wait"
            assert runner.status()["failed_count"] == 1

    _run(scenario())


def test_empty_poll_commits_expired_lease_recovery(tmp_path) -> None:
    async def scenario():
        config = _config()
        async with _session_factory(tmp_path / "recovery-poll.db") as factory:
            job_id = await _enqueue(factory, job_type="e2.recovery", config=config)

            async with SqlUnitOfWork(factory) as uow:
                repository = JobRepository(uow.require_session(), config)
                claim = await repository.claim_one(lease_owner="crashed-runner", now=AVAILABLE_NOW)
                assert claim is not None
                started = await repository.start(
                    job_id=job_id,
                    lease_owner="crashed-runner",
                    fencing_token=claim.attempt.fencing_token,
                    now=AVAILABLE_NOW,
                )
                assert started.accepted
                await uow.commit()

            # Simulate a crashed worker whose SQL lease has expired.  The
            # runner's next empty poll must persist the recovery transition.
            async with factory() as session:
                await session.execute(
                    text("UPDATE jobs SET lease_expires_at = :expired WHERE id = :job_id"),
                    {"expired": AVAILABLE_NOW.replace(year=2019), "job_id": job_id},
                )
                await session.commit()

            runner = SqlJobRunner(factory, config=config, lease_owner="replacement-runner")
            assert await runner.run_once() is False

            async with factory() as session:
                job = await session.get(Job, job_id)
                attempt = await session.scalar(select(JobAttempt).where(JobAttempt.job_id == job_id))
                assert job is not None and job.status == "retry_wait"
                assert attempt is not None and attempt.outcome == "abandoned"
                assert await session.scalar(
                    select(AuditEvent.action).where(
                        AuditEvent.job_id == job_id,
                        AuditEvent.action == "job.lease_expired",
                    )
                ) == "job.lease_expired"

    _run(scenario())


def test_lost_lease_cancels_handler_without_accepting_result(tmp_path) -> None:
    async def scenario():
        registry = JobHandlerRegistry()
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def blocking_handler(_payload, _context):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        registry.register("e2.blocking", blocking_handler)
        async with _session_factory(tmp_path / "fence.db") as factory:
            job_id = await _enqueue(factory, job_type="e2.blocking", config=_config())
            runner = SqlJobRunner(factory, config=_config(), registry=registry, lease_owner="runner-fence")

            async def lost_heartbeat(*, job_id: str, fencing_token: int) -> bool:
                del job_id, fencing_token
                return False

            runner._heartbeat = lost_heartbeat
            task = asyncio.create_task(runner.run_once())
            await asyncio.wait_for(started.wait(), timeout=1)
            assert await asyncio.wait_for(task, timeout=1) is True
            assert cancelled.is_set()

            async with factory() as session:
                job = await session.get(Job, job_id)
                assert job is not None and job.status == "running"
            assert runner.status()["rejected_count"] == 1

    _run(scenario())


def test_cancellation_request_prevents_success_commit(tmp_path) -> None:
    async def scenario():
        config = _config()
        registry = JobHandlerRegistry()
        started = asyncio.Event()
        release = asyncio.Event()

        async def cancellable_handler(_payload, _context):
            started.set()
            await release.wait()
            return {"schema_version": 1, "ok": True}

        registry.register("e2.cancellable", cancellable_handler)
        async with _session_factory(tmp_path / "cancel.db") as factory:
            job_id = await _enqueue(factory, job_type="e2.cancellable", config=config)
            runner = SqlJobRunner(factory, config=config, registry=registry, lease_owner="runner-cancel")
            task = asyncio.create_task(runner.run_once())
            await asyncio.wait_for(started.wait(), timeout=1)

            async with SqlUnitOfWork(factory) as uow:
                repository = JobRepository(uow.require_session(), config)
                transition = await repository.cancel(job_id=job_id, reason="synthetic cancellation")
                assert transition.status == "cancel_requested"
                await uow.commit()

            release.set()
            assert await asyncio.wait_for(task, timeout=1) is True
            async with factory() as session:
                job = await session.get(Job, job_id)
                assert job is not None and job.status == "cancelled"
            assert runner.status()["succeeded_count"] == 0

    _run(scenario())


def test_runner_start_and_graceful_stop(tmp_path) -> None:
    async def scenario():
        config = _config()
        async with _session_factory(tmp_path / "lifecycle.db") as factory:
            await _enqueue(factory, job_type="e2.noop", config=config)
            runner = SqlJobRunner(factory, config=config, lease_owner="runner-lifecycle", enabled=True)
            await runner.start()
            for _ in range(300):
                if runner.status()["succeeded_count"] == 1:
                    break
                await asyncio.sleep(0.01)
            await runner.stop()
            assert runner.status()["succeeded_count"] == 1
            assert runner.status()["status"] == "stopped"
            assert runner.task is None

    _run(scenario())
