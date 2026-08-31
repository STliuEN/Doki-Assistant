from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.uow import SqlUnitOfWork, UnitOfWorkError, run_in_uow
from app.jobs.config import JobRuntimeConfig
from app.jobs.repository import (
    JobBackpressureError,
    JobConflictError,
    JobRepository,
    JobValidationError,
)
from app.models.chat_history import Base
from app.models.job_domain import AuditEvent, Job, JobAttempt

JOB_TABLES = (Job.__table__, JobAttempt.__table__, AuditEvent.__table__)
BASE_TIME = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


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


def _payload(value: str = "one") -> dict[str, object]:
    return {"schema_version": 1, "value": value}


def _config(**overrides) -> JobRuntimeConfig:
    values = {"global_backpressure": 1000, "owner_type_backpressure": 100}
    values.update(overrides)
    return JobRuntimeConfig(**values)


def test_database_now_accepts_sqlite_text_and_normalizes_utc() -> None:
    class FakeSession:
        async def scalar(self, _statement):
            return "2026-08-28 12:34:56.123456"

    value = _run(JobRepository(FakeSession())._database_now())
    assert value == datetime(2026, 8, 28, 12, 34, 56, 123456, tzinfo=UTC)


def test_uow_commit_and_implicit_rollback(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "uow.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                repository = JobRepository(uow.require_session())
                result = await repository.enqueue(
                    job_type="e2.noop",
                    owner_scope_type="user",
                    owner_scope_id="uow",
                    idempotency_key="commit",
                    payload=_payload(),
                    payload_schema_version=1,
                    available_at=BASE_TIME,
                )
                await uow.commit()
                assert result.created

            async with SqlUnitOfWork(factory) as uow:
                repository = JobRepository(uow.require_session())
                await repository.enqueue(
                    job_type="e2.noop",
                    owner_scope_type="user",
                    owner_scope_id="uow",
                    idempotency_key="rollback",
                    payload=_payload("rollback"),
                    payload_schema_version=1,
                    available_at=BASE_TIME,
                )

            async with factory() as session:
                assert await session.scalar(select(func.count(Job.id))) == 1
                assert await session.scalar(select(func.count(AuditEvent.id))) == 1

    _run(scenario())


def test_job_state_machine_fencing_and_idempotency(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "state.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                repository = JobRepository(uow.require_session())
                first = await repository.enqueue(
                    job_type="e2.noop",
                    owner_scope_type="user",
                    owner_scope_id="state",
                    idempotency_key="same",
                    payload=_payload(),
                    payload_schema_version=1,
                    available_at=BASE_TIME,
                )
                duplicate = await repository.enqueue(
                    job_type="e2.noop",
                    owner_scope_type="user",
                    owner_scope_id="state",
                    idempotency_key="same",
                    payload={"value": "one", "schema_version": 1},
                    payload_schema_version=1,
                    available_at=BASE_TIME,
                )
                assert duplicate.created is False
                with pytest.raises(JobConflictError):
                    await repository.enqueue(
                        job_type="e2.noop",
                        owner_scope_type="user",
                        owner_scope_id="state",
                        idempotency_key="same",
                        payload=_payload("different"),
                        payload_schema_version=1,
                        available_at=BASE_TIME,
                    )
                await uow.commit()

            async with SqlUnitOfWork(factory) as uow:
                repository = JobRepository(uow.require_session())
                claim = await repository.claim_one(lease_owner="runner-a", now=BASE_TIME + timedelta(seconds=1))
                assert claim is not None
                assert claim.job.id == first.job.id
                assert claim.attempt.fencing_token == 1
                await uow.commit()

            async with SqlUnitOfWork(factory) as uow:
                repository = JobRepository(uow.require_session())
                started = await repository.start(
                    job_id=claim.job.id,
                    lease_owner="runner-a",
                    fencing_token=1,
                    now=BASE_TIME + timedelta(seconds=2),
                )
                assert started.accepted and started.status == "running"
                heartbeat = await repository.heartbeat(
                    job_id=claim.job.id,
                    lease_owner="runner-a",
                    fencing_token=1,
                    now=BASE_TIME + timedelta(seconds=3),
                )
                assert heartbeat.accepted
                await uow.commit()

            async with SqlUnitOfWork(factory) as uow:
                repository = JobRepository(uow.require_session())
                stale = await repository.succeed(
                    job_id=claim.job.id,
                    lease_owner="old-runner",
                    fencing_token=0,
                    result_payload={"schema_version": 1, "ok": True},
                    result_schema_version=1,
                    now=BASE_TIME + timedelta(seconds=4),
                )
                assert stale.accepted is False and stale.reason == "stale_fencing_token"
                succeeded = await repository.succeed(
                    job_id=claim.job.id,
                    lease_owner="runner-a",
                    fencing_token=1,
                    result_payload={"schema_version": 1, "ok": True},
                    result_schema_version=1,
                    now=BASE_TIME + timedelta(seconds=4),
                )
                assert succeeded.accepted and succeeded.status == "succeeded"
                await uow.commit()

            async with factory() as session:
                job = await session.get(Job, claim.job.id)
                assert job is not None and job.status == "succeeded"
                assert await session.scalar(
                    select(func.count(AuditEvent.id)).where(AuditEvent.action == "job.fenced_rejected")
                ) == 1

    _run(scenario())


def test_retry_cancel_dead_letter_and_replay(tmp_path) -> None:
    async def scenario():
        config = _config(max_attempts=2, retry_delays_seconds=(5,))
        async with _session_factory(tmp_path / "retry.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                repository = JobRepository(uow.require_session(), config)
                enqueued = await repository.enqueue(
                    job_type="e2.fail",
                    owner_scope_type="user",
                    owner_scope_id="retry",
                    idempotency_key="retry",
                    payload=_payload(),
                    payload_schema_version=1,
                    available_at=BASE_TIME,
                )
                await uow.commit()

            async with SqlUnitOfWork(factory) as uow:
                repository = JobRepository(uow.require_session(), config)
                claim = await repository.claim_one(lease_owner="runner", now=BASE_TIME)
                assert claim is not None
                await repository.start(
                    job_id=claim.job.id,
                    lease_owner="runner",
                    fencing_token=claim.attempt.fencing_token,
                    now=BASE_TIME,
                )
                failed = await repository.fail(
                    job_id=claim.job.id,
                    lease_owner="runner",
                    fencing_token=claim.attempt.fencing_token,
                    error_code="temporary",
                    error_detail="try again",
                    permanent=False,
                    now=BASE_TIME,
                )
                assert failed.status == "retry_wait"
                await uow.commit()

            async with SqlUnitOfWork(factory) as uow:
                repository = JobRepository(uow.require_session(), config)
                claim = await repository.claim_one(lease_owner="runner", now=BASE_TIME + timedelta(seconds=6))
                assert claim is not None and claim.attempt.attempt_number == 2
                await repository.start(
                    job_id=claim.job.id,
                    lease_owner="runner",
                    fencing_token=claim.attempt.fencing_token,
                    now=BASE_TIME + timedelta(seconds=6),
                )
                failed = await repository.fail(
                    job_id=claim.job.id,
                    lease_owner="runner",
                    fencing_token=claim.attempt.fencing_token,
                    error_code="permanent",
                    error_detail="done",
                    permanent=False,
                    now=BASE_TIME + timedelta(seconds=6),
                )
                assert failed.status == "dead_letter"
                await uow.commit()

            async with SqlUnitOfWork(factory) as uow:
                repository = JobRepository(uow.require_session(), config)
                replay = await repository.replay_dead_letter(job_id=enqueued.job.id, idempotency_key="replay")
                assert replay.created and replay.job.replay_of_job_id == enqueued.job.id
                await uow.commit()

            async with SqlUnitOfWork(factory) as uow:
                repository = JobRepository(uow.require_session(), config)
                cancelled = await repository.cancel(job_id=replay.job.id, reason="operator requested", now=BASE_TIME)
                assert cancelled.status == "cancelled"
                await uow.commit()

    _run(scenario())


def test_running_cancellation_is_cooperative_and_expiry_recovers(tmp_path) -> None:
    async def scenario():
        config = _config(max_attempts=2, retry_delays_seconds=(5,))
        async with _session_factory(tmp_path / "cancel.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                repository = JobRepository(uow.require_session(), config)
                enqueued = await repository.enqueue(
                    job_type="e2.cancel",
                    owner_scope_type="user",
                    owner_scope_id="cancel",
                    idempotency_key="cancel",
                    payload=_payload(),
                    payload_schema_version=1,
                    available_at=BASE_TIME,
                )
                await uow.commit()

            async with SqlUnitOfWork(factory) as uow:
                repository = JobRepository(uow.require_session(), config)
                claim = await repository.claim_one(lease_owner="runner", now=BASE_TIME)
                assert claim is not None
                await repository.start(
                    job_id=claim.job.id,
                    lease_owner="runner",
                    fencing_token=claim.attempt.fencing_token,
                    now=BASE_TIME,
                )
                await uow.commit()

            async with SqlUnitOfWork(factory) as uow:
                repository = JobRepository(uow.require_session(), config)
                requested = await repository.cancel(job_id=enqueued.job.id, reason="stop", now=BASE_TIME)
                assert requested.status == "cancel_requested"
                assert await repository.cancellation_requested(
                    job_id=enqueued.job.id,
                    lease_owner="runner",
                    fencing_token=claim.attempt.fencing_token,
                )
                await uow.commit()

            async with SqlUnitOfWork(factory) as uow:
                repository = JobRepository(uow.require_session(), config)
                recovered = await repository.recover_expired(
                    now=BASE_TIME + timedelta(seconds=config.lease_seconds + 1)
                )
                assert recovered == 1
                await uow.commit()

            async with factory() as session:
                job = await session.get(Job, enqueued.job.id)
                assert job is not None and job.status == "cancelled"
                attempt = await session.scalar(select(JobAttempt).where(JobAttempt.job_id == job.id))
                assert attempt is not None and attempt.outcome == "abandoned"

    _run(scenario())


def test_backpressure_and_input_limits(tmp_path) -> None:
    async def scenario():
        config = _config(global_backpressure=1, owner_type_backpressure=1)
        async with _session_factory(tmp_path / "limits.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                repository = JobRepository(uow.require_session(), config)
                await repository.enqueue(
                    job_type="e2.limit",
                    owner_scope_type="user",
                    owner_scope_id="limit",
                    idempotency_key="one",
                    payload=_payload(),
                    payload_schema_version=1,
                    available_at=BASE_TIME,
                )
                with pytest.raises(JobBackpressureError):
                    await repository.enqueue(
                        job_type="e2.limit",
                        owner_scope_type="user",
                        owner_scope_id="limit",
                        idempotency_key="two",
                        payload=_payload("two"),
                        payload_schema_version=1,
                        available_at=BASE_TIME,
                    )
                with pytest.raises(JobValidationError):
                    await repository.enqueue(
                        job_type="e2.limit",
                        owner_scope_type="user",
                        owner_scope_id="limit",
                        idempotency_key="bad",
                        payload={"schema_version": 2},
                        payload_schema_version=1,
                        available_at=BASE_TIME,
                    )
                await uow.commit()

    _run(scenario())


def test_uow_operation_exception_rolls_back_and_reentry_is_rejected(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "errors.db") as factory:
            async def operation(session):
                repository = JobRepository(session)
                await repository.enqueue(
                    job_type="e2.error",
                    owner_scope_type="user",
                    owner_scope_id="error",
                    idempotency_key="rollback",
                    payload=_payload(),
                    payload_schema_version=1,
                    available_at=BASE_TIME,
                )
                raise RuntimeError("abort")

            with pytest.raises(RuntimeError, match="abort"):
                await run_in_uow(factory, operation)

            uow = SqlUnitOfWork(factory)
            async with uow:
                await uow.commit()
                with pytest.raises(UnitOfWorkError, match="already committed"):
                    await uow.commit()
                await uow.rollback()
            with pytest.raises(UnitOfWorkError, match="cannot be entered twice"):
                await uow.__aenter__()

            async with factory() as session:
                assert await session.scalar(select(func.count(Job.id))) == 0

    _run(scenario())
