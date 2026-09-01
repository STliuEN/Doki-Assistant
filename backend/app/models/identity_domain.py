from __future__ import annotations

from uuid import uuid4

from sqlalchemy import JSON, BigInteger, CheckConstraint, Column, ForeignKey, Index, String, Text, UniqueConstraint, event
from sqlalchemy.orm import validates
from sqlalchemy.sql import func

from app.models.chat_history import Base
from app.models.foundation_types import (
    DIGEST_PATTERN,
    DIGEST_TYPE,
    UTC_DATETIME,
    UUID_PATTERN,
    UUID_TYPE,
    ascii_string,
    binary_string,
)


def _uuid() -> str:
    return str(uuid4())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_users_id_uuid"),
        CheckConstraint("status IN ('active', 'disabled', 'locked')", name="ck_users_status"),
        UniqueConstraint("username", name="uq_users_username"),
        UniqueConstraint("email_normalized", name="uq_users_email_normalized"),
        UniqueConstraint("phone_e164", name="uq_users_phone_e164"),
        Index("ix_users_status_created", "status", "created_at"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=_uuid)
    username = Column(String(150), nullable=False)
    email_display = Column(String(254), nullable=False)
    email_normalized = Column(binary_string(254), nullable=False)
    phone_display = Column(String(32), nullable=True)
    phone_e164 = Column(ascii_string(32), nullable=True)
    password_hash = Column(String(255), nullable=False)
    status = Column(ascii_string(32), nullable=False, default="active", server_default="active")
    token_version = Column(BigInteger, nullable=False, default=1, server_default="1")
    created_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())
    updated_at = Column(UTC_DATETIME, nullable=False, server_default=func.now(), onupdate=func.now())
    disabled_at = Column(UTC_DATETIME, nullable=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_auth_sessions_id_uuid"),
        CheckConstraint("status IN ('active', 'revoked', 'expired')", name="ck_auth_sessions_status"),
        Index("ix_auth_sessions_user_status", "user_id", "status"),
        Index("ix_auth_sessions_expires", "status", "expires_at"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=_uuid)
    user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    status = Column(ascii_string(32), nullable=False, default="active", server_default="active")
    issued_token_version = Column(BigInteger, nullable=False)
    revision = Column(BigInteger, nullable=False, default=1, server_default="1")
    expires_at = Column(UTC_DATETIME, nullable=False)
    revoked_at = Column(UTC_DATETIME, nullable=True)
    revoke_reason = Column(String(4096), nullable=True)
    last_seen_at = Column(UTC_DATETIME, nullable=True)
    created_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())
    updated_at = Column(UTC_DATETIME, nullable=False, server_default=func.now(), onupdate=func.now())


class AuthSessionMetadata(Base):
    __tablename__ = "auth_session_metadata"
    __table_args__ = (
        CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_auth_session_metadata_id_uuid"),
        CheckConstraint(f"ip_digest IS NULL OR ip_digest REGEXP '{DIGEST_PATTERN}'", name="ck_auth_session_metadata_ip_digest"),
        UniqueConstraint("session_id", name="uq_auth_session_metadata_session"),
        Index("ix_auth_session_metadata_session", "session_id"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=_uuid)
    session_id = Column(UUID_TYPE, ForeignKey("auth_sessions.id", ondelete="CASCADE"), nullable=False)
    user_agent = Column(String(512), nullable=True)
    device_label = Column(String(128), nullable=True)
    ip_digest = Column(DIGEST_TYPE, nullable=True)
    created_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())
    updated_at = Column(UTC_DATETIME, nullable=False, server_default=func.now(), onupdate=func.now())


