"""Add the E3 authentication runtime metadata and authorization grants.

This revision is intentionally additive.  It does not alter populated E4
business tables and must be applied only to an explicitly approved E3 target.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision = "20260831_0006_e3_auth_runtime"
down_revision = "20260828_0005_rag_skill"
branch_labels = None
depends_on = None

UUID_PATTERN = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
DIGEST_PATTERN = "^[0-9a-f]{64}$"


def _ascii(length: int):
    return sa.String(length).with_variant(
        mysql.VARCHAR(length=length, charset="ascii", collation="ascii_bin"),
        "mysql",
    )


def _binary_text(length: int):
    return sa.String(length).with_variant(
        mysql.VARCHAR(length=length, charset="utf8mb4", collation="utf8mb4_bin"),
        "mysql",
    )


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
        "auth_session_metadata",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("session_id", _uuid(), nullable=False),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("device_label", sa.String(length=128), nullable=True),
        sa.Column("ip_digest", _digest(), nullable=True),
        sa.Column("created_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.Column("updated_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_auth_session_metadata_id_uuid"),
        sa.CheckConstraint(
            f"ip_digest IS NULL OR ip_digest REGEXP '{DIGEST_PATTERN}'",
            name="ck_auth_session_metadata_ip_digest",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["auth_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_auth_session_metadata_session"),
    )
    op.create_index("ix_auth_session_metadata_session", "auth_session_metadata", ["session_id"])

    op.create_table(
        "user_profiles",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("user_id", _uuid(), nullable=False),
        sa.Column("gender", _ascii(32), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("avatar", sa.String(length=1024), nullable=True),
        sa.Column("last_login", _utc_datetime(), nullable=True),
        sa.Column("created_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.Column("updated_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_user_profiles_id_uuid"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_profiles_user"),
    )
    op.create_index("ix_user_profiles_user", "user_profiles", ["user_id"])

    op.create_table(
        "authorization_grants",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("target_type", _ascii(64), nullable=False),
        sa.Column("target_id", _binary_text(255), nullable=False),
        sa.Column("scope_type", _ascii(32), server_default="global", nullable=False),
        sa.Column("scope_id", _ascii(64), server_default="global", nullable=False),
        sa.Column("requested_by", _uuid(), nullable=False),
        sa.Column("approved_by", _uuid(), nullable=True),
        sa.Column("revoked_by", _uuid(), nullable=True),
        sa.Column("grant_json", sa.JSON(), nullable=False),
        sa.Column("policy_revision", sa.BigInteger(), server_default="1", nullable=False),
        sa.Column("subject_revision", sa.BigInteger(), server_default="1", nullable=False),
        sa.Column("content_digest", _digest(), nullable=False),
        sa.Column("effective_at", _utc_datetime(), nullable=True),
        sa.Column("expires_at", _utc_datetime(), nullable=True),
        sa.Column("status", _ascii(32), server_default="requested", nullable=False),
        sa.Column("reason", sa.String(length=4096), nullable=False),
        sa.Column("created_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.Column("updated_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_authorization_grants_id_uuid"),
        sa.CheckConstraint(
            "status IN ('requested', 'approved', 'rejected', 'revoked')",
            name="ck_authorization_grants_status",
        ),
        sa.CheckConstraint("policy_revision > 0 AND subject_revision > 0", name="ck_authorization_grants_revisions"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "target_type",
            "target_id",
            "scope_type",
            "scope_id",
            "status",
            name="uq_authorization_grants_active",
        ),
    )
    op.create_index(
        "ix_authorization_grants_status_created",
        "authorization_grants",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_authorization_grants_target",
        "authorization_grants",
        ["target_type", "target_id", "scope_type", "scope_id"],
    )
    op.create_index(
        "ix_authorization_grants_requester",
        "authorization_grants",
        ["requested_by", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_authorization_grants_requester", table_name="authorization_grants")
    op.drop_index("ix_authorization_grants_target", table_name="authorization_grants")
    op.drop_index("ix_authorization_grants_status_created", table_name="authorization_grants")
    op.drop_table("authorization_grants")
    op.drop_index("ix_user_profiles_user", table_name="user_profiles")
    op.drop_table("user_profiles")
    op.drop_index("ix_auth_session_metadata_session", table_name="auth_session_metadata")
    op.drop_table("auth_session_metadata")
