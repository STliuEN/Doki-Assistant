from __future__ import annotations

# Imports below the path bootstrap are intentional for direct script execution.
# ruff: noqa: E402
import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Direct script execution starts with ``backend/scripts`` on ``sys.path``.
# Add the backend root before importing the sibling application package.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import func, select, text

from app.db.uow import SqlUnitOfWork
from app.jobs.config import JobRuntimeConfig
from app.jobs.e2_runtime import E2RunnerRuntime, build_e2_runner
from app.jobs.repository import JobBackpressureError, JobConflictError, JobRepository
from app.jobs.runner import JobHandlerContext, JobHandlerError
from app.models.job_domain import AuditEvent, Job, JobAttempt
from scripts.backup_restore import BackupRestoreError, write_json_artifact


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps({"at": _now(), **event}, sort_keys=True) + "\n")


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Hard-stop only the probe process and its interpreter children."""

    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    else:
        process.kill()
    process.wait(timeout=10)


def _environment(database_url: str, approval_token: str, preflight_file: Path) -> dict[str, str]:
    return {
        "E2_RUNNER_ENABLED": "true",
        "E2_MIGRATION_ENABLED": "I_UNDERSTAND_E2_MIGRATION",
        "E2_DATABASE_URL": database_url,
        "E2_APPROVAL_TOKEN": approval_token,
        "E2_PREFLIGHT_FILE": str(preflight_file.resolve()),
        "JOB_LEASE_SECONDS": "6",
        "JOB_HEARTBEAT_SECONDS": "1",
        "JOB_POLL_SECONDS": "0.2",
        "JOB_SHUTDOWN_DRAIN_SECONDS": "5",
        "JOB_GLOBAL_BACKPRESSURE": "100",
        "JOB_OWNER_TYPE_BACKPRESSURE": "100",
    }


async def _job_snapshot(factory: Any, job_id: str) -> dict[str, Any]:
    async with factory() as session:
        job = await session.get(Job, job_id)
        if job is None:
            raise RuntimeError(f"live probe job disappeared: {job_id}")
        attempts = (
            await session.execute(
                select(JobAttempt)
                .where(JobAttempt.job_id == job_id)
                .order_by(JobAttempt.attempt_number)
            )
        ).scalars()
        return {
            "id": str(job.id),
            "job_type": str(job.job_type),
            "status": str(job.status),
            "attempt_count": int(job.attempt_count),
            "fencing_token": int(job.fencing_token),
            "lease_owner": job.lease_owner,
            "error_code": job.error_code,
            "result_json": job.result_json,
            "attempts": [
                {
                    "attempt_number": int(attempt.attempt_number),
                    "lease_owner": attempt.lease_owner,
                    "fencing_token": int(attempt.fencing_token),
                    "outcome": attempt.outcome,
                    "error_code": attempt.error_code,
                }
                for attempt in attempts
            ],
        }


async def _wait_for_status(factory: Any, job_id: str, expected: set[str], timeout: float = 40) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        latest = await _job_snapshot(factory, job_id)
        if latest["status"] in expected:
            return latest
        await asyncio.sleep(0.2)
    raise RuntimeError(f"job {job_id} did not reach {sorted(expected)}: {latest}")


async def _enqueue(
    factory: Any,
    *,
    config: JobRuntimeConfig,
    job_type: str,
    owner_scope_id: str,
    idempotency_key: str,
    value: str,
    priority: int = 0,
) -> tuple[str, bool]:
    async with SqlUnitOfWork(factory) as uow:
        repository = JobRepository(uow.require_session(), config)
        result = await repository.enqueue(
            job_type=job_type,
            owner_scope_type="e2-live",
            owner_scope_id=owner_scope_id,
            idempotency_key=idempotency_key,
            payload={"schema_version": 1, "value": value},
            payload_schema_version=1,
            priority=priority,
        )
        await uow.commit()
        return str(result.job.id), result.created


async def _dispose(runtime: E2RunnerRuntime) -> None:
    await runtime.runner.stop()
    await runtime.engine.dispose()


async def _wait_for_runner_lock_free(
    *,
    database_url: str,
    approval_token: str,
    preflight_file: Path,
    timeout: float = 20,
) -> None:
    """Wait until MySQL observes the killed worker's connection is gone."""

    runtime = build_e2_runner(
        environ=_environment(database_url, approval_token, preflight_file)
    )
    if runtime is None:
        raise RuntimeError("E2 runner was unexpectedly disabled while checking lock release")
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            async with runtime.engine.connect() as connection:
                free = await connection.scalar(text("SELECT IS_FREE_LOCK(:lock_name)"), {"lock_name": "doki-e2-sql-runner"})
            if int(free or 0) == 1:
                return
            await asyncio.sleep(0.2)
    finally:
        await runtime.engine.dispose()
    raise RuntimeError("MySQL did not release the E2 runner process lock after worker termination")


