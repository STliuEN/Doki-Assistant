"""E4 migration batch, entity-state, and media shadow models."""

from uuid import uuid4

from sqlalchemy import JSON, BigInteger, CheckConstraint, Column, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.models.chat_history import Base
from app.models.foundation_types import DIGEST_PATTERN, DIGEST_TYPE, LONG_BLOB, UTC_DATETIME, UUID_PATTERN, UUID_TYPE, ascii_string, binary_string

E4_MIGRATION_STATUSES = (
    "candidate",
    "validated",
    "mapped",
    "imported",
    "reconciled",
    "conflict",
    "orphan",
    "excluded",
)
E4_BATCH_STATUSES = (
    "planned",
    "validated",
    "importing",
    "imported",
    "reconciled",
    "blocked",
    "rolled_back",
)


def _uuid() -> str:
    return str(uuid4())


class E4MigrationBatch(Base):
    """Immutable identity for one replayable E4 migration batch."""

    __tablename__ = "e4_migration_batches"
    __table_args__ = (
        CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_e4_migration_batches_id_uuid"),
        CheckConstraint(
            f"snapshot_manifest_digest REGEXP '{DIGEST_PATTERN}'",
            name="ck_e4_migration_batches_snapshot_digest",
        ),
        CheckConstraint("length(migration_batch_id) > 0", name="ck_e4_migration_batches_batch_id"),
        CheckConstraint("length(schema_revision) > 0", name="ck_e4_migration_batches_schema_revision"),
        CheckConstraint(
            "status IN ('planned', 'validated', 'importing', 'imported', 'reconciled', 'blocked', 'rolled_back')",
            name="ck_e4_migration_batches_status",
        ),
        UniqueConstraint("migration_batch_id", name="uq_e4_migration_batches_batch"),
        Index("ix_e4_migration_batches_status_created", "status", "created_at"),
        Index("ix_e4_migration_batches_correlation", "correlation_id"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=_uuid)
    migration_batch_id = Column(ascii_string(64), nullable=False)
    snapshot_manifest_digest = Column(DIGEST_TYPE, nullable=False)
    schema_revision = Column(ascii_string(128), nullable=False)
    correlation_id = Column(UUID_TYPE, nullable=False)
    source_locator_digest = Column(DIGEST_TYPE, nullable=True)
    target_id = Column(ascii_string(64), nullable=True)
    restore_target_id = Column(ascii_string(64), nullable=True)
    status = Column(ascii_string(32), nullable=False, default="planned", server_default="planned")
    actor_id = Column(String(64), nullable=True)
    started_at = Column(UTC_DATETIME, nullable=True)
    finished_at = Column(UTC_DATETIME, nullable=True)
    created_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())
    updated_at = Column(UTC_DATETIME, nullable=False, server_default=func.now(), onupdate=func.now())


