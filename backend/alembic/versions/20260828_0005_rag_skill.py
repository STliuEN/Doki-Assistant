"""Add dormant RAG generation and SQL Skill package foundations.

Revision ID: 20260828_0005_rag_skill
Revises: 20260828_0004_jobs_audit
"""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision = "20260828_0005_rag_skill"
down_revision = "20260828_0004_jobs_audit"
branch_labels = None
depends_on = None

UUID_PATTERN = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
DIGEST_PATTERN = "^[0-9a-f]{64}$"


def _ascii(length: int):
    return sa.String(length).with_variant(mysql.VARCHAR(length=length, charset="ascii", collation="ascii_bin"), "mysql")


def _uuid():
    return sa.String(36).with_variant(mysql.CHAR(length=36, charset="ascii", collation="ascii_bin"), "mysql")


def _digest():
    return sa.String(64).with_variant(mysql.CHAR(length=64, charset="ascii", collation="ascii_bin"), "mysql")


def _utc_datetime():
    return sa.DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=6), "mysql")


def _long_blob():
    return sa.LargeBinary().with_variant(mysql.LONGBLOB(), "mysql")


def _now():
    return sa.text("CURRENT_TIMESTAMP(6)")


def upgrade() -> None:
    op.create_table(
        "rag_generations",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("owner_scope_type", _ascii(32), nullable=False),
        sa.Column("owner_scope_id", _ascii(64), nullable=False),
        sa.Column("index_kind", _ascii(64), nullable=False),
        sa.Column("embedding_fingerprint", _digest(), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("status", _ascii(32), server_default="building", nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("config_schema_version", sa.Integer(), nullable=False),
        sa.Column("source_revision", sa.BigInteger(), nullable=False),
        sa.Column("job_id", _uuid(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.Column("ready_at", _utc_datetime(), nullable=True),
        sa.Column("retired_at", _utc_datetime(), nullable=True),
        sa.CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_rag_generations_id_uuid"),
        sa.CheckConstraint(f"embedding_fingerprint REGEXP '{DIGEST_PATTERN}'", name="ck_rag_generations_fingerprint"),
        sa.CheckConstraint("status IN ('building', 'ready', 'failed', 'retired')", name="ck_rag_generations_status"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_scope_type",
            "owner_scope_id",
            "index_kind",
            "embedding_fingerprint",
            "generation",
            name="uq_rag_generations_owner_index_generation",
        ),
    )
    op.create_index(
        "ix_rag_generations_owner_status",
        "rag_generations",
        ["owner_scope_type", "owner_scope_id", "index_kind", "status"],
    )
    op.create_index("ix_rag_generations_job", "rag_generations", ["job_id"])

    op.create_table(
        "rag_generation_heads",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("owner_scope_type", _ascii(32), nullable=False),
        sa.Column("owner_scope_id", _ascii(64), nullable=False),
        sa.Column("index_kind", _ascii(64), nullable=False),
        sa.Column("active_generation_id", _uuid(), nullable=True),
        sa.Column("staging_generation_id", _uuid(), nullable=True),
        sa.Column("revision", sa.BigInteger(), server_default="1", nullable=False),
        sa.Column("created_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.Column("updated_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_rag_generation_heads_id_uuid"),
        sa.CheckConstraint("revision > 0", name="ck_rag_generation_heads_revision"),
        sa.ForeignKeyConstraint(["active_generation_id"], ["rag_generations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["staging_generation_id"], ["rag_generations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_scope_type", "owner_scope_id", "index_kind", name="uq_rag_generation_heads_owner_index"),
    )
    op.create_index("ix_rag_generation_heads_active", "rag_generation_heads", ["active_generation_id"])
    op.create_index("ix_rag_generation_heads_staging", "rag_generation_heads", ["staging_generation_id"])

    op.create_table(
        "skill_packages",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("package_digest", _digest(), nullable=False),
        sa.Column("canonical_archive_digest", _digest(), nullable=False),
        sa.Column("canonical_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("media_type", _ascii(128), server_default="application/zip", nullable=False),
        sa.Column("canonical_archive", _long_blob(), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("manifest_schema_version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_skill_packages_id_uuid"),
        sa.CheckConstraint(f"package_digest REGEXP '{DIGEST_PATTERN}'", name="ck_skill_packages_package_digest"),
        sa.CheckConstraint(
            f"canonical_archive_digest REGEXP '{DIGEST_PATTERN}'",
            name="ck_skill_packages_archive_digest",
        ),
        sa.CheckConstraint("canonical_size_bytes >= 0 AND canonical_size_bytes <= 67108864", name="ck_skill_packages_size"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_archive_digest", name="uq_skill_packages_archive_digest"),
        sa.UniqueConstraint("package_digest", name="uq_skill_packages_package_digest"),
    )
    op.create_index("ix_skill_packages_created_by", "skill_packages", ["created_by"])

    op.create_table(
        "skill_package_uploads",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("package_id", _uuid(), nullable=False),
        sa.Column("request_archive_digest", _digest(), nullable=False),
        sa.Column("original_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("media_type", _ascii(128), server_default="application/zip", nullable=False),
        sa.Column("raw_archive", _long_blob(), nullable=False),
        sa.Column("uploaded_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_skill_package_uploads_id_uuid"),
        sa.CheckConstraint(
            f"request_archive_digest REGEXP '{DIGEST_PATTERN}'",
            name="ck_skill_package_uploads_request_digest",
        ),
        sa.CheckConstraint("original_size_bytes >= 0 AND original_size_bytes <= 67108864", name="ck_skill_package_uploads_size"),
        sa.ForeignKeyConstraint(["package_id"], ["skill_packages.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_archive_digest", name="uq_skill_package_uploads_request_digest"),
    )
    op.create_index("ix_skill_package_uploads_package_created", "skill_package_uploads", ["package_id", "created_at"])
    op.create_index("ix_skill_package_uploads_uploaded_by", "skill_package_uploads", ["uploaded_by"])


def downgrade() -> None:
    for table, indexes in (
        (
            "skill_package_uploads",
            ["ix_skill_package_uploads_uploaded_by", "ix_skill_package_uploads_package_created"],
        ),
        ("skill_packages", ["ix_skill_packages_created_by"]),
        (
            "rag_generation_heads",
            ["ix_rag_generation_heads_staging", "ix_rag_generation_heads_active"],
        ),
        ("rag_generations", ["ix_rag_generations_job", "ix_rag_generations_owner_status"]),
    ):
        for index in indexes:
            op.drop_index(index, table_name=table)
        op.drop_table(table)