async def _run_kill_restart(
    *,
    database_url: str,
    approval_token: str,
    preflight_file: Path,
    prefix: str,
    root: Path,
) -> dict[str, Any]:
    runtime = build_e2_runner(
        environ=_environment(database_url, approval_token, preflight_file)
    )
    if runtime is None:
        raise RuntimeError("E2 runner was unexpectedly disabled")
    try:
        job_id, created = await _enqueue(
            runtime.runner.session_factory,
            config=runtime.runner.config,
            job_type="e2.restart.block",
            owner_scope_id=prefix,
            idempotency_key=f"{prefix}-restart",
            value="restart",
        )
    finally:
        await runtime.engine.dispose()
    if not created:
        raise RuntimeError("kill/restart fixture idempotency key already existed")

    event_file = root / "logs" / f"{prefix}-events.jsonl"
    stdout_file = root / "logs" / f"{prefix}-worker.log"
    event_file.unlink(missing_ok=True)
    worker = Path(__file__).resolve()
    worker_python = sys.executable

    def spawn(exit_on_success: bool) -> subprocess.Popen[bytes]:
        command = [
            worker_python,
            str(worker),
            "--mode",
            "worker",
            "--database-url",
            database_url,
            "--approval-token",
            approval_token,
            "--preflight-file",
            str(preflight_file.resolve()),
            "--event-file",
            str(event_file),
            "--job-id",
            job_id,
        ]
        if exit_on_success:
            command.append("--exit-on-success")
        with stdout_file.open("ab") as stream:
            return subprocess.Popen(command, cwd=str(worker.parents[1]), stdout=stream, stderr=stream)

    first = spawn(False)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        events = _read_events(event_file)
        if any(event.get("event") == "handler_started" and event.get("attempt") == 1 for event in events):
            break
        if first.poll() is not None:
            raise RuntimeError(f"first runner exited before claim: {first.returncode}")
        await asyncio.sleep(0.2)
    else:
        _terminate_process_tree(first)
        raise RuntimeError("first runner did not reach handler_started")

    runtime_after_kill = build_e2_runner(
        environ=_environment(database_url, approval_token, preflight_file)
    )
    if runtime_after_kill is None:
        raise RuntimeError("E2 runner was unexpectedly disabled after kill")
    try:
        running_snapshot = await _job_snapshot(runtime_after_kill.runner.session_factory, job_id)
    finally:
        await runtime_after_kill.engine.dispose()
    _terminate_process_tree(first)
    await _wait_for_runner_lock_free(
        database_url=database_url,
        approval_token=approval_token,
        preflight_file=preflight_file,
    )

    await asyncio.sleep(7)
    runtime_before_restart = build_e2_runner(
        environ=_environment(database_url, approval_token, preflight_file)
    )
    if runtime_before_restart is None:
        raise RuntimeError("E2 runner was unexpectedly disabled before restart")
    try:
        still_running = await _job_snapshot(runtime_before_restart.runner.session_factory, job_id)
    finally:
        await runtime_before_restart.engine.dispose()

    second = spawn(True)
    second_deadline = time.monotonic() + 30
    while time.monotonic() < second_deadline:
        if second.poll() is not None:
            break
        await asyncio.sleep(0.2)
    if second.poll() is None:
        _terminate_process_tree(second)
        raise RuntimeError("restarted runner did not finish the recovered job")
    if second.returncode != 0:
        raise RuntimeError(f"restarted runner exited with {second.returncode}")

    runtime_final = build_e2_runner(
        environ=_environment(database_url, approval_token, preflight_file)
    )
    if runtime_final is None:
        raise RuntimeError("E2 runner was unexpectedly disabled after restart")
    try:
        final_snapshot = await _job_snapshot(runtime_final.runner.session_factory, job_id)
    finally:
        await runtime_final.engine.dispose()
    return {
        "job_id": job_id,
        "first_process_exit": first.returncode,
        "second_process_exit": second.returncode,
        "running_after_claim": running_snapshot,
        "still_running_after_lease_wait": still_running,
        "final": final_snapshot,
        "events": _read_events(event_file),
        "event_file": str(event_file),
        "worker_log": str(stdout_file),
    }