class E4MigrationEntity(Base):
    """One source entity and its append-only E4 state for a batch."""

    __tablename__ = "e4_migration_entities"
    __table_args__ = (
        CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_e4_migration_entities_id_uuid"),
        CheckConstraint(
            f"target_uuid IS NULL OR target_uuid REGEXP '{UUID_PATTERN}'",
            name="ck_e4_migration_entities_target_uuid",
        ),
        CheckConstraint(
            f"canonical_user_id IS NULL OR canonical_user_id REGEXP '{UUID_PATTERN}'",
            name="ck_e4_migration_entities_canonical_user_uuid",
        ),
        CheckConstraint(
            f"entity_content_digest REGEXP '{DIGEST_PATTERN}'",
            name="ck_e4_migration_entities_content_digest",
        ),
        CheckConstraint(
            f"artifact_digest IS NULL OR artifact_digest REGEXP '{DIGEST_PATTERN}'",
            name="ck_e4_migration_entities_artifact_digest",
        ),
        CheckConstraint(
            "legacy_md5 IS NULL OR legacy_md5 REGEXP '^[0-9a-fA-F]{32}$'",
            name="ck_e4_migration_entities_legacy_md5",
        ),
        CheckConstraint(
            "status IN ('candidate', 'validated', 'mapped', 'imported', 'reconciled', 'conflict', 'orphan', 'excluded')",
            name="ck_e4_migration_entities_status",
        ),
        CheckConstraint("scope_type IN ('user', 'global')", name="ck_e4_migration_entities_scope"),
        CheckConstraint(
            "(scope_type = 'global' AND canonical_user_id IS NULL) OR "
            "(scope_type = 'user' AND canonical_user_id IS NOT NULL)",
            name="ck_e4_migration_entities_user_owner",
        ),
        UniqueConstraint(
            "batch_id",
            "source_system",
            "entity_type",
            "source_id",
            name="uq_e4_migration_entities_batch_source",
        ),
        Index("ix_e4_migration_entities_batch_status", "batch_id", "status"),
        Index("ix_e4_migration_entities_target", "target_uuid"),
        Index("ix_e4_migration_entities_canonical_user", "canonical_user_id"),
        Index("ix_e4_migration_entities_correlation", "correlation_id"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=_uuid)
    batch_id = Column(UUID_TYPE, ForeignKey("e4_migration_batches.id", ondelete="CASCADE"), nullable=False)
    source_system = Column(ascii_string(64), nullable=False)
    entity_type = Column(ascii_string(64), nullable=False)
    source_id = Column(binary_string(255), nullable=False)
    target_uuid = Column(UUID_TYPE, nullable=True)
    canonical_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    scope_type = Column(ascii_string(32), nullable=False)
    owner_source_key = Column(JSON, nullable=True)
    entity_content_digest = Column(DIGEST_TYPE, nullable=False)
    artifact_digest = Column(DIGEST_TYPE, nullable=True)
    legacy_md5 = Column(ascii_string(32), nullable=True)
    status = Column(ascii_string(32), nullable=False, default="candidate", server_default="candidate")
    issue_code = Column(ascii_string(64), nullable=True)
    error_detail = Column(Text, nullable=True)
    correlation_id = Column(UUID_TYPE, nullable=False)
    imported_at = Column(UTC_DATETIME, nullable=True)
    reconciled_at = Column(UTC_DATETIME, nullable=True)
    created_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())
    updated_at = Column(UTC_DATETIME, nullable=False, server_default=func.now(), onupdate=func.now())


class MediaAsset(Base):
    """Canonical SQL representation for source media and original bytes."""

    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_media_assets_id_uuid"),
        CheckConstraint(f"content_digest REGEXP '{DIGEST_PATTERN}'", name="ck_media_assets_content_digest"),
        CheckConstraint(f"artifact_digest REGEXP '{DIGEST_PATTERN}'", name="ck_media_assets_artifact_digest"),
        CheckConstraint("legacy_md5 REGEXP '^[0-9a-fA-F]{32}$'", name="ck_media_assets_legacy_md5"),
        CheckConstraint("scope_type IN ('user', 'global')", name="ck_media_assets_scope"),
        CheckConstraint(
            "(scope_type = 'global' AND canonical_user_id IS NULL AND scope_id = 'global') OR "
            "(scope_type = 'user' AND canonical_user_id IS NOT NULL AND scope_id = canonical_user_id)",
            name="ck_media_assets_scope_owner",
        ),
        CheckConstraint("byte_size >= 0 AND byte_size <= 268435456", name="ck_media_assets_size"),
        CheckConstraint("status IN ('active', 'quarantined')", name="ck_media_assets_status"),
        UniqueConstraint("source_system", "source_id", name="uq_media_assets_source"),
        UniqueConstraint("content_digest", "scope_type", "scope_id", name="uq_media_assets_content_scope"),
        Index("ix_media_assets_owner_created", "canonical_user_id", "created_at"),
        Index("ix_media_assets_batch", "migration_batch_id"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=_uuid)
    canonical_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    scope_type = Column(ascii_string(32), nullable=False)
    scope_id = Column(ascii_string(64), nullable=False, default="global", server_default="global")
    source_system = Column(ascii_string(64), nullable=False)
    source_id = Column(binary_string(255), nullable=False)
    migration_batch_id = Column(ascii_string(64), nullable=False)
    content_digest = Column(DIGEST_TYPE, nullable=False)
    artifact_digest = Column(DIGEST_TYPE, nullable=False)
    legacy_md5 = Column(ascii_string(32), nullable=False)
    filename = Column(String(255), nullable=False)
    mime_type = Column(String(255), nullable=False)
    byte_size = Column(BigInteger, nullable=False)
    content_blob = Column(LONG_BLOB, nullable=False)
    status = Column(ascii_string(32), nullable=False, default="active", server_default="active")
    created_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())
    updated_at = Column(UTC_DATETIME, nullable=False, server_default=func.now(), onupdate=func.now())
