from __future__ import annotations

from uuid import uuid4

from sqlalchemy import JSON, BigInteger, CheckConstraint, Column, ForeignKey, Index, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.sql import func

from app.models.chat_history import Base
from app.models.foundation_types import (
    DIGEST_PATTERN,
    DIGEST_TYPE,
    LONG_BLOB,
    UTC_DATETIME,
    UUID_PATTERN,
    UUID_TYPE,
    ascii_string,
)


def _uuid() -> str:
    return str(uuid4())


class RagGeneration(Base):
    __tablename__ = "rag_generations"
    __table_args__ = (
        CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_rag_generations_id_uuid"),
        CheckConstraint(f"embedding_fingerprint REGEXP '{DIGEST_PATTERN}'", name="ck_rag_generations_fingerprint"),
        CheckConstraint("status IN ('building', 'ready', 'failed', 'retired')", name="ck_rag_generations_status"),
        UniqueConstraint(
            "owner_scope_type",
            "owner_scope_id",
            "index_kind",
            "embedding_fingerprint",
            "generation",
            name="uq_rag_generations_owner_index_generation",
        ),
        Index("ix_rag_generations_owner_status", "owner_scope_type", "owner_scope_id", "index_kind", "status"),
        Index("ix_rag_generations_job", "job_id"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=_uuid)
    owner_scope_type = Column(ascii_string(32), nullable=False)
    owner_scope_id = Column(ascii_string(64), nullable=False)
    index_kind = Column(ascii_string(64), nullable=False)
    embedding_fingerprint = Column(DIGEST_TYPE, nullable=False)
    generation = Column(BigInteger, nullable=False)
    status = Column(ascii_string(32), nullable=False, default="building", server_default="building")
    config_json = Column(JSON, nullable=False)
    config_schema_version = Column(Integer, nullable=False)
    source_revision = Column(BigInteger, nullable=False)
    job_id = Column(UUID_TYPE, ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=True)
    error_detail = Column(Text, nullable=True)
    created_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())
    ready_at = Column(UTC_DATETIME, nullable=True)
    retired_at = Column(UTC_DATETIME, nullable=True)


class RagGenerationHead(Base):
    __tablename__ = "rag_generation_heads"
    __table_args__ = (
        CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_rag_generation_heads_id_uuid"),
        CheckConstraint("revision > 0", name="ck_rag_generation_heads_revision"),
        UniqueConstraint("owner_scope_type", "owner_scope_id", "index_kind", name="uq_rag_generation_heads_owner_index"),
        Index("ix_rag_generation_heads_active", "active_generation_id"),
        Index("ix_rag_generation_heads_staging", "staging_generation_id"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=_uuid)
    owner_scope_type = Column(ascii_string(32), nullable=False)
    owner_scope_id = Column(ascii_string(64), nullable=False)
    index_kind = Column(ascii_string(64), nullable=False)
    active_generation_id = Column(UUID_TYPE, ForeignKey("rag_generations.id", ondelete="RESTRICT"), nullable=True)
    staging_generation_id = Column(UUID_TYPE, ForeignKey("rag_generations.id", ondelete="RESTRICT"), nullable=True)
    revision = Column(BigInteger, nullable=False, default=1, server_default="1")
    created_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())
    updated_at = Column(UTC_DATETIME, nullable=False, server_default=func.now(), onupdate=func.now())


class SkillPackage(Base):
    __tablename__ = "skill_packages"
    __table_args__ = (
        CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_skill_packages_id_uuid"),
        CheckConstraint(f"package_digest REGEXP '{DIGEST_PATTERN}'", name="ck_skill_packages_package_digest"),
        CheckConstraint(
            f"canonical_archive_digest REGEXP '{DIGEST_PATTERN}'",
            name="ck_skill_packages_archive_digest",
        ),
        CheckConstraint("canonical_size_bytes >= 0 AND canonical_size_bytes <= 67108864", name="ck_skill_packages_size"),
        UniqueConstraint("package_digest", name="uq_skill_packages_package_digest"),
        UniqueConstraint("canonical_archive_digest", name="uq_skill_packages_archive_digest"),
        Index("ix_skill_packages_created_by", "created_by"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=_uuid)
    package_digest = Column(DIGEST_TYPE, nullable=False)
    canonical_archive_digest = Column(DIGEST_TYPE, nullable=False)
    canonical_size_bytes = Column(BigInteger, nullable=False)
    media_type = Column(ascii_string(128), nullable=False, default="application/zip", server_default="application/zip")
    canonical_archive = Column(LONG_BLOB, nullable=False)
    manifest_json = Column(JSON, nullable=False)
    manifest_schema_version = Column(Integer, nullable=False)
    created_by = Column(String(64), nullable=True)
    created_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())


class SkillPackageUpload(Base):
    __tablename__ = "skill_package_uploads"
    __table_args__ = (
        CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_skill_package_uploads_id_uuid"),
        CheckConstraint(
            f"request_archive_digest REGEXP '{DIGEST_PATTERN}'",
            name="ck_skill_package_uploads_request_digest",
        ),
        CheckConstraint("original_size_bytes >= 0 AND original_size_bytes <= 67108864", name="ck_skill_package_uploads_size"),
        UniqueConstraint("request_archive_digest", name="uq_skill_package_uploads_request_digest"),
        Index("ix_skill_package_uploads_package_created", "package_id", "created_at"),
        Index("ix_skill_package_uploads_uploaded_by", "uploaded_by"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=_uuid)
    package_id = Column(UUID_TYPE, ForeignKey("skill_packages.id", ondelete="RESTRICT"), nullable=False)
    request_archive_digest = Column(DIGEST_TYPE, nullable=False)
    original_size_bytes = Column(BigInteger, nullable=False)
    media_type = Column(ascii_string(128), nullable=False, default="application/zip", server_default="application/zip")
    raw_archive = Column(LONG_BLOB, nullable=False)
    uploaded_by = Column(String(64), nullable=True)
    created_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())


def _reject_mutation(_mapper, _connection, target) -> None:
    raise ValueError(f"{target.__tablename__} is immutable")


for _immutable_model in (SkillPackage, SkillPackageUpload):
    event.listen(_immutable_model, "before_update", _reject_mutation)
    event.listen(_immutable_model, "before_delete", _reject_mutation)
