"""E5 SQL RAG availability, configuration and immutable artifact manifests."""

import sqlalchemy as sa

from alembic import op
from app.models.foundation_types import DIGEST_TYPE, UTC_DATETIME, UUID_TYPE

revision = "20260914_0009_e5_rag_runtime"
down_revision = "20260905_0008_e4_business_shadow"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rag_user_states",
        sa.Column("user_id", UUID_TYPE, sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("query_revision", sa.BigInteger(), nullable=False),
        sa.Column("index_config", sa.JSON(), nullable=False),
        sa.Column("query_config", sa.JSON(), nullable=False),
        sa.Column("job_id", UUID_TYPE, sa.ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("source_digest", DIGEST_TYPE, nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("updated_at", UTC_DATETIME, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('building','ready','failed')", name="ck_rag_user_states_status"),
        sa.CheckConstraint("revision > 0 AND query_revision > 0", name="ck_rag_user_states_revisions"),
    )
    op.create_table(
        "rag_artifacts",
        sa.Column("generation_id", UUID_TYPE, sa.ForeignKey("rag_generations.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("collection_name", sa.String(128), nullable=False),
        sa.Column("job_id", UUID_TYPE, sa.ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("manifest_digest", DIGEST_TYPE, nullable=False),
        sa.Column("embedding_config", sa.JSON(), nullable=False),
        sa.Column("receipt", sa.JSON(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("cleanup_status", sa.String(16), nullable=False),
        sa.UniqueConstraint("collection_name", name="uq_rag_artifact_collection"),
    )


def downgrade():
    raise RuntimeError("E5 requires restore-forward; populated RAG runtime downgrade is not supported")
