"""E6/E7 SQL package links, original uploads and owner-bound source media."""

import sqlalchemy as sa

from alembic import op
from app.models.foundation_types import UUID_TYPE, ascii_string, binary_string

revision = "20260914_0010_e6e7_sql_authority"
down_revision = "20260914_0009_e5_rag_runtime"
branch_labels = None
depends_on = None


def upgrade():
    for table, column, target in (
        ("skill_versions", "package_id", "skill_packages.id"),
        ("skill_imports", "package_id", "skill_packages.id"),
        ("skill_imports", "upload_id", "skill_package_uploads.id"),
        ("skill_installations", "authorization_grant_id", "authorization_grants.id"),
    ):
        op.add_column(table, sa.Column(column, UUID_TYPE, nullable=True))
        remote_table, remote_column = target.split(".")
        op.create_foreign_key(f"fk_{table}_{column}", table, remote_table, [column], [remote_column], ondelete="RESTRICT")
        op.create_index(f"ix_{table}_{column}", table, [column])
    op.alter_column("skill_package_uploads", "package_id", existing_type=UUID_TYPE, nullable=True)
    op.add_column("skill_package_uploads", sa.Column("source_kind", ascii_string(32), nullable=False, server_default="upload"))
    op.create_unique_constraint("uq_knowledge_source_id_owner", "knowledge_source_documents", ["canonical_id", "canonical_user_id"])
    op.create_unique_constraint("uq_media_assets_id_owner", "media_assets", ["id", "canonical_user_id"])
    op.create_table(
        "source_media",
        sa.Column("source_id", UUID_TYPE, primary_key=True),
        sa.Column("media_id", UUID_TYPE, primary_key=True),
        sa.Column("filename", binary_string(255), primary_key=True),
        sa.Column("user_id", UUID_TYPE, nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.UniqueConstraint("source_id", "filename", name="uq_source_media_filename"),
        sa.ForeignKeyConstraint(["source_id", "user_id"],
                                ["knowledge_source_documents.canonical_id", "knowledge_source_documents.canonical_user_id"],
                                ondelete="CASCADE", name="fk_source_media_source_owner"),
        sa.ForeignKeyConstraint(["media_id", "user_id"], ["media_assets.id", "media_assets.canonical_user_id"],
                                ondelete="RESTRICT", name="fk_source_media_asset_owner"),
    )


def downgrade():
    raise RuntimeError("E6/E7 requires restore-forward; preserve SQL packages, media and authorization evidence")
