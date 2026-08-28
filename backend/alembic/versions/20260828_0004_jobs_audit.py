"""Add durable jobs and append-only audit events.

Revision ID: 20260828_0004_jobs_audit
Revises: 20260828_0003_identity_auth
"""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision = "20260828_0004_jobs_audit"
down_revision = "20260828_0003_identity_auth"
branch_labels = None
depends_on = None

UUID_PATTERN = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
DIGEST_PATTERN = "^[0-9a-f]{64}$"
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


def _ascii(length: int):
    return sa.String(length).with_variant(mysql.VARCHAR(length=length, charset="ascii", collation="ascii_bin"), "mysql")


def _uuid():
    return sa.String(36).with_variant(mysql.CHAR(length=36, charset="ascii", collation="ascii_bin"), "mysql")


def _digest():
    return sa.String(64).with_variant(mysql.CHAR(length=64, charset="ascii", collation="ascii_bin"), "mysql")


def _utc_datetime():
    return sa.DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=6), "mysql")


def _now():
    return sa.text("CURRENT_TIMESTAMP(6)")


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("job_type", _ascii(128), nullable=False),
        sa.Column("owner_scope_type", _ascii(32), nullable=False),
        sa.Column("owner_scope_id", _ascii(64), nullable=False),
        sa.Column("correlation_id", _uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128, collation="utf8mb4_bin"), nullable=False),
        sa.Column("payload_digest", _digest(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("payload_schema_version", sa.Integer(), nullable=False),
        sa.Column("status", _ascii(32), server_default="queued", nullable=False),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("available_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("lease_owner", _ascii(128), nullable=True),
        sa.Column("lease_expires_at", _utc_datetime(), nullable=True),
        sa.Column("heartbeat_at", _utc_datetime(), nullable=True),
        sa.Column("fencing_token", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("cancel_requested_at", _utc_datetime(), nullable=True),
        sa.Column("cancel_reason", sa.String(length=4096), nullable=True),
        sa.Column("cancelled_at", _utc_datetime(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("result_schema_version", sa.Integer(), nullable=True),
        sa.Column("error_code", _ascii(64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("completed_at", _utc_datetime(), nullable=True),
        sa.Column("replay_of_job_id", _uuid(), nullable=True),
        sa.Column("created_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.Column("updated_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_jobs_id_uuid"),
        sa.CheckConstraint(f"payload_digest REGEXP '{DIGEST_PATTERN}'", name="ck_jobs_payload_digest"),
        sa.CheckConstraint(f"status IN ({', '.join(repr(item) for item in JOB_STATUSES)})", name="ck_jobs_status"),
        sa.CheckConstraint("attempt_count >= 0 AND max_attempts > 0 AND attempt_count <= max_attempts", name="ck_jobs_attempts"),
        sa.CheckConstraint("fencing_token >= 0", name="ck_jobs_fencing_token"),
        sa.ForeignKeyConstraint(["replay_of_job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_type",
            "owner_scope_type",
            "owner_scope_id",
            "idempotency_key",
            name="uq_jobs_idempotency_scope",
        ),
    )
    op.create_index("ix_jobs_claim", "jobs", ["status", "available_at", "priority", "created_at", "id"])
    op.create_index("ix_jobs_owner_status", "jobs", ["owner_scope_type", "owner_scope_id", "job_type", "status"])
    op.create_index("ix_jobs_lease_expiry", "jobs", ["status", "lease_expires_at"])
    op.create_index("ix_jobs_correlation", "jobs", ["correlation_id"])

    op.create_table(
        "job_attempts",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("job_id", _uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("lease_owner", _ascii(128), nullable=False),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False),
        sa.Column("started_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.Column("heartbeat_at", _utc_datetime(), nullable=True),
        sa.Column("finished_at", _utc_datetime(), nullable=True),
        sa.Column("outcome", _ascii(32), server_default="running", nullable=False),
        sa.Column("error_code", _ascii(64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("worker_metadata_json", sa.JSON(), nullable=False),
        sa.CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_job_attempts_id_uuid"),
        sa.CheckConstraint("attempt_number > 0", name="ck_job_attempts_number"),
        sa.CheckConstraint("fencing_token > 0", name="ck_job_attempts_fencing"),
        sa.CheckConstraint(
            "outcome IN ('running', 'succeeded', 'retry_wait', 'cancelled', 'dead_letter', 'abandoned', 'fenced')",
            name="ck_job_attempts_outcome",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "attempt_number", name="uq_job_attempts_job_number"),
    )
    op.create_index("ix_job_attempts_job_started", "job_attempts", ["job_id", "started_at"])
    op.create_index("ix_job_attempts_lease", "job_attempts", ["lease_owner", "fencing_token"])

    op.create_table(
        "audit_events",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("actor_type", _ascii(32), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("actor_role", _ascii(64), nullable=True),
        sa.Column("action", _ascii(128), nullable=False),
        sa.Column("target_type", _ascii(64), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("scope_type", _ascii(32), nullable=True),
        sa.Column("scope_id", sa.String(length=64), nullable=True),
        sa.Column("policy_revision", sa.BigInteger(), nullable=True),
        sa.Column("subject_revision", sa.BigInteger(), nullable=True),
        sa.Column("content_digest", _digest(), nullable=True),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("grant_diff_json", sa.JSON(), nullable=True),
        sa.Column("reason", sa.String(length=4096), nullable=False),
        sa.Column("effective_at", _utc_datetime(), nullable=True),
        sa.Column("expires_at", _utc_datetime(), nullable=True),
        sa.Column("result", _ascii(32), nullable=False),
        sa.Column("error_code", _ascii(64), nullable=True),
        sa.Column("correlation_id", _uuid(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("job_id", _uuid(), nullable=True),
        sa.Column("import_id", sa.String(length=64), nullable=True),
        sa.Column("migration_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_audit_events_id_uuid"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_correlation_created", "audit_events", ["correlation_id", "created_at"])
    op.create_index("ix_audit_events_job_created", "audit_events", ["job_id", "created_at"])
    op.create_index("ix_audit_events_target_created", "audit_events", ["target_type", "target_id", "created_at"])
    op.create_index("ix_audit_events_actor_created", "audit_events", ["actor_type", "actor_id", "created_at"])


def downgrade() -> None:
    for table, indexes in (
        (
            "audit_events",
            [
                "ix_audit_events_actor_created",
                "ix_audit_events_target_created",
                "ix_audit_events_job_created",
                "ix_audit_events_correlation_created",
            ],
        ),
        ("job_attempts", ["ix_job_attempts_lease", "ix_job_attempts_job_started"]),
        ("jobs", ["ix_jobs_correlation", "ix_jobs_lease_expiry", "ix_jobs_owner_status", "ix_jobs_claim"]),
    ):
        for index in indexes:
            op.drop_index(index, table_name=table)
        op.drop_table(table)
