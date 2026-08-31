"""Single-concurrency SQL durable job runner.

The runner owns no business data and only dispatches handlers explicitly
registered by the E2 process.  Lease state is committed before a handler is
started, and every heartbeat/result transition is fenced by the SQL token.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable, Mapping, Protocol
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.uow import SqlUnitOfWork
from app.jobs.config import JobRuntimeConfig
from app.jobs.repository import JobRepository

logger = logging.getLogger(__name__)


class JobHandlerError(RuntimeError):
    """A handler failure with an explicit retry/permanent decision."""

    def __init__(self, code: str, detail: str, *, permanent: bool = False) -> None:
        self.code = code
        self.detail = detail
        self.permanent = permanent
        super().__init__(detail)


class LeaseLostError(RuntimeError):
    """The runner lost its SQL lease while a handler was executing."""


class JobHandlerContext(Protocol):
    job_id: str
    job_type: str
    attempt_number: int
    fencing_token: int
    lease_owner: str

    async def cancellation_requested(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class RunnerHandlerContext:
    job_id: str
    job_type: str
    attempt_number: int
    fencing_token: int
    lease_owner: str
    _cancellation_probe: Callable[[], Awaitable[bool]]

    async def cancellation_requested(self) -> bool:
        return await self._cancellation_probe()


JobHandler = Callable[[Mapping[str, Any], JobHandlerContext], Awaitable[Mapping[str, Any]] | Mapping[str, Any]]


class JobHandlerRegistry:
    """Explicit allowlist of job handlers available to the E2 runner."""

    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}

    def register(self, job_type: str, handler: JobHandler, *, replace: bool = False) -> None:
        if not isinstance(job_type, str) or not job_type or len(job_type) > 128:
            raise ValueError("job_type must be a non-empty string of at most 128 characters")
        if not callable(handler):
            raise TypeError("job handler must be callable")
        if job_type in self._handlers and not replace:
            raise ValueError(f"job handler already registered: {job_type}")
        self._handlers[job_type] = handler

    def resolve(self, job_type: str) -> JobHandler | None:
        return self._handlers.get(job_type)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))


async def _noop_handler(payload: Mapping[str, Any], _context: JobHandlerContext) -> Mapping[str, Any]:
    del payload
    return {"schema_version": 1, "ok": True}


async def _echo_handler(payload: Mapping[str, Any], _context: JobHandlerContext) -> Mapping[str, Any]:
    return {"schema_version": 1, "echo": dict(payload)}


def default_job_handlers() -> JobHandlerRegistry:
    """Build the small, deterministic E2 handler allowlist."""

    registry = JobHandlerRegistry()
    registry.register("e2.noop", _noop_handler)
    registry.register("e2.echo", _echo_handler)
    return registry


@dataclass(frozen=True, slots=True)
class RunnerSnapshot:
    status: str = "disabled"
    enabled: bool = False
    concurrency: int = 1
    lease_owner: str | None = None
    active_job_id: str | None = None
    active_job_type: str | None = None
    active_attempt: int | None = None
    active_fencing_token: int | None = None
    claimed_count: int = 0
    succeeded_count: int = 0
    failed_count: int = 0
    rejected_count: int = 0
    last_poll_at: datetime | None = None
    last_completed_at: datetime | None = None
    last_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "enabled": self.enabled,
            "concurrency": self.concurrency,
            "lease_owner": self.lease_owner,
            "active_job_id": self.active_job_id,
            "active_job_type": self.active_job_type,
            "active_attempt": self.active_attempt,
            "active_fencing_token": self.active_fencing_token,
            "claimed_count": self.claimed_count,
            "succeeded_count": self.succeeded_count,
            "failed_count": self.failed_count,
            "rejected_count": self.rejected_count,
            "last_poll_at": self.last_poll_at.isoformat() if self.last_poll_at else None,
            "last_completed_at": self.last_completed_at.isoformat() if self.last_completed_at else None,
            "last_error": self.last_error,
        }


class SqlJobRunner:
    """An at-least-once SQL runner with a hard concurrency limit of one."""

    CONCURRENCY = 1

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        *,
        config: JobRuntimeConfig | None = None,
        registry: JobHandlerRegistry | None = None,
        lease_owner: str | None = None,
        enabled: bool = True,
        lock_name: str = "doki-e2-sql-runner",
    ) -> None:
        self.session_factory = session_factory
        self.config = config or JobRuntimeConfig.from_environment()
        self.registry = registry or default_job_handlers()
        self.lease_owner = lease_owner or f"runner-{uuid4()}"
        self.enabled = bool(enabled)
        self.lock_name = lock_name
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._lock_session: AsyncSession | None = None
        self._snapshot = RunnerSnapshot(enabled=self.enabled, lease_owner=self.lease_owner)

    @property
    def snapshot(self) -> RunnerSnapshot:
        return self._snapshot

    def status(self) -> dict[str, Any]:
        return self._snapshot.as_dict()

    @property
    def task(self) -> asyncio.Task[None] | None:
        return self._task

    async def start(self) -> None:
        if not self.enabled:
            self._set_snapshot(status="disabled")
            return
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._set_snapshot(status="starting", last_error=None)
        self._task = asyncio.create_task(self.run_forever(), name="e2-sql-job-runner")

    async def stop(self) -> None:
        self._stop_event.set()
        task = self._task
        if task is None:
            if self.enabled:
                self._set_snapshot(status="stopped")
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=self.config.shutdown_drain_seconds)
        except TimeoutError:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        finally:
            self._task = None
            if self.enabled and self._snapshot.status not in {"failed", "stopped"}:
                self._set_snapshot(status="stopped")

    async def run_forever(self) -> None:
        if not self.enabled:
            self._set_snapshot(status="disabled")
            return
        try:
            if not await self._acquire_process_lock():
                self._set_snapshot(status="failed", last_error="runner process lock is held by another instance")
                return
            self._set_snapshot(status="running", last_error=None)
            while not self._stop_event.is_set():
                try:
                    await self.run_once()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # one bad job must not kill the poller
                    message = f"{type(exc).__name__}: {str(exc)[:500]}"
                    logger.error("E2 SQL runner iteration failed: %s", message, exc_info=True)
                    self._set_snapshot(last_error=message)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self.config.poll_seconds)
                except TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            message = f"{type(exc).__name__}: {str(exc)[:500]}"
            logger.error("E2 SQL runner stopped unexpectedly: %s", message, exc_info=True)
            self._set_snapshot(status="failed", last_error=message)
        finally:
            await self._release_process_lock()
            if self._snapshot.status == "running":
                self._set_snapshot(status="stopped")

    async def run_once(self) -> bool:
        """Claim and execute at most one job; return whether a job was claimed."""

        if not self.enabled:
            return False
        self._set_snapshot(last_poll_at=datetime.now(UTC))
        claim = await self._claim()
        if claim is None:
            return False
        job, attempt = claim
        self._set_snapshot(
            active_job_id=str(job.id),
            active_job_type=str(job.job_type),
            active_attempt=int(attempt.attempt_number),
            active_fencing_token=int(attempt.fencing_token),
            claimed_count=self._snapshot.claimed_count + 1,
        )
        try:
            started = await self._start(job_id=str(job.id), fencing_token=int(attempt.fencing_token))
            if not started:
                self._set_snapshot(rejected_count=self._snapshot.rejected_count + 1)
                return True

            handler = self.registry.resolve(str(job.job_type))
            if handler is None:
                await self._finish_failure(
                    job_id=str(job.id),
                    fencing_token=int(attempt.fencing_token),
                    error=JobHandlerError("unknown_job_type", f"no handler registered for {job.job_type}", permanent=True),
                )
                self._set_snapshot(
                    failed_count=self._snapshot.failed_count + 1,
                    last_completed_at=datetime.now(UTC),
                )
                return True

            context = RunnerHandlerContext(
                job_id=str(job.id),
                job_type=str(job.job_type),
                attempt_number=int(attempt.attempt_number),
                fencing_token=int(attempt.fencing_token),
                lease_owner=self.lease_owner,
                _cancellation_probe=lambda: self._cancellation_requested(
                    job_id=str(job.id), fencing_token=int(attempt.fencing_token)
                ),
            )
            result = await self._execute_handler(handler, job.payload_json, context, str(job.id), int(attempt.fencing_token))
            await self._finish_success(
                job_id=str(job.id),
                fencing_token=int(attempt.fencing_token),
                result=result,
            )
            self._set_snapshot(
                succeeded_count=self._snapshot.succeeded_count + 1,
                last_completed_at=datetime.now(UTC),
            )
            return True
        except LeaseLostError as exc:
            self._set_snapshot(rejected_count=self._snapshot.rejected_count + 1, last_error=str(exc))
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            error = exc if isinstance(exc, JobHandlerError) else JobHandlerError(
                "handler_error", f"{type(exc).__name__}: {exc}"
            )
            await self._finish_failure(job_id=str(job.id), fencing_token=int(attempt.fencing_token), error=error)
            self._set_snapshot(
                failed_count=self._snapshot.failed_count + 1,
                last_completed_at=datetime.now(UTC),
            )
            return True
        finally:
            self._set_snapshot(
                active_job_id=None,
                active_job_type=None,
                active_attempt=None,
                active_fencing_token=None,
            )

    async def _claim(self):
        async with SqlUnitOfWork(self.session_factory) as uow:
            await self._set_claim_isolation(uow.require_session())
            repository = JobRepository(uow.require_session(), self.config)
            result = await repository.claim_one(lease_owner=self.lease_owner)
            if result is None:
                # ``claim_one`` may have recovered an expired lease before
                # finding no immediately eligible job.  Keep that recovery
                # and its audit event durable instead of rolling it back.
                await uow.commit()
                return None
            await uow.commit()
            return result.job, result.attempt

    async def _start(self, *, job_id: str, fencing_token: int) -> bool:
        async with SqlUnitOfWork(self.session_factory) as uow:
            repository = JobRepository(uow.require_session(), self.config)
            result = await repository.start(
                job_id=job_id,
                lease_owner=self.lease_owner,
                fencing_token=fencing_token,
            )
            await uow.commit()
            return result.accepted

    async def _heartbeat(self, *, job_id: str, fencing_token: int) -> bool:
        async with SqlUnitOfWork(self.session_factory) as uow:
            repository = JobRepository(uow.require_session(), self.config)
            result = await repository.heartbeat(
                job_id=job_id,
                lease_owner=self.lease_owner,
                fencing_token=fencing_token,
            )
            await uow.commit()
            return result.accepted

    async def _cancellation_requested(self, *, job_id: str, fencing_token: int) -> bool:
        async with self.session_factory() as session:
            repository = JobRepository(session, self.config)
            return await repository.cancellation_requested(
                job_id=job_id,
                lease_owner=self.lease_owner,
                fencing_token=fencing_token,
            )

    async def _finish_success(self, *, job_id: str, fencing_token: int, result: Mapping[str, Any]) -> None:
        async with SqlUnitOfWork(self.session_factory) as uow:
            repository = JobRepository(uow.require_session(), self.config)
            transition = await repository.succeed(
                job_id=job_id,
                lease_owner=self.lease_owner,
                fencing_token=fencing_token,
                result_payload=result,
                result_schema_version=int(result.get("schema_version", 0)),
            )
            await uow.commit()
            if not transition.accepted:
                raise LeaseLostError(transition.reason or "job result was fenced")

    async def _finish_failure(self, *, job_id: str, fencing_token: int, error: JobHandlerError) -> None:
        async with SqlUnitOfWork(self.session_factory) as uow:
            repository = JobRepository(uow.require_session(), self.config)
            transition = await repository.fail(
                job_id=job_id,
                lease_owner=self.lease_owner,
                fencing_token=fencing_token,
                error_code=error.code,
                error_detail=error.detail,
                permanent=error.permanent,
            )
            await uow.commit()
            if not transition.accepted:
                self._set_snapshot(rejected_count=self._snapshot.rejected_count + 1)

    async def _execute_handler(
        self,
        handler: JobHandler,
        payload: Mapping[str, Any],
        context: RunnerHandlerContext,
        job_id: str,
        fencing_token: int,
    ) -> Mapping[str, Any]:
        result = handler(payload, context)
        if inspect.isawaitable(result):
            handler_task = asyncio.create_task(result, name=f"e2-job-{job_id}")
        else:
            async def _completed():
                return result

            handler_task = asyncio.create_task(_completed(), name=f"e2-job-{job_id}")
        try:
            while True:
                done, _ = await asyncio.wait((handler_task,), timeout=self.config.heartbeat_seconds)
                if done:
                    value = handler_task.result()
                    if not isinstance(value, Mapping):
                        raise JobHandlerError("invalid_result", "job handler must return a JSON object", permanent=True)
                    if await context.cancellation_requested():
                        raise JobHandlerError(
                            "cancel_requested",
                            "job cancellation was requested before the handler completed",
                            permanent=True,
                        )
                    return dict(value)
                if not await self._heartbeat(job_id=job_id, fencing_token=fencing_token):
                    handler_task.cancel()
                    try:
                        await handler_task
                    except (asyncio.CancelledError, Exception):
                        pass
                    raise LeaseLostError("job lease was lost during handler execution")
        except asyncio.CancelledError:
            handler_task.cancel()
            try:
                await handler_task
            except (asyncio.CancelledError, Exception):
                pass
            raise

    async def _acquire_process_lock(self) -> bool:
        session = self.session_factory()
        try:
            # Explicitly own the transaction for the lifetime of the lock
            # session.  MySQL GET_LOCK is connection-scoped, so allowing the
            # session to return its connection to the pool would make the
            # process lock unenforceable during a restart or pool checkout.
            await session.begin()
            connection = await session.connection()
            if connection.dialect.name == "mysql":
                acquired = await session.scalar(text("SELECT GET_LOCK(:lock_name, 0)"), {"lock_name": self.lock_name})
                if int(acquired or 0) != 1:
                    await session.rollback()
                    await session.close()
                    return False
            self._lock_session = session
            return True
        except Exception:
            await session.close()
            raise

    async def _release_process_lock(self) -> None:
        session, self._lock_session = self._lock_session, None
        if session is None:
            return
        try:
            connection = await session.connection()
            if connection.dialect.name == "mysql":
                released = await session.scalar(text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": self.lock_name})
                if released not in (None, 1):
                    logger.warning("E2 runner process lock was not held at release: %s", self.lock_name)
            await session.rollback()
        except Exception:
            logger.warning("failed to release E2 runner process lock", exc_info=True)
        finally:
            await session.close()

    @staticmethod
    async def _set_claim_isolation(session: AsyncSession) -> None:
        bind = session.get_bind()
        if getattr(getattr(bind, "dialect", None), "name", None) == "mysql":
            await session.execute(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED"))

    def _set_snapshot(self, **changes: Any) -> None:
        self._snapshot = replace(self._snapshot, **changes)


def runner_enabled_from_environment(environ: Mapping[str, str] | None = None) -> bool:
    """Read the E2-only lifecycle switch without loading any dotenv file."""

    values = environ if environ is not None else os.environ
    return values.get("E2_RUNNER_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


_default_runner: SqlJobRunner | None = None


def configure_default_runner(runner: SqlJobRunner | None) -> None:
    global _default_runner
    _default_runner = runner


def get_default_runner_status() -> dict[str, Any]:
    if _default_runner is None:
        return RunnerSnapshot(enabled=False).as_dict()
    return _default_runner.status()
