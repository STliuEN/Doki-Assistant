from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.config import JobRuntimeConfig
from app.models.job_domain import TERMINAL_JOB_STATUSES, AuditEvent, Job, JobAttempt


class JobValidationError(ValueError):
    pass


class JobConflictError(RuntimeError):
    pass


class JobBackpressureError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    job: Job
    created: bool


@dataclass(frozen=True, slots=True)
class ClaimResult:
    job: Job
    attempt: JobAttempt


@dataclass(frozen=True, slots=True)
class TransitionResult:
    accepted: bool
    status: str | None
    reason: str | None = None


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise JobValidationError("job JSON must be deterministic and JSON-serializable") from exc
    return rendered.encode("utf-8")


def payload_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


class JobRepository:
    def __init__(self, session: AsyncSession, config: JobRuntimeConfig | None = None) -> None:
        self.session = session
        self.config = config or JobRuntimeConfig()

    async def _database_now(self) -> datetime:
        value = await self.session.scalar(select(func.current_timestamp()))
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, bytes):
            parsed = self._parse_database_timestamp(value.decode("utf-8", errors="strict"))
        elif isinstance(value, str):
            parsed = self._parse_database_timestamp(value)
        else:
            raise RuntimeError("database did not return a timestamp")
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _parse_database_timestamp(value: str) -> datetime:
        normalized = value.strip().replace(" ", "T", 1)
        try:
            return datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise RuntimeError("database returned an invalid timestamp") from exc

    @staticmethod
    def _required_text(value: str, field: str, maximum: int) -> str:
        if not isinstance(value, str) or not value or len(value) > maximum:
            raise JobValidationError(f"{field} must be a non-empty string of at most {maximum} characters")
        return value

    @staticmethod
    def _versioned_json(value: Mapping[str, Any], schema_version: int, field: str, maximum: int) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise JobValidationError(f"{field} must be a JSON object")
        if not isinstance(schema_version, int) or schema_version <= 0:
            raise JobValidationError(f"{field} schema version must be positive")
        if value.get("schema_version") != schema_version:
            raise JobValidationError(f"{field} schema_version does not match the declared version")
        normalized = dict(value)
        if len(canonical_json_bytes(normalized)) > maximum:
            raise JobValidationError(f"{field} exceeds the {maximum}-byte UTF-8 limit")
        return normalized

    async def _existing_job(
        self,
        *,
        job_type: str,
        owner_scope_type: str,
        owner_scope_id: str,
        idempotency_key: str,
    ) -> Job | None:
        result = await self.session.execute(
            select(Job).where(
                Job.job_type == job_type,
                Job.owner_scope_type == owner_scope_type,
                Job.owner_scope_id == owner_scope_id,
                Job.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    async def _check_backpressure(self, *, job_type: str, owner_scope_type: str, owner_scope_id: str) -> None:
        active = ~Job.status.in_(TERMINAL_JOB_STATUSES)
        global_count = int(await self.session.scalar(select(func.count(Job.id)).where(active)) or 0)
        if global_count >= self.config.global_backpressure:
            raise JobBackpressureError("global SQL job backlog limit reached")
        owner_count = int(
            await self.session.scalar(
                select(func.count(Job.id)).where(
                    active,
                    Job.job_type == job_type,
                    Job.owner_scope_type == owner_scope_type,
                    Job.owner_scope_id == owner_scope_id,
                )
            )
            or 0
        )
        if owner_count >= self.config.owner_type_backpressure:
            raise JobBackpressureError("owner/job-type SQL backlog limit reached")

    def append_audit(
        self,
        *,
        action: str,
        target_type: str,
        reason: str,
        result: str,
        correlation_id: str,
        job_id: str | None = None,
        target_id: str | None = None,
        actor_type: str = "system",
        actor_id: str | None = None,
        scope_type: str | None = None,
        scope_id: str | None = None,
        before: Mapping[str, Any] | None = None,
        after: Mapping[str, Any] | None = None,
        error_code: str | None = None,
    ) -> AuditEvent:
        reason_bytes = reason.encode("utf-8")
        if not reason or len(reason_bytes) > self.config.audit_reason_max_bytes:
            raise JobValidationError("audit reason is empty or exceeds its UTF-8 byte limit")
        total_json_bytes = sum(len(canonical_json_bytes(item)) for item in (before, after) if item is not None)
        if total_json_bytes > self.config.audit_json_max_bytes:
            raise JobValidationError("audit JSON exceeds its UTF-8 byte limit")
        event = AuditEvent(
            actor_type=self._required_text(actor_type, "actor_type", 32),
            actor_id=actor_id,
            action=self._required_text(action, "action", 128),
            target_type=self._required_text(target_type, "target_type", 64),
            target_id=target_id,
            scope_type=scope_type,
            scope_id=scope_id,
            before_json=dict(before) if before is not None else None,
            after_json=dict(after) if after is not None else None,
            reason=reason,
            result=self._required_text(result, "result", 32),
            error_code=error_code,
            correlation_id=correlation_id,
            job_id=job_id,
        )
        self.session.add(event)
        return event

    async def enqueue(
        self,
        *,
        job_type: str,
        owner_scope_type: str,
        owner_scope_id: str,
        idempotency_key: str,
        payload: Mapping[str, Any],
        payload_schema_version: int,
        correlation_id: str | None = None,
        priority: int = 0,
        available_at: datetime | None = None,
        max_attempts: int | None = None,
        replay_of_job_id: str | None = None,
    ) -> EnqueueResult:
        job_type = self._required_text(job_type, "job_type", 128)
        owner_scope_type = self._required_text(owner_scope_type, "owner_scope_type", 32)
        owner_scope_id = self._required_text(owner_scope_id, "owner_scope_id", 64)
        idempotency_key = self._required_text(idempotency_key, "idempotency_key", 128)
        normalized_payload = self._versioned_json(
            payload,
            payload_schema_version,
            "payload",
            self.config.payload_max_bytes,
        )
        digest = payload_digest(normalized_payload)
        existing = await self._existing_job(
            job_type=job_type,
            owner_scope_type=owner_scope_type,
            owner_scope_id=owner_scope_id,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            if existing.payload_digest != digest:
                raise JobConflictError("idempotency key already exists with a different payload digest")
            return EnqueueResult(job=existing, created=False)

        await self._check_backpressure(
            job_type=job_type,
            owner_scope_type=owner_scope_type,
            owner_scope_id=owner_scope_id,
        )
        attempts = max_attempts if max_attempts is not None else self.config.max_attempts
        if attempts != self.config.max_attempts:
            raise JobValidationError("E2 jobs must use the frozen maximum attempt count")
        job = Job(
            job_type=job_type,
            owner_scope_type=owner_scope_type,
            owner_scope_id=owner_scope_id,
            correlation_id=correlation_id or str(uuid4()),
            idempotency_key=idempotency_key,
            payload_digest=digest,
            payload_json=normalized_payload,
            payload_schema_version=payload_schema_version,
            priority=int(priority),
            available_at=available_at or await self._database_now(),
            max_attempts=attempts,
            replay_of_job_id=replay_of_job_id,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(job)
                await self.session.flush()
        except IntegrityError:
            existing = await self._existing_job(
                job_type=job_type,
                owner_scope_type=owner_scope_type,
                owner_scope_id=owner_scope_id,
                idempotency_key=idempotency_key,
            )
            if existing is None:
                raise
            if existing.payload_digest != digest:
                raise JobConflictError("idempotency key raced with a different payload digest") from None
            return EnqueueResult(job=existing, created=False)
        self.append_audit(
            action="job.enqueued",
            target_type="job",
            target_id=job.id,
            job_id=job.id,
            correlation_id=job.correlation_id,
            scope_type=owner_scope_type,
            scope_id=owner_scope_id,
            reason="durable job accepted",
            result="accepted",
            after={"status": "queued", "payload_digest": digest},
        )
        return EnqueueResult(job=job, created=True)

    async def _reject_fence(self, *, job_id: str, correlation_id: str, operation: str) -> TransitionResult:
        existing_job_id = await self.session.scalar(select(Job.id).where(Job.id == job_id))
        self.append_audit(
            action="job.fenced_rejected",
            target_type="job",
            target_id=job_id,
            job_id=str(existing_job_id) if existing_job_id is not None else None,
            correlation_id=correlation_id,
            reason=f"stale lease rejected during {operation}",
            result="rejected",
            error_code="stale_fencing_token",
        )
        return TransitionResult(False, None, "stale_fencing_token")

    async def recover_expired(self, *, now: datetime | None = None) -> int:
        checked_at = now or await self._database_now()
        result = await self.session.execute(
            select(Job)
            .where(
                Job.status.in_(("leased", "running", "cancel_requested")),
                Job.lease_expires_at <= checked_at,
            )
            .order_by(Job.lease_expires_at, Job.id)
            .with_for_update(skip_locked=True)
        )
        jobs = tuple(result.scalars())
        for job in jobs:
            attempt = await self._attempt(job.id, int(job.attempt_count))
            if attempt is not None:
                attempt.finished_at = checked_at
                attempt.outcome = "abandoned"
                attempt.error_code = "lease_expired"
            old_status = job.status
            job.lease_owner = None
            job.lease_expires_at = None
            job.heartbeat_at = None
            if old_status == "cancel_requested":
                job.status = "cancelled"
                job.cancelled_at = checked_at
                job.completed_at = checked_at
            elif int(job.attempt_count) >= int(job.max_attempts):
                job.status = "dead_letter"
                job.completed_at = checked_at
                job.error_code = "lease_expired"
            else:
                job.status = "retry_wait"
                job.available_at = checked_at + timedelta(seconds=self._retry_delay(int(job.attempt_count)))
                job.error_code = "lease_expired"
            self.append_audit(
                action="job.lease_expired",
                target_type="job",
                target_id=job.id,
                job_id=job.id,
                correlation_id=job.correlation_id,
                reason="lease expired and SQL state was recovered",
                result=job.status,
                before={"status": old_status, "fencing_token": job.fencing_token},
                after={"status": job.status},
                error_code="lease_expired",
            )
        await self.session.flush()
        return len(jobs)

    def _retry_delay(self, attempt_number: int) -> int:
        index = min(max(attempt_number - 1, 0), len(self.config.retry_delays_seconds) - 1)
        return self.config.retry_delays_seconds[index]

    async def claim_one(self, *, lease_owner: str, now: datetime | None = None) -> ClaimResult | None:
        lease_owner = self._required_text(lease_owner, "lease_owner", 128)
        checked_at = now or await self._database_now()
        await self.recover_expired(now=checked_at)
        result = await self.session.execute(
            select(Job)
            .where(
                Job.status.in_(("queued", "retry_wait")),
                Job.available_at <= checked_at,
                Job.cancel_requested_at.is_(None),
            )
            .order_by(Job.priority.desc(), Job.available_at, Job.created_at, Job.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return None
        job.status = "leased"
        job.attempt_count = int(job.attempt_count) + 1
        job.fencing_token = int(job.fencing_token) + 1
        job.lease_owner = lease_owner
        job.heartbeat_at = checked_at
        job.lease_expires_at = checked_at + timedelta(seconds=self.config.lease_seconds)
        attempt = JobAttempt(
            job_id=job.id,
            attempt_number=job.attempt_count,
            lease_owner=lease_owner,
            fencing_token=job.fencing_token,
            started_at=checked_at,
            heartbeat_at=checked_at,
            outcome="leased",
            worker_metadata_json={"schema_version": 1},
        )
        self.session.add(attempt)
        self.append_audit(
            action="job.claimed",
            target_type="job",
            target_id=job.id,
            job_id=job.id,
            correlation_id=job.correlation_id,
            reason="runner acquired SQL lease",
            result="leased",
            after={"attempt": job.attempt_count, "fencing_token": job.fencing_token},
        )
        await self.session.flush()
        return ClaimResult(job=job, attempt=attempt)

    async def _attempt(self, job_id: str, attempt_number: int) -> JobAttempt | None:
        result = await self.session.execute(
            select(JobAttempt).where(JobAttempt.job_id == job_id, JobAttempt.attempt_number == attempt_number)
        )
        return result.scalar_one_or_none()

    async def _job_correlation(self, job_id: str) -> str:
        correlation_id = await self.session.scalar(select(Job.correlation_id).where(Job.id == job_id))
        return str(correlation_id or uuid4())

    async def start(self, *, job_id: str, lease_owner: str, fencing_token: int, now: datetime | None = None) -> TransitionResult:
        checked_at = now or await self._database_now()
        statement = (
            update(Job)
            .where(
                Job.id == job_id,
                Job.status == "leased",
                Job.lease_owner == lease_owner,
                Job.fencing_token == fencing_token,
                Job.lease_expires_at > checked_at,
            )
            .values(status="running", heartbeat_at=checked_at, updated_at=checked_at)
        )
        result = await self.session.execute(statement)
        correlation_id = await self._job_correlation(job_id)
        if result.rowcount != 1:
            return await self._reject_fence(
                job_id=job_id,
                correlation_id=correlation_id,
                operation="start",
            )
        attempt = await self.session.scalar(
            select(JobAttempt).where(JobAttempt.job_id == job_id, JobAttempt.fencing_token == fencing_token)
        )
        if attempt is not None:
            attempt.outcome = "running"
        self.append_audit(
            action="job.started",
            target_type="job",
            target_id=job_id,
            job_id=job_id,
            correlation_id=correlation_id,
            reason="leased handler started",
            result="running",
            after={"fencing_token": fencing_token},
        )
        return TransitionResult(True, "running")

    async def heartbeat(
        self,
        *,
        job_id: str,
        lease_owner: str,
        fencing_token: int,
        now: datetime | None = None,
    ) -> TransitionResult:
        checked_at = now or await self._database_now()
        result = await self.session.execute(
            update(Job)
            .where(
                Job.id == job_id,
                Job.status.in_(("leased", "running", "cancel_requested")),
                Job.lease_owner == lease_owner,
                Job.fencing_token == fencing_token,
                Job.lease_expires_at > checked_at,
            )
            .values(
                heartbeat_at=checked_at,
                lease_expires_at=checked_at + timedelta(seconds=self.config.lease_seconds),
                updated_at=checked_at,
            )
        )
        if result.rowcount != 1:
            return await self._reject_fence(
                job_id=job_id,
                correlation_id=await self._job_correlation(job_id),
                operation="heartbeat",
            )
        await self.session.execute(
            update(JobAttempt)
            .where(JobAttempt.job_id == job_id, JobAttempt.fencing_token == fencing_token)
            .values(heartbeat_at=checked_at)
        )
        return TransitionResult(True, "running")

    async def cancellation_requested(self, *, job_id: str, lease_owner: str, fencing_token: int) -> bool:
        status = await self.session.scalar(
            select(Job.status).where(
                Job.id == job_id,
                Job.lease_owner == lease_owner,
                Job.fencing_token == fencing_token,
            )
        )
        if status is None:
            return True
        return status == "cancel_requested"

    async def succeed(
        self,
        *,
        job_id: str,
        lease_owner: str,
        fencing_token: int,
        result_payload: Mapping[str, Any],
        result_schema_version: int,
        now: datetime | None = None,
    ) -> TransitionResult:
        normalized_result = self._versioned_json(
            result_payload,
            result_schema_version,
            "result",
            self.config.result_max_bytes,
        )
        checked_at = now or await self._database_now()
        result = await self.session.execute(
            update(Job)
            .where(
                Job.id == job_id,
                Job.status == "running",
                Job.lease_owner == lease_owner,
                Job.fencing_token == fencing_token,
                Job.lease_expires_at > checked_at,
            )
            .values(
                status="succeeded",
                result_json=normalized_result,
                result_schema_version=result_schema_version,
                completed_at=checked_at,
                lease_owner=None,
                lease_expires_at=None,
                heartbeat_at=None,
                error_code=None,
                error_detail=None,
                updated_at=checked_at,
            )
        )
        correlation_id = await self._job_correlation(job_id)
        if result.rowcount != 1:
            return await self._reject_fence(
                job_id=job_id,
                correlation_id=correlation_id,
                operation="succeed",
            )
        await self.session.execute(
            update(JobAttempt)
            .where(JobAttempt.job_id == job_id, JobAttempt.fencing_token == fencing_token)
            .values(outcome="succeeded", finished_at=checked_at)
        )
        self.append_audit(
            action="job.succeeded",
            target_type="job",
            target_id=job_id,
            job_id=job_id,
            correlation_id=correlation_id,
            reason="handler result committed with matching fence",
            result="succeeded",
            after={"fencing_token": fencing_token, "result_digest": payload_digest(normalized_result)},
        )
        return TransitionResult(True, "succeeded")

    def _bounded_error(self, value: str) -> str:
        encoded = str(value).encode("utf-8")
        if len(encoded) <= self.config.error_detail_max_bytes:
            return str(value)
        return encoded[: self.config.error_detail_max_bytes].decode("utf-8", errors="ignore")

    async def fail(
        self,
        *,
        job_id: str,
        lease_owner: str,
        fencing_token: int,
        error_code: str,
        error_detail: str,
        permanent: bool,
        now: datetime | None = None,
    ) -> TransitionResult:
        checked_at = now or await self._database_now()
        result = await self.session.execute(
            select(Job)
            .where(
                Job.id == job_id,
                Job.status.in_(("running", "cancel_requested")),
                Job.lease_owner == lease_owner,
                Job.fencing_token == fencing_token,
                Job.lease_expires_at > checked_at,
            )
            .with_for_update()
        )
        job = result.scalar_one_or_none()
        correlation_id = await self._job_correlation(job_id)
        if job is None:
            return await self._reject_fence(
                job_id=job_id,
                correlation_id=correlation_id,
                operation="fail",
            )
        if job.status == "cancel_requested":
            next_status = "cancelled"
            job.cancelled_at = checked_at
            job.completed_at = checked_at
        elif permanent or int(job.attempt_count) >= int(job.max_attempts):
            next_status = "dead_letter"
            job.completed_at = checked_at
        else:
            next_status = "retry_wait"
            job.available_at = checked_at + timedelta(seconds=self._retry_delay(int(job.attempt_count)))
        job.status = next_status
        job.error_code = self._required_text(error_code, "error_code", 64)
        job.error_detail = self._bounded_error(error_detail)
        job.lease_owner = None
        job.lease_expires_at = None
        job.heartbeat_at = None
        attempt = await self._attempt(job.id, int(job.attempt_count))
        if attempt is not None:
            attempt.outcome = next_status
            attempt.error_code = job.error_code
            attempt.error_detail = job.error_detail
            attempt.finished_at = checked_at
        self.append_audit(
            action=f"job.{next_status}",
            target_type="job",
            target_id=job.id,
            job_id=job.id,
            correlation_id=correlation_id,
            reason="handler failure resolved by retry policy",
            result=next_status,
            error_code=job.error_code,
            after={"attempt": job.attempt_count, "fencing_token": fencing_token},
        )
        await self.session.flush()
        return TransitionResult(True, next_status)

    async def cancel(self, *, job_id: str, reason: str, now: datetime | None = None) -> TransitionResult:
        if not reason or len(reason.encode("utf-8")) > self.config.audit_reason_max_bytes:
            raise JobValidationError("cancel reason is empty or too large")
        checked_at = now or await self._database_now()
        result = await self.session.execute(select(Job).where(Job.id == job_id).with_for_update())
        job = result.scalar_one_or_none()
        if job is None:
            return TransitionResult(False, None, "not_found")
        previous = job.status
        if previous in TERMINAL_JOB_STATUSES:
            return TransitionResult(True, previous, "already_terminal")
        job.cancel_requested_at = checked_at
        job.cancel_reason = reason
        if previous in {"queued", "retry_wait"}:
            job.status = "cancelled"
            job.cancelled_at = checked_at
            job.completed_at = checked_at
        else:
            job.status = "cancel_requested"
        self.append_audit(
            action="job.cancel_requested" if job.status == "cancel_requested" else "job.cancelled",
            target_type="job",
            target_id=job.id,
            job_id=job.id,
            correlation_id=job.correlation_id,
            reason=reason,
            result=job.status,
            before={"status": previous},
            after={"status": job.status},
        )
        await self.session.flush()
        return TransitionResult(True, job.status)

    async def replay_dead_letter(
        self,
        *,
        job_id: str,
        idempotency_key: str,
        correlation_id: str | None = None,
    ) -> EnqueueResult:
        original = await self.session.get(Job, job_id)
        if original is None or original.status != "dead_letter":
            raise JobConflictError("only dead-letter jobs can be replayed")
        replay = await self.enqueue(
            job_type=original.job_type,
            owner_scope_type=original.owner_scope_type,
            owner_scope_id=original.owner_scope_id,
            idempotency_key=idempotency_key,
            payload=original.payload_json,
            payload_schema_version=original.payload_schema_version,
            correlation_id=correlation_id,
            priority=original.priority,
            replay_of_job_id=original.id,
        )
        if replay.created:
            self.append_audit(
                action="job.replayed",
                target_type="job",
                target_id=replay.job.id,
                job_id=replay.job.id,
                correlation_id=replay.job.correlation_id,
                reason="dead-letter replay created a distinct durable job",
                result="queued",
                before={"source_job_id": original.id},
                after={"replay_job_id": replay.job.id},
            )
        return replay