class UserProfile(Base):
    __tablename__ = "user_profiles"
    __table_args__ = (
        CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_user_profiles_id_uuid"),
        UniqueConstraint("user_id", name="uq_user_profiles_user"),
        Index("ix_user_profiles_user", "user_id"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=_uuid)
    user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    gender = Column(ascii_string(32), nullable=True)
    bio = Column(Text, nullable=True)
    avatar = Column(String(1024), nullable=True)
    last_login = Column(UTC_DATETIME, nullable=True)
    created_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())
    updated_at = Column(UTC_DATETIME, nullable=False, server_default=func.now(), onupdate=func.now())


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_refresh_tokens_id_uuid"),
        CheckConstraint(f"family_id REGEXP '{UUID_PATTERN}'", name="ck_refresh_tokens_family_uuid"),
        CheckConstraint(f"token_digest REGEXP '{DIGEST_PATTERN}'", name="ck_refresh_tokens_token_digest"),
        CheckConstraint(f"jti_digest REGEXP '{DIGEST_PATTERN}'", name="ck_refresh_tokens_jti_digest"),
        CheckConstraint("status IN ('active', 'consumed', 'revoked')", name="ck_refresh_tokens_status"),
        UniqueConstraint("token_digest", name="uq_refresh_tokens_token_digest"),
        UniqueConstraint("jti_digest", name="uq_refresh_tokens_jti_digest"),
        Index("ix_refresh_tokens_session_status", "session_id", "status"),
        Index("ix_refresh_tokens_family_status", "family_id", "status"),
        Index("ix_refresh_tokens_expires", "status", "expires_at"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=_uuid)
    session_id = Column(UUID_TYPE, ForeignKey("auth_sessions.id", ondelete="RESTRICT"), nullable=False)
    family_id = Column(UUID_TYPE, nullable=False)
    token_digest = Column(DIGEST_TYPE, nullable=False)
    jti_digest = Column(DIGEST_TYPE, nullable=False)
    parent_token_id = Column(UUID_TYPE, ForeignKey("refresh_tokens.id", ondelete="RESTRICT"), nullable=True)
    replaced_by_token_id = Column(UUID_TYPE, ForeignKey("refresh_tokens.id", ondelete="RESTRICT"), nullable=True)
    status = Column(ascii_string(32), nullable=False, default="active", server_default="active")
    revision = Column(BigInteger, nullable=False, default=1, server_default="1")
    issued_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())
    consumed_at = Column(UTC_DATETIME, nullable=True)
    expires_at = Column(UTC_DATETIME, nullable=False)
    revoked_at = Column(UTC_DATETIME, nullable=True)
    created_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())


class TokenRevocation(Base):
    __tablename__ = "token_revocations"
    __table_args__ = (
        CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_token_revocations_id_uuid"),
        CheckConstraint("scope_type IN ('token', 'session', 'user_version')", name="ck_token_revocations_scope"),
        UniqueConstraint("scope_type", "scope_key", name="uq_token_revocations_scope_key"),
        Index("ix_token_revocations_user_created", "user_id", "created_at"),
        Index("ix_token_revocations_session_created", "session_id", "created_at"),
        Index("ix_token_revocations_expires", "expires_at"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=_uuid)
    scope_type = Column(ascii_string(32), nullable=False)
    scope_key = Column(ascii_string(160), nullable=False)
    token_digest = Column(DIGEST_TYPE, nullable=True)
    session_id = Column(UUID_TYPE, ForeignKey("auth_sessions.id", ondelete="RESTRICT"), nullable=True)
    user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    token_version = Column(BigInteger, nullable=True)
    reason = Column(String(4096), nullable=False)
    correlation_id = Column(UUID_TYPE, nullable=True)
    expires_at = Column(UTC_DATETIME, nullable=True)
    created_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_roles_id_uuid"),
        CheckConstraint("status IN ('active', 'disabled')", name="ck_roles_status"),
        UniqueConstraint("name", name="uq_roles_name"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=_uuid)
    name = Column(ascii_string(64), nullable=False)
    description = Column(String(512), nullable=False)
    status = Column(ascii_string(32), nullable=False, default="active", server_default="active")
    revision = Column(BigInteger, nullable=False, default=1, server_default="1")
    created_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())
    updated_at = Column(UTC_DATETIME, nullable=False, server_default=func.now(), onupdate=func.now())


class RoleBinding(Base):
    __tablename__ = "role_bindings"
    __table_args__ = (
        CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_role_bindings_id_uuid"),
        CheckConstraint("status IN ('active', 'revoked')", name="ck_role_bindings_status"),
        UniqueConstraint("user_id", "role_id", "scope_type", "scope_id", name="uq_role_bindings_subject_scope"),
        Index("ix_role_bindings_user_status", "user_id", "status"),
        Index("ix_role_bindings_scope_status", "scope_type", "scope_id", "status"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=_uuid)
    user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    role_id = Column(UUID_TYPE, ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
    scope_type = Column(ascii_string(32), nullable=False)
    scope_id = Column(ascii_string(64), nullable=False)
    status = Column(ascii_string(32), nullable=False, default="active", server_default="active")
    revision = Column(BigInteger, nullable=False, default=1, server_default="1")
    effective_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())
    expires_at = Column(UTC_DATETIME, nullable=True)
    revoked_at = Column(UTC_DATETIME, nullable=True)
    created_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())
    updated_at = Column(UTC_DATETIME, nullable=False, server_default=func.now(), onupdate=func.now())