async def run_worker(args: argparse.Namespace) -> int:
    if args.event_file is None or args.job_id is None:
        raise ValueError("worker mode requires --event-file and --job-id")
    runtime = build_e2_runner(
        environ=_environment(args.database_url, args.approval_token, args.preflight_file)
    )
    if runtime is None:
        raise RuntimeError("E2 runner was unexpectedly disabled")

    attempt_two_started = asyncio.Event()

    async def restart_handler(_payload: dict[str, Any], context: JobHandlerContext) -> dict[str, Any]:
        _append_event(
            args.event_file,
            {
                "event": "handler_started",
                "job_id": context.job_id,
                "attempt": context.attempt_number,
                "fencing_token": context.fencing_token,
            },
        )
        if context.attempt_number >= 2:
            attempt_two_started.set()
        if context.attempt_number == 1:
            await asyncio.Event().wait()
        return {"schema_version": 1, "attempt": context.attempt_number}

    runtime.runner.registry.register("e2.restart.block", restart_handler)
    try:
        await runtime.start()
        _append_event(args.event_file, {"event": "runner_started", "status": runtime.runner.status()["status"]})
        # The runner's pool has one connection reserved for GET_LOCK and one
        # for claim/transition work.  Polling the job through that same pool
        # can starve claim indefinitely, so observe lifecycle and completion
        # through in-memory runner state and the target handler event instead.
        if args.exit_on_success:
            try:
                await asyncio.wait_for(attempt_two_started.wait(), timeout=60)
            except TimeoutError as exc:
                snapshot = runtime.runner.status()
                raise RuntimeError(f"restarted runner did not start attempt two: {snapshot}") from exc
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                snapshot = runtime.runner.status()
                if snapshot["status"] == "failed":
                    raise RuntimeError(f"E2 runner failed: {snapshot.get('last_error')}")
                if snapshot["succeeded_count"] >= 1 and snapshot["active_job_id"] is None:
                    break
                await asyncio.sleep(0.1)
            else:
                raise RuntimeError(f"restarted runner did not commit attempt two: {runtime.runner.status()}")
        else:
            while True:
                snapshot = runtime.runner.status()
                if snapshot["status"] == "failed":
                    raise RuntimeError(f"E2 runner failed: {snapshot.get('last_error')}")
                await asyncio.sleep(0.2)
    finally:
        await _dispose(runtime)
    return 0


