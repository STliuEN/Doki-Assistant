"""E8 durable SQL pending confirmation actions."""

import sqlalchemy as sa

from alembic import op

revision = "20260915_0011_e8_pending_actions"
down_revision = "20260914_0010_e6e7_sql_authority"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pending_actions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("tool_id", sa.String(255), nullable=False),
        sa.Column("args", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False, server_default="local"),
        sa.Column("provider_id", sa.String(128), nullable=True),
        sa.Column("external_name", sa.String(255), nullable=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("registry_revision", sa.BigInteger(), nullable=False),
        sa.Column("tool_digest", sa.String(64), nullable=False),
        sa.Column("provider_config_digest", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Index("ix_pending_actions_user_expires", "user_id", "expires_at"),
        sa.Index("ix_pending_actions_expires", "expires_at"),
    )


def downgrade():
    raise RuntimeError("E8 pending actions require restore-forward; do not downgrade a live confirmation ledger")