class AuthorizationGrant(Base):
    __tablename__ = "authorization_grants"
    __table_args__ = (
        CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_authorization_grants_id_uuid"),
        CheckConstraint(
            "status IN ('requested', 'approved', 'rejected', 'revoked')",
            name="ck_authorization_grants_status",
        ),
        CheckConstraint("policy_revision > 0 AND subject_revision > 0", name="ck_authorization_grants_revisions"),
        UniqueConstraint("target_type", "target_id", "scope_type", "scope_id", "status", name="uq_authorization_grants_active"),
        Index("ix_authorization_grants_status_created", "status", "created_at"),
        Index("ix_authorization_grants_target", "target_type", "target_id", "scope_type", "scope_id"),
        Index("ix_authorization_grants_requester", "requested_by", "created_at"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=_uuid)
    target_type = Column(ascii_string(64), nullable=False)
    target_id = Column(String(255), nullable=False)
    scope_type = Column(ascii_string(32), nullable=False, default="global", server_default="global")
    scope_id = Column(ascii_string(64), nullable=False, default="global", server_default="global")
    requested_by = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    revoked_by = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    grant_json = Column(JSON, nullable=False)
    policy_revision = Column(BigInteger, nullable=False, default=1, server_default="1")
    subject_revision = Column(BigInteger, nullable=False, default=1, server_default="1")
    content_digest = Column(DIGEST_TYPE, nullable=False)
    effective_at = Column(UTC_DATETIME, nullable=True)
    expires_at = Column(UTC_DATETIME, nullable=True)
    status = Column(ascii_string(32), nullable=False, default="requested", server_default="requested")
    reason = Column(String(4096), nullable=False)
    created_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())
    updated_at = Column(UTC_DATETIME, nullable=False, server_default=func.now(), onupdate=func.now())


class MigrationMap(Base):
    __tablename__ = "migration_maps"
    __table_args__ = (
        CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_migration_maps_id_uuid"),
        CheckConstraint(f"target_uuid REGEXP '{UUID_PATTERN}'", name="ck_migration_maps_target_uuid"),
        CheckConstraint(f"source_digest REGEXP '{DIGEST_PATTERN}'", name="ck_migration_maps_source_digest"),
        CheckConstraint("status IN ('mapped', 'conflict', 'error')", name="ck_migration_maps_status"),
        UniqueConstraint("source_system", "entity_type", "source_id", name="uq_migration_maps_source"),
        Index("ix_migration_maps_batch_status", "migration_batch_id", "status"),
        Index("ix_migration_maps_target", "target_uuid"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=_uuid)
    migration_batch_id = Column(ascii_string(64), nullable=False)
    source_system = Column(ascii_string(64), nullable=False)
    entity_type = Column(ascii_string(64), nullable=False)
    source_id = Column(String(255), nullable=False)
    target_uuid = Column(UUID_TYPE, nullable=False)
    source_digest = Column(DIGEST_TYPE, nullable=False)
    status = Column(ascii_string(32), nullable=False, default="mapped", server_default="mapped")
    error_detail = Column(Text, nullable=True)
    created_at = Column(UTC_DATETIME, nullable=False, server_default=func.now())
    updated_at = Column(UTC_DATETIME, nullable=False, server_default=func.now(), onupdate=func.now())

    @validates("target_uuid")
    def _target_is_immutable(self, _key: str, value: str) -> str:
        current = getattr(self, "target_uuid", None)
        if current is not None and current != value:
            raise ValueError("target_uuid is immutable")
        return value


def _reject_mutation(_mapper, _connection, target) -> None:
    raise ValueError(f"{target.__tablename__} is append-only")


for _append_only_model in (TokenRevocation,):
    event.listen(_append_only_model, "before_update", _reject_mutation)
    event.listen(_append_only_model, "before_delete", _reject_mutation)