async def run_probe(args: argparse.Namespace) -> dict[str, Any]:
    # The probe output lives at ``artifacts/<kind>/...``; sibling worker logs
    # must remain inside this batch's evidence directory.
    root = args.output.resolve().parent.parent
    prefix = f"e2-live-{int(time.time())}"
    runtime = build_e2_runner(
        environ=_environment(args.database_url, args.approval_token, args.preflight_file)
    )
    if runtime is None:
        raise RuntimeError("E2 runner was unexpectedly disabled")
    factory = runtime.runner.session_factory
    config = runtime.runner.config
    retry_calls = 0
    cancel_started = asyncio.Event()
    cancel_release = asyncio.Event()

    async def retry_handler(_payload: dict[str, Any], _context: JobHandlerContext) -> dict[str, Any]:
        nonlocal retry_calls
        retry_calls += 1
        if retry_calls == 1:
            raise JobHandlerError("synthetic_retry", "first attempt intentionally failed")
        return {"schema_version": 1, "retry": "succeeded", "attempt": retry_calls}

    async def cancel_handler(_payload: dict[str, Any], _context: JobHandlerContext) -> dict[str, Any]:
        cancel_started.set()
        await cancel_release.wait()
        return {"schema_version": 1, "cancel": "should-not-commit"}

    runtime.runner.registry.register("e2.live.retry", retry_handler)
    runtime.runner.registry.register("e2.live.cancel", cancel_handler)
    try:
        echo_id, _ = await _enqueue(
            factory,
            config=config,
            job_type="e2.echo",
            owner_scope_id=prefix,
            idempotency_key=f"{prefix}-echo",
            value="live-echo",
        )
        duplicate_id, duplicate_created = await _enqueue(
            factory,
            config=config,
            job_type="e2.echo",
            owner_scope_id=prefix,
            idempotency_key=f"{prefix}-echo",
            value="live-echo",
        )
        conflict_error = None
        try:
            await _enqueue(
                factory,
                config=config,
                job_type="e2.echo",
                owner_scope_id=prefix,
                idempotency_key=f"{prefix}-echo",
                value="different-payload",
            )
        except JobConflictError as exc:
            conflict_error = str(exc)
        if duplicate_id != echo_id or duplicate_created or conflict_error is None:
            raise RuntimeError("live idempotency contract did not hold")

        unknown_id, _ = await _enqueue(
            factory,
            config=config,
            job_type="e2.live.unknown",
            owner_scope_id=prefix,
            idempotency_key=f"{prefix}-unknown",
            value="unknown",
        )
        retry_id, _ = await _enqueue(
            factory,
            config=config,
            job_type="e2.live.retry",
            owner_scope_id=prefix,
            idempotency_key=f"{prefix}-retry",
            value="retry",
        )
        cancel_id, _ = await _enqueue(
            factory,
            config=config,
            job_type="e2.live.cancel",
            owner_scope_id=prefix,
            idempotency_key=f"{prefix}-cancel",
            value="cancel",
        )

        await runtime.start()
        deadline = time.monotonic() + 10
        while runtime.runner.status()["status"] != "running" and time.monotonic() < deadline:
            if runtime.runner.status()["status"] == "failed":
                raise RuntimeError(f"live runner failed to acquire lock: {runtime.runner.status()}")
            await asyncio.sleep(0.1)
        if runtime.runner.status()["status"] != "running":
            raise RuntimeError(f"live runner did not start: {runtime.runner.status()}")

        echo_snapshot = await _wait_for_status(factory, echo_id, {"succeeded"})
        unknown_snapshot = await _wait_for_status(factory, unknown_id, {"dead_letter"})
        await asyncio.wait_for(cancel_started.wait(), timeout=20)
        async with SqlUnitOfWork(factory) as uow:
            cancelled = await JobRepository(uow.require_session(), config).cancel(
                job_id=cancel_id,
                reason="synthetic live cancellation",
            )
            await uow.commit()
        cancel_release.set()
        cancel_snapshot = await _wait_for_status(factory, cancel_id, {"cancelled"})
        retry_snapshot = await _wait_for_status(factory, retry_id, {"succeeded"}, timeout=30)
        runner_snapshot = runtime.runner.status()
    finally:
        await _dispose(runtime)

    lock_a = build_e2_runner(environ=_environment(args.database_url, args.approval_token, args.preflight_file))
    lock_b = build_e2_runner(environ=_environment(args.database_url, args.approval_token, args.preflight_file))
    if lock_a is None or lock_b is None:
        raise RuntimeError("lock probe could not build two E2 runtimes")
    try:
        await lock_a.start()
        deadline = time.monotonic() + 10
        while lock_a.runner.status()["status"] != "running" and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        await lock_b.start()
        deadline = time.monotonic() + 10
        while lock_b.runner.status()["status"] not in {"failed", "running"} and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        lock_snapshot = {"first": lock_a.runner.status(), "second": lock_b.runner.status()}
    finally:
        await _dispose(lock_b)
        await _dispose(lock_a)

    fence_runtime = build_e2_runner(environ=_environment(args.database_url, args.approval_token, args.preflight_file))
    if fence_runtime is None:
        raise RuntimeError("fencing probe could not build an E2 runtime")
    try:
        fence_id, _ = await _enqueue(
            fence_runtime.runner.session_factory,
            config=fence_runtime.runner.config,
            job_type="e2.echo",
            owner_scope_id=prefix,
            idempotency_key=f"{prefix}-fence",
            value="fence",
            priority=1000,
        )
        claim_time = datetime.now(UTC)
        async with SqlUnitOfWork(fence_runtime.runner.session_factory) as uow:
            claim_a = await JobRepository(uow.require_session(), config).claim_one(
                lease_owner="e2-fence-a",
                now=claim_time,
            )
            if claim_a is None or str(claim_a.job.id) != fence_id:
                raise RuntimeError("live fencing probe did not claim the expected job")
            await uow.commit()
        async with fence_runtime.runner.session_factory() as session:
            await session.execute(
                text("UPDATE jobs SET lease_expires_at = UTC_TIMESTAMP(6) - INTERVAL 60 SECOND WHERE id = :job_id"),
                {"job_id": fence_id},
            )
            await session.commit()
        recovery_time = claim_time + timedelta(seconds=2)
        async with SqlUnitOfWork(fence_runtime.runner.session_factory) as uow:
            repository = JobRepository(uow.require_session(), config)
            recovered = await repository.recover_expired(now=recovery_time)
            claim_b = await repository.claim_one(
                lease_owner="e2-fence-b",
                now=recovery_time + timedelta(seconds=6),
            )
            if claim_b is None:
                raise RuntimeError("live fencing probe did not reclaim the expired job")
            await uow.commit()
        transition_time = recovery_time + timedelta(seconds=7)
        async with SqlUnitOfWork(fence_runtime.runner.session_factory) as uow:
            repository = JobRepository(uow.require_session(), config)
            stale = await repository.succeed(
                job_id=fence_id,
                lease_owner="e2-fence-a",
                fencing_token=int(claim_a.attempt.fencing_token),
                result_payload={"schema_version": 1, "stale": True},
                result_schema_version=1,
                now=transition_time,
            )
            started = await repository.start(
                job_id=fence_id,
                lease_owner="e2-fence-b",
                fencing_token=int(claim_b.attempt.fencing_token),
                now=transition_time,
            )
            succeeded = await repository.succeed(
                job_id=fence_id,
                lease_owner="e2-fence-b",
                fencing_token=int(claim_b.attempt.fencing_token),
                result_payload={"schema_version": 1, "fenced": "accepted"},
                result_schema_version=1,
                now=transition_time,
            )
            await uow.commit()
        fence_snapshot = await _job_snapshot(fence_runtime.runner.session_factory, fence_id)

        pressure_config = JobRuntimeConfig(global_backpressure=1, owner_type_backpressure=1)
        pressure_first_id = None
        pressure_error = None
        async with SqlUnitOfWork(fence_runtime.runner.session_factory) as uow:
            repository = JobRepository(uow.require_session(), pressure_config)
            first = await repository.enqueue(
                job_type="e2.live.pressure",
                owner_scope_type="e2-pressure",
                owner_scope_id=prefix,
                idempotency_key=f"{prefix}-pressure-1",
                payload={"schema_version": 1, "value": "one"},
                payload_schema_version=1,
            )
            pressure_first_id = str(first.job.id)
            try:
                await repository.enqueue(
                    job_type="e2.live.pressure",
                    owner_scope_type="e2-pressure",
                    owner_scope_id=prefix,
                    idempotency_key=f"{prefix}-pressure-2",
                    payload={"schema_version": 1, "value": "two"},
                    payload_schema_version=1,
                )
            except JobBackpressureError as exc:
                pressure_error = str(exc)
            await repository.cancel(job_id=pressure_first_id, reason="synthetic backpressure cleanup")
            await uow.commit()
        if pressure_error is None:
            raise RuntimeError("live SQL backpressure did not reject the second job")
        pressure_snapshot = await _job_snapshot(fence_runtime.runner.session_factory, pressure_first_id)
    finally:
        await fence_runtime.engine.dispose()

    restart = await _run_kill_restart(
        database_url=args.database_url,
        approval_token=args.approval_token,
        preflight_file=args.preflight_file,
        prefix=f"{prefix}-restart",
        root=root,
    )

    job_ids = [echo_id, unknown_id, retry_id, cancel_id, fence_id, pressure_first_id, restart["job_id"]]
    final_runtime = build_e2_runner(environ=_environment(args.database_url, args.approval_token, args.preflight_file))
    if final_runtime is None:
        raise RuntimeError("final evidence runtime could not be built")
    try:
        async with final_runtime.runner.session_factory() as session:
            counts = {
                "jobs": int(await session.scalar(select(func.count(Job.id))) or 0),
                "attempts": int(await session.scalar(select(func.count(JobAttempt.id))) or 0),
                "audit_events": int(await session.scalar(select(func.count(AuditEvent.id))) or 0),
            }
            audit_actions = [
                str(value)
                for value in (
                    await session.execute(
                        select(AuditEvent.action)
                        .where(AuditEvent.job_id.in_(job_ids))
                        .order_by(AuditEvent.created_at, AuditEvent.id)
                    )
                ).scalars()
            ]
    finally:
        await final_runtime.engine.dispose()

    return {
        "schema_version": 1,
        "operation": "e2-live-runner-probe",
        "target": {"host": "127.0.0.1", "port": 33317, "database": "doki_e2", "role": "source"},
        "prefix": prefix,
        "idempotency": {
            "original_job_id": echo_id,
            "duplicate_job_id": duplicate_id,
            "duplicate_created": duplicate_created,
            "conflict_error": conflict_error,
        },
        "runner": {
            "snapshot_after_matrix": runner_snapshot,
            "process_lock": lock_snapshot,
            "concurrency": 1,
        },
        "matrix": {
            "echo": echo_snapshot,
            "unknown_dead_letter": unknown_snapshot,
            "retry": retry_snapshot,
            "cancel": {"request": cancelled.status, "final": cancel_snapshot},
            "fencing": {
                "recovered": recovered,
                "old_claim_token": int(claim_a.attempt.fencing_token),
                "new_claim_token": int(claim_b.attempt.fencing_token),
                "stale_transition_accepted": stale.accepted,
                "stale_transition_reason": stale.reason,
                "new_start_accepted": started.accepted,
                "new_success_accepted": succeeded.accepted,
                "final": fence_snapshot,
            },
            "backpressure": {"error": pressure_error, "cleanup": pressure_snapshot},
            "kill_restart": restart,
        },
        "database_counts_after_probe": counts,
        "audit_actions_for_probe_jobs": audit_actions,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the approved E2 MySQL runner conformance probe.")
    parser.add_argument("--mode", choices=("probe", "worker"), default="probe")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--approval-token", required=True)
    parser.add_argument("--preflight-file", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--event-file", type=Path)
    parser.add_argument("--job-id")
    parser.add_argument("--exit-on-success", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.mode == "worker":
            return asyncio.run(run_worker(args))
        if args.output is None:
            raise ValueError("probe mode requires --output")
        evidence = asyncio.run(run_probe(args))
        write_json_artifact(evidence, args.output)
        print(f"e2-live-runner-probe verified: path={args.output} prefix={evidence['prefix']}")
        return 0
    except (BackupRestoreError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
        print(f"e2 live probe failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
