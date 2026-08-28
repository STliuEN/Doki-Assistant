"""Add the canonical identity and authentication foundation.

Revision ID: 20260828_0003_identity_auth
Revises: 20260824_0002
"""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision = "20260828_0003_identity_auth"
down_revision = "20260824_0002"
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


def _now():
    return sa.text("CURRENT_TIMESTAMP(6)")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("username", sa.String(length=150), nullable=False),
        sa.Column("email_display", sa.String(length=254), nullable=False),
        sa.Column("email_normalized", sa.String(length=254, collation="utf8mb4_bin"), nullable=False),
        sa.Column("phone_display", sa.String(length=32), nullable=True),
        sa.Column("phone_e164", _ascii(32), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("status", _ascii(32), server_default="active", nullable=False),
        sa.Column("token_version", sa.BigInteger(), server_default="1", nullable=False),
        sa.Column("created_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.Column("updated_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.Column("disabled_at", _utc_datetime(), nullable=True),
        sa.CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_users_id_uuid"),
        sa.CheckConstraint("status IN ('active', 'disabled', 'locked')", name="ck_users_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email_normalized", name="uq_users_email_normalized"),
        sa.UniqueConstraint("phone_e164", name="uq_users_phone_e164"),
    )
    op.create_index("ix_users_status_created", "users", ["status", "created_at"])

    op.create_table(
        "roles",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("name", _ascii(64), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False),
        sa.Column("status", _ascii(32), server_default="active", nullable=False),
        sa.Column("revision", sa.BigInteger(), server_default="1", nullable=False),
        sa.Column("created_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.Column("updated_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_roles_id_uuid"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_roles_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("user_id", _uuid(), nullable=False),
        sa.Column("status", _ascii(32), server_default="active", nullable=False),
        sa.Column("issued_token_version", sa.BigInteger(), nullable=False),
        sa.Column("revision", sa.BigInteger(), server_default="1", nullable=False),
        sa.Column("expires_at", _utc_datetime(), nullable=False),
        sa.Column("revoked_at", _utc_datetime(), nullable=True),
        sa.Column("revoke_reason", sa.String(length=4096), nullable=True),
        sa.Column("last_seen_at", _utc_datetime(), nullable=True),
        sa.Column("created_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.Column("updated_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_auth_sessions_id_uuid"),
        sa.CheckConstraint("status IN ('active', 'revoked', 'expired')", name="ck_auth_sessions_status"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_sessions_user_status", "auth_sessions", ["user_id", "status"])
    op.create_index("ix_auth_sessions_expires", "auth_sessions", ["status", "expires_at"])

    op.create_table(
        "role_bindings",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("user_id", _uuid(), nullable=False),
        sa.Column("role_id", _uuid(), nullable=False),
        sa.Column("scope_type", _ascii(32), nullable=False),
        sa.Column("scope_id", _ascii(64), nullable=False),
        sa.Column("status", _ascii(32), server_default="active", nullable=False),
        sa.Column("revision", sa.BigInteger(), server_default="1", nullable=False),
        sa.Column("effective_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.Column("expires_at", _utc_datetime(), nullable=True),
        sa.Column("revoked_at", _utc_datetime(), nullable=True),
        sa.Column("created_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.Column("updated_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_role_bindings_id_uuid"),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="ck_role_bindings_status"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "role_id", "scope_type", "scope_id", name="uq_role_bindings_subject_scope"),
    )
    op.create_index("ix_role_bindings_user_status", "role_bindings", ["user_id", "status"])
    op.create_index("ix_role_bindings_scope_status", "role_bindings", ["scope_type", "scope_id", "status"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("session_id", _uuid(), nullable=False),
        sa.Column("family_id", _uuid(), nullable=False),
        sa.Column("token_digest", _digest(), nullable=False),
        sa.Column("jti_digest", _digest(), nullable=False),
        sa.Column("parent_token_id", _uuid(), nullable=True),
        sa.Column("replaced_by_token_id", _uuid(), nullable=True),
        sa.Column("status", _ascii(32), server_default="active", nullable=False),
        sa.Column("revision", sa.BigInteger(), server_default="1", nullable=False),
        sa.Column("issued_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.Column("consumed_at", _utc_datetime(), nullable=True),
        sa.Column("expires_at", _utc_datetime(), nullable=False),
        sa.Column("revoked_at", _utc_datetime(), nullable=True),
        sa.Column("created_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_refresh_tokens_id_uuid"),
        sa.CheckConstraint(f"family_id REGEXP '{UUID_PATTERN}'", name="ck_refresh_tokens_family_uuid"),
        sa.CheckConstraint(f"token_digest REGEXP '{DIGEST_PATTERN}'", name="ck_refresh_tokens_token_digest"),
        sa.CheckConstraint(f"jti_digest REGEXP '{DIGEST_PATTERN}'", name="ck_refresh_tokens_jti_digest"),
        sa.CheckConstraint("status IN ('active', 'consumed', 'revoked')", name="ck_refresh_tokens_status"),
        sa.ForeignKeyConstraint(["parent_token_id"], ["refresh_tokens.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["replaced_by_token_id"], ["refresh_tokens.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["session_id"], ["auth_sessions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("jti_digest", name="uq_refresh_tokens_jti_digest"),
        sa.UniqueConstraint("token_digest", name="uq_refresh_tokens_token_digest"),
    )
    op.create_index("ix_refresh_tokens_session_status", "refresh_tokens", ["session_id", "status"])
    op.create_index("ix_refresh_tokens_family_status", "refresh_tokens", ["family_id", "status"])
    op.create_index("ix_refresh_tokens_expires", "refresh_tokens", ["status", "expires_at"])

    op.create_table(
        "token_revocations",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("scope_type", _ascii(32), nullable=False),
        sa.Column("scope_key", _ascii(160), nullable=False),
        sa.Column("token_digest", _digest(), nullable=True),
        sa.Column("session_id", _uuid(), nullable=True),
        sa.Column("user_id", _uuid(), nullable=True),
        sa.Column("token_version", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.String(length=4096), nullable=False),
        sa.Column("correlation_id", _uuid(), nullable=True),
        sa.Column("expires_at", _utc_datetime(), nullable=True),
        sa.Column("created_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_token_revocations_id_uuid"),
        sa.CheckConstraint("scope_type IN ('token', 'session', 'user_version')", name="ck_token_revocations_scope"),
        sa.ForeignKeyConstraint(["session_id"], ["auth_sessions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope_type", "scope_key", name="uq_token_revocations_scope_key"),
    )
    op.create_index("ix_token_revocations_user_created", "token_revocations", ["user_id", "created_at"])
    op.create_index("ix_token_revocations_session_created", "token_revocations", ["session_id", "created_at"])
    op.create_index("ix_token_revocations_expires", "token_revocations", ["expires_at"])

    op.create_table(
        "migration_maps",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("migration_batch_id", _ascii(64), nullable=False),
        sa.Column("source_system", _ascii(64), nullable=False),
        sa.Column("entity_type", _ascii(64), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("target_uuid", _uuid(), nullable=False),
        sa.Column("source_digest", _digest(), nullable=False),
        sa.Column("status", _ascii(32), server_default="mapped", nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.Column("updated_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_migration_maps_id_uuid"),
        sa.CheckConstraint(f"target_uuid REGEXP '{UUID_PATTERN}'", name="ck_migration_maps_target_uuid"),
        sa.CheckConstraint(f"source_digest REGEXP '{DIGEST_PATTERN}'", name="ck_migration_maps_source_digest"),
        sa.CheckConstraint("status IN ('mapped', 'conflict', 'error')", name="ck_migration_maps_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_system", "entity_type", "source_id", name="uq_migration_maps_source"),
    )
    op.create_index("ix_migration_maps_batch_status", "migration_maps", ["migration_batch_id", "status"])
    op.create_index("ix_migration_maps_target", "migration_maps", ["target_uuid"])


def downgrade() -> None:
    for table, indexes in (
        ("migration_maps", ["ix_migration_maps_target", "ix_migration_maps_batch_status"]),
        (
            "token_revocations",
            ["ix_token_revocations_expires", "ix_token_revocations_session_created", "ix_token_revocations_user_created"],
        ),
        ("refresh_tokens", ["ix_refresh_tokens_expires", "ix_refresh_tokens_family_status", "ix_refresh_tokens_session_status"]),
        ("role_bindings", ["ix_role_bindings_scope_status", "ix_role_bindings_user_status"]),
        ("auth_sessions", ["ix_auth_sessions_expires", "ix_auth_sessions_user_status"]),
        ("roles", []),
        ("users", ["ix_users_status_created"]),
    ):
        for index in indexes:
            op.drop_index(index, table_name=table)
        op.drop_table(table)
