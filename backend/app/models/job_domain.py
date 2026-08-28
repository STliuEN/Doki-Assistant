from __future__ import annotations

from uuid import uuid4

from sqlalchemy import JSON, BigInteger, CheckConstraint, Column, ForeignKey, Index, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.sql import func

from app.models.chat_history import Base
from app.models.foundation_types import DIGEST_PATTERN, DIGEST_TYPE, UTC_DATETIME, UUID_PATTERN, UUID_TYPE, ascii_string

JOB_STATUSES = (
    "queued",
    "leased",
    "running",
    "retry_wait",
    "cancel_requested",
    "succeeded",
    "cancelled",
    "dead_letter",
)
TERMINAL_JOB_STATUSES = frozenset({"succeeded", "cancelled", "dead_letter"})


def _uuid() -> str:
    return str(uuid4())


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_jobs_id_uuid"),
        CheckConstraint(f"payload_digest REGEXP '{DIGEST_PATTERN}'", name="ck_jobs_payload_digest"),
        CheckConstraint(f"status IN ({', '.join(repr(item) for item in JOB_STATUSES)})", name="ck_jobs_status"),
        CheckConstraint("attempt_count >= 0 AND max_attempts > 0 AND attempt_count <= max_attempts", name="ck_jobs_attempts"),
        CheckConstraint("fencing_token >= 0", name="ck_jobs_fencing_token"),
        UniqueConstraint(
            "job_type",
            "owner_scope_type",
            "owner_scope_id",
            "idempotency_key",
            name="uq_jobs_idempotency_scope",
        ),
        Index("ix_jobs_claim", "status", "available_at", "priority", "created_at", "id"),
        Index("ix_jobs_owner_status", "owner_scope_type", "owner_scope_id", "job_type", "status"),
        Index("ix_jobs_lease_expiry", "status", "lease_expires_at"),
        Index("ix_jobs_correlation", "correlation_id"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=_uuid)
    job_type = Column(ascii_string(128), nullable=False)
    owner_scope_type = Column(ascii_string(32), nullable=False)
    owner_scope_id = Column(ascii_string(64), nullable=False)
    correlation_id = Column(UUID_TYPE, nullable=False, default=_uuid)
    idempotency_key = Column(String(128, collation="utf8mb4_bin"), nullable=False)
    payload_digest = Column(DIGEST_TYPE, nullable=False)
    payload_json = Column(JSON, nullable=False)
    payload_schema_version = Column(Integer, nullable=False)
    status = Column(ascii_string(32), nullable=False, default="queued", server_default="queued")
    priority = Column(Integer, nullable=False, default=0, server_default="0")
    available_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())
    attempt_count = Column(Integer, nullable=False, default=0, server_default="0")
    max_attempts = Column(Integer, nullable=False, default=5, server_default="5")
    lease_owner = Column(ascii_string(128), nullable=True)
    lease_expires_at = Column(UTC_DATETIME, nullable=True)
    heartbeat_at = Column(UTC_DATETIME, nullable=True)
    fencing_token = Column(BigInteger, nullable=False, default=0, server_default="0")
    cancel_requested_at = Column(UTC_DATETIME, nullable=True)
    cancel_reason = Column(String(4096), nullable=True)
    cancelled_at = Column(UTC_DATETIME, nullable=True)
    result_json = Column(JSON, nullable=True)
    result_schema_version = Column(Integer, nullable=True)
    error_code = Column(ascii_string(64), nullable=True)
    error_detail = Column(Text, nullable=True)
    completed_at = Column(UTC_DATETIME, nullable=True)
    replay_of_job_id = Column(UUID_TYPE, ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=True)
    created_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())
    updated_at = Column(UTC_DATETIME, nullable=False, server_default=func.now(), onupdate=func.now())


class JobAttempt(Base):
    __tablename__ = "job_attempts"
    __table_args__ = (
        CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_job_attempts_id_uuid"),
        CheckConstraint("attempt_number > 0", name="ck_job_attempts_number"),
        CheckConstraint("fencing_token > 0", name="ck_job_attempts_fencing"),
        CheckConstraint(
            "outcome IN ('running', 'succeeded', 'retry_wait', 'cancelled', 'dead_letter', 'abandoned', 'fenced')",
            name="ck_job_attempts_outcome",
        ),
        UniqueConstraint("job_id", "attempt_number", name="uq_job_attempts_job_number"),
        Index("ix_job_attempts_job_started", "job_id", "started_at"),
        Index("ix_job_attempts_lease", "lease_owner", "fencing_token"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=_uuid)
    job_id = Column(UUID_TYPE, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    lease_owner = Column(ascii_string(128), nullable=False)
    fencing_token = Column(BigInteger, nullable=False)
    started_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())
    heartbeat_at = Column(UTC_DATETIME, nullable=True)
    finished_at = Column(UTC_DATETIME, nullable=True)
    outcome = Column(ascii_string(32), nullable=False, default="running", server_default="running")
    error_code = Column(ascii_string(64), nullable=True)
    error_detail = Column(Text, nullable=True)
    worker_metadata_json = Column(JSON, nullable=False, default=dict)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_audit_events_id_uuid"),
        Index("ix_audit_events_correlation_created", "correlation_id", "created_at"),
        Index("ix_audit_events_job_created", "job_id", "created_at"),
        Index("ix_audit_events_target_created", "target_type", "target_id", "created_at"),
        Index("ix_audit_events_actor_created", "actor_type", "actor_id", "created_at"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=_uuid)
    actor_type = Column(ascii_string(32), nullable=False)
    actor_id = Column(String(64), nullable=True)
    actor_role = Column(ascii_string(64), nullable=True)
    action = Column(ascii_string(128), nullable=False)
    target_type = Column(ascii_string(64), nullable=False)
    target_id = Column(String(64), nullable=True)
    scope_type = Column(ascii_string(32), nullable=True)
    scope_id = Column(String(64), nullable=True)
    policy_revision = Column(BigInteger, nullable=True)
    subject_revision = Column(BigInteger, nullable=True)
    content_digest = Column(DIGEST_TYPE, nullable=True)
    before_json = Column(JSON, nullable=True)
    after_json = Column(JSON, nullable=True)
    grant_diff_json = Column(JSON, nullable=True)
    reason = Column(String(4096), nullable=False)
    effective_at = Column(UTC_DATETIME, nullable=True)
    expires_at = Column(UTC_DATETIME, nullable=True)
    result = Column(ascii_string(32), nullable=False)
    error_code = Column(ascii_string(64), nullable=True)
    correlation_id = Column(UUID_TYPE, nullable=False)
    run_id = Column(String(64), nullable=True)
    job_id = Column(UUID_TYPE, ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=True)
    import_id = Column(String(64), nullable=True)
    migration_id = Column(String(64), nullable=True)
    created_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())


def _reject_mutation(_mapper, _connection, target) -> None:
    raise ValueError(f"{target.__tablename__} is append-only")


event.listen(AuditEvent, "before_update", _reject_mutation)
event.listen(AuditEvent, "before_delete", _reject_mutation)
