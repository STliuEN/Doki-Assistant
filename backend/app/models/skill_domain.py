from __future__ import annotations

from enum import Enum
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import relationship
from sqlalchemy.orm.attributes import NEVER_SET, NO_VALUE
from sqlalchemy.sql import func

from app.models.chat_history import Base


def _uuid() -> str:
    return str(uuid4())


def _enum(enum_type: type[Enum], name: str) -> SAEnum:
    return SAEnum(
        enum_type,
        values_callable=lambda members: [member.value for member in members],
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
    )


class SkillLifecycleStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class SkillPackageFormat(str, Enum):
    AGENT_SKILLS_V1 = "agent_skills_v1"


class SkillVersionStatus(str, Enum):
    DRAFT = "draft"
    VALIDATING = "validating"
    READY = "ready"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"
    RETIRED = "retired"


class SkillInstallationStatus(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class SkillImportStatus(str, Enum):
    RECEIVED = "received"
    STAGED = "staged"
    VALIDATION_QUEUED = "validation_queued"
    VALIDATING = "validating"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"
    AWAITING_APPROVAL = "awaiting_approval"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED_RETRYABLE = "failed_retryable"


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (
        UniqueConstraint("canonical_name", name="uq_skills_canonical_name"),
        Index("ix_skills_status", "status"),
    )

    id = Column(String(36), primary_key=True, default=_uuid, comment="UUID")
    canonical_name = Column(String(128), nullable=False, comment="Stable canonical Skill name")
    status = Column(
        _enum(SkillLifecycleStatus, "skill_lifecycle_status"),
        nullable=False,
        default=SkillLifecycleStatus.ACTIVE,
        server_default=SkillLifecycleStatus.ACTIVE.value,
    )
    created_by = Column(String(64), nullable=True, index=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    aliases = relationship("SkillAlias", back_populates="skill", cascade="all, delete-orphan")
    versions = relationship(
        "SkillVersion",
        back_populates="skill",
        foreign_keys="SkillVersion.skill_id",
    )
    installations = relationship("SkillInstallation", back_populates="skill")


class SkillAlias(Base):
    __tablename__ = "skill_aliases"
    __table_args__ = (
        UniqueConstraint("alias_name", name="uq_skill_aliases_alias_name"),
        UniqueConstraint("skill_id", "alias_name", name="uq_skill_aliases_skill_alias"),
    )

    id = Column(String(36), primary_key=True, default=_uuid, comment="UUID")
    skill_id = Column(String(36), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    alias_name = Column(String(128), nullable=False)
    alias_type = Column(String(32), nullable=False, default="legacy", server_default="legacy")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    skill = relationship("Skill", back_populates="aliases")


class SkillVersion(Base):
    __tablename__ = "skill_versions"
    __table_args__ = (
        UniqueConstraint("skill_id", "version_number", name="uq_skill_versions_skill_number"),
        UniqueConstraint("skill_id", "id", name="uq_skill_versions_skill_id"),
        UniqueConstraint("package_digest", name="uq_skill_versions_package_digest"),
        UniqueConstraint("storage_key", name="uq_skill_versions_storage_key"),
        Index("ix_skill_versions_skill_status", "skill_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=_uuid, comment="UUID")
    skill_id = Column(String(36), ForeignKey("skills.id", ondelete="RESTRICT"), nullable=False, index=True)
    parent_version_id = Column(
        String(36),
        ForeignKey("skill_versions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    version_number = Column(Integer, nullable=False)
    package_format = Column(
        _enum(SkillPackageFormat, "skill_package_format"),
        nullable=False,
    )
    schema_version = Column(String(32), nullable=False, default="1", server_default="1")
    source = Column(String(32), nullable=False, comment="import/editor/legacy/system")
    package_digest = Column(String(64), nullable=False, comment="Immutable SHA-256 digest")
    storage_key = Column(String(500), nullable=False, comment="Immutable canonical Storage object key")
    package_size_bytes = Column(BigInteger, nullable=False, default=0, server_default="0")
    name = Column(String(128), nullable=False)
    display_name = Column(String(160), nullable=False)
    description = Column(Text, nullable=False)
    manifest = Column(JSON, nullable=False, default=dict)
    requested_capabilities = Column(JSON, nullable=False, default=dict)
    status = Column(
        _enum(SkillVersionStatus, "skill_version_status"),
        nullable=False,
        default=SkillVersionStatus.DRAFT,
        server_default=SkillVersionStatus.DRAFT.value,
        index=True,
    )
    created_by = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    published_at = Column(DateTime(timezone=True), nullable=True)
    retired_at = Column(DateTime(timezone=True), nullable=True)

    skill = relationship("Skill", back_populates="versions", foreign_keys=[skill_id])
    parent_version = relationship("SkillVersion", remote_side=[id], foreign_keys=[parent_version_id])
    installations = relationship(
        "SkillInstallation",
        back_populates="active_version",
        foreign_keys="SkillInstallation.active_version_id",
        viewonly=True,
    )


class SkillInstallation(Base):
    __tablename__ = "skill_installations"
    __table_args__ = (
        UniqueConstraint("skill_id", "scope_type", "scope_key", name="uq_skill_installations_scope"),
        ForeignKeyConstraint(
            ["skill_id", "active_version_id"],
            ["skill_versions.skill_id", "skill_versions.id"],
            name="fk_skill_installations_active_skill_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["skill_id", "draft_version_id"],
            ["skill_versions.skill_id", "skill_versions.id"],
            name="fk_skill_installations_draft_skill_version",
            ondelete="RESTRICT",
        ),
        Index("ix_skill_installations_scope_status", "scope_type", "scope_key", "status"),
    )

    id = Column(String(36), primary_key=True, default=_uuid, comment="UUID")
    skill_id = Column(String(36), ForeignKey("skills.id", ondelete="RESTRICT"), nullable=False, index=True)
    active_version_id = Column(
        String(36),
        nullable=True,
        index=True,
    )
    draft_version_id = Column(String(36), nullable=True, index=True)
    scope_type = Column(String(32), nullable=False, default="system", server_default="system")
    scope_key = Column(String(128), nullable=False, default="global", server_default="global")
    status = Column(
        _enum(SkillInstallationStatus, "skill_installation_status"),
        nullable=False,
        default=SkillInstallationStatus.DISABLED,
        server_default=SkillInstallationStatus.DISABLED.value,
    )
    settings = Column(JSON, nullable=False, default=dict)
    revision = Column(BigInteger, nullable=False, default=1, server_default="1")
    created_by = Column(String(64), nullable=True)
    updated_by = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    skill = relationship("Skill", back_populates="installations")
    active_version = relationship(
        "SkillVersion",
        back_populates="installations",
        foreign_keys=[active_version_id],
        viewonly=True,
    )
    draft_version = relationship(
        "SkillVersion",
        foreign_keys=[draft_version_id],
        viewonly=True,
    )
    capability_grants = relationship(
        "SkillCapabilityGrant",
        back_populates="installation",
        cascade="all, delete-orphan",
    )


class SkillCapabilityGrant(Base):
    __tablename__ = "skill_capability_grants"
    __table_args__ = (
        UniqueConstraint(
            "installation_id",
            "skill_version_id",
            name="uq_skill_capability_grants_installation_version",
        ),
        Index("ix_skill_capability_grants_version_revoked", "skill_version_id", "revoked_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid, comment="UUID")
    installation_id = Column(
        String(36),
        ForeignKey("skill_installations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_version_id = Column(
        String(36),
        ForeignKey("skill_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    grants = Column(JSON, nullable=False, default=dict)
    revision = Column(BigInteger, nullable=False, default=1, server_default="1")
    granted_by = Column(String(64), nullable=True, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    installation = relationship("SkillInstallation", back_populates="capability_grants")
    skill_version = relationship("SkillVersion", foreign_keys=[skill_version_id])


class SkillImport(Base):
    __tablename__ = "skill_imports"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_skill_imports_idempotency_key"),
        Index("ix_skill_imports_status_created", "status", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid, comment="UUID")
    requested_by = Column(String(64), nullable=False, index=True)
    idempotency_key = Column(String(128), nullable=False)
    request_archive_digest = Column(String(64), nullable=False, comment="SHA-256 of the exact uploaded archive bytes")
    source_kind = Column(String(32), nullable=False, comment="upload/editor/legacy/system")
    source_reference = Column(String(500), nullable=True)
    staged_storage_key = Column(String(500), nullable=True)
    package_digest = Column(String(64), nullable=True, index=True)
    package_size_bytes = Column(BigInteger, nullable=True)
    discovered_canonical_name = Column(String(128), nullable=True)
    status = Column(
        _enum(SkillImportStatus, "skill_import_status"),
        nullable=False,
        default=SkillImportStatus.RECEIVED,
        server_default=SkillImportStatus.RECEIVED.value,
    )
    diagnostics = Column(JSON, nullable=False, default=dict)
    requested_capabilities = Column(JSON, nullable=False, default=dict)
    target_revision = Column(BigInteger, nullable=True)
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0, server_default="0")
    skill_id = Column(String(36), ForeignKey("skills.id", ondelete="SET NULL"), nullable=True, index=True)
    skill_version_id = Column(
        String(36),
        ForeignKey("skill_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    skill = relationship("Skill", foreign_keys=[skill_id])
    skill_version = relationship("SkillVersion", foreign_keys=[skill_version_id])


class SkillAuditEvent(Base):
    __tablename__ = "skill_audit_events"
    __table_args__ = (
        Index("ix_skill_audit_events_skill_created", "skill_id", "created_at"),
        Index("ix_skill_audit_events_action_created", "action", "created_at"),
        Index("ix_skill_audit_events_correlation_id", "correlation_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid, comment="UUID")
    skill_id = Column(String(36), ForeignKey("skills.id", ondelete="SET NULL"), nullable=True)
    skill_version_id = Column(
        String(36),
        ForeignKey("skill_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    installation_id = Column(
        String(36),
        ForeignKey("skill_installations.id", ondelete="SET NULL"),
        nullable=True,
    )
    import_id = Column(String(36), ForeignKey("skill_imports.id", ondelete="SET NULL"), nullable=True)
    actor_type = Column(String(32), nullable=False, default="user", server_default="user")
    actor_id = Column(String(64), nullable=True, index=True)
    action = Column(String(64), nullable=False)
    target_type = Column(String(32), nullable=False)
    target_id = Column(String(64), nullable=True)
    correlation_id = Column(String(64), nullable=True)
    before_state = Column(JSON, nullable=True)
    after_state = Column(JSON, nullable=True)
    details = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    skill = relationship("Skill", foreign_keys=[skill_id])
    skill_version = relationship("SkillVersion", foreign_keys=[skill_version_id])
    installation = relationship("SkillInstallation", foreign_keys=[installation_id])
    skill_import = relationship("SkillImport", foreign_keys=[import_id])


class SkillRegistryState(Base):
    __tablename__ = "skill_registry_state"

    id = Column(String(32), primary_key=True, default="global")
    revision = Column(BigInteger, nullable=False, default=0, server_default="0")
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class SkillRegistryEvent(Base):
    __tablename__ = "skill_registry_events"
    __table_args__ = (
        UniqueConstraint("revision", name="uq_skill_registry_events_revision"),
        Index("ix_skill_registry_events_processed_created", "processed_at", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid, comment="UUID")
    revision = Column(BigInteger, nullable=False)
    event_type = Column(String(64), nullable=False)
    skill_id = Column(String(36), ForeignKey("skills.id", ondelete="SET NULL"), nullable=True, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)

    skill = relationship("Skill", foreign_keys=[skill_id])


class SkillRunBinding(Base):
    """Immutable audit record of the exact Skill snapshot used by one Agent run."""

    __tablename__ = "skill_run_bindings"
    __table_args__ = (
        Index("ix_skill_run_bindings_user_created", "user_id", "created_at"),
        Index("ix_skill_run_bindings_session_created", "session_id", "created_at"),
    )

    run_id = Column(String(64), primary_key=True)
    session_id = Column(String(64), nullable=True)
    user_id = Column(String(64), nullable=False)
    registry_revision = Column(BigInteger, nullable=False)
    skill_bindings = Column(JSON, nullable=False, default=list)
    effective_grants = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _reject_immutable_change(target: SkillVersion, value: object, old_value: object, initiator):
    if old_value not in (NO_VALUE, NEVER_SET, None) and value != old_value:
        raise ValueError(f"SkillVersion.{initiator.key} is immutable")
    return value


for _immutable_version_attribute in (
    SkillVersion.package_digest,
    SkillVersion.storage_key,
    SkillVersion.name,
    SkillVersion.description,
    SkillVersion.manifest,
    SkillVersion.requested_capabilities,
):
    event.listen(
        _immutable_version_attribute,
        "set",
        _reject_immutable_change,
        retval=True,
        active_history=True,
    )
