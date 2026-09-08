"""Add the E4 business migration shadow and audit contract.

The revision is additive: legacy primary keys and source columns remain in
place while canonical UUIDs, content digests, and batch state are populated by
the E4 importer.  It is intentionally a forward-only production migration;
removing the shadow columns from a populated database requires a separately
approved cleanup stage.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision = "20260905_0008_e4_business_shadow"
down_revision = "20260901_0007_e3_auth"
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


def _long_blob():
    return sa.LargeBinary().with_variant(mysql.LONGBLOB(), "mysql")


def _now():
    return sa.text("CURRENT_TIMESTAMP(6)")


def _add_business_shadow_columns() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("canonical_id", _uuid(), nullable=True, comment="E4 canonical session UUID"),
    )
    op.add_column(
        "chat_sessions",
        sa.Column("canonical_user_id", _uuid(), nullable=True, comment="E4 canonical user UUID"),
    )
    op.create_unique_constraint("uq_chat_sessions_canonical_id", "chat_sessions", ["canonical_id"])
    op.create_foreign_key(
        "fk_chat_sessions_canonical_user",
        "chat_sessions",
        "users",
        ["canonical_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_chat_sessions_canonical_user", "chat_sessions", ["canonical_user_id"])

    op.add_column(
        "chat_messages",
        sa.Column("canonical_id", _uuid(), nullable=True, comment="E4 canonical message UUID"),
    )
    op.add_column(
        "chat_messages",
        sa.Column("canonical_session_id", _uuid(), nullable=True, comment="E4 canonical session UUID"),
    )
    op.add_column(
        "chat_messages",
        sa.Column("content_digest", _digest(), nullable=True, comment="E4 normalized message content SHA-256"),
    )
    op.create_unique_constraint("uq_chat_messages_canonical_id", "chat_messages", ["canonical_id"])
    op.create_foreign_key(
        "fk_chat_messages_canonical_session",
        "chat_messages",
        "chat_sessions",
        ["canonical_session_id"],
        ["canonical_id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_chat_messages_canonical_session", "chat_messages", ["canonical_session_id"])
    op.create_index("ix_chat_messages_content_digest", "chat_messages", ["content_digest"])

    op.add_column(
        "knowledge_source_documents",
        sa.Column("canonical_id", _uuid(), nullable=True, comment="E4 canonical document UUID"),
    )
    op.add_column(
        "knowledge_source_documents",
        sa.Column("canonical_user_id", _uuid(), nullable=True, comment="E4 canonical user UUID"),
    )
    op.add_column(
        "knowledge_source_documents",
        sa.Column("content_digest", _digest(), nullable=True, comment="E4 normalized document content SHA-256"),
    )
    op.add_column(
        "knowledge_source_documents",
        sa.Column("artifact_digest", _digest(), nullable=True, comment="E4 original artifact SHA-256"),
    )
    op.create_unique_constraint("uq_knowledge_source_canonical_id", "knowledge_source_documents", ["canonical_id"])
    op.create_foreign_key(
        "fk_knowledge_source_canonical_user",
        "knowledge_source_documents",
        "users",
        ["canonical_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_knowledge_source_canonical_user", "knowledge_source_documents", ["canonical_user_id"])

    for table, label in (("memory_items", "memory"), ("note_templates", "template"), ("notes", "note")):
        op.add_column(table, sa.Column("canonical_id", _uuid(), nullable=True, comment=f"E4 canonical {label} UUID"))
        op.add_column(table, sa.Column("canonical_user_id", _uuid(), nullable=True, comment="E4 canonical user UUID"))
        op.add_column(
            table,
            sa.Column("content_digest", _digest(), nullable=True, comment=f"E4 normalized {label} content SHA-256"),
        )
        op.create_unique_constraint(f"uq_{table}_canonical_id", table, ["canonical_id"])
        op.create_foreign_key(
            f"fk_{table}_canonical_user",
            table,
            "users",
            ["canonical_user_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(f"ix_{table}_canonical_user", table, ["canonical_user_id"])

    for table, label in (("user_embedding_configs", "embedding"), ("user_model_configs", "model config")):
        op.add_column(table, sa.Column("canonical_id", _uuid(), nullable=True, comment=f"E4 canonical {label} UUID"))
        op.add_column(table, sa.Column("canonical_user_id", _uuid(), nullable=True, comment="E4 canonical user UUID"))
        op.add_column(
            table,
            sa.Column("content_digest", _digest(), nullable=True, comment=f"E4 {label} content SHA-256"),
        )
        op.create_unique_constraint(f"uq_{table}_canonical_id", table, ["canonical_id"])
        op.create_foreign_key(
            f"fk_{table}_canonical_user",
            table,
            "users",
            ["canonical_user_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(f"ix_{table}_canonical_user", table, ["canonical_user_id"])
    op.add_column(
        "user_model_configs",
        sa.Column("api_key_key_version", _ascii(64), nullable=True, comment="Required before encrypted key migration"),
    )

    op.add_column(
        "skill_run_bindings",
        sa.Column("canonical_session_id", _uuid(), nullable=True, comment="E4 canonical session UUID"),
    )
    op.add_column(
        "skill_run_bindings",
        sa.Column("canonical_user_id", _uuid(), nullable=True, comment="E4 canonical user UUID"),
    )
    op.create_foreign_key(
        "fk_skill_run_bindings_canonical_user",
        "skill_run_bindings",
        "users",
        ["canonical_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_skill_run_bindings_canonical_session", "skill_run_bindings", ["canonical_session_id"])
    op.create_index("ix_skill_run_bindings_canonical_user", "skill_run_bindings", ["canonical_user_id"])

    # Shadow values are nullable during backfill, but any value that is
    # written must already be canonical.  This keeps a partial batch from
    # silently introducing a second UUID/digest spelling.
    for table, column, name in (
        ("chat_sessions", "canonical_id", "ck_chat_sessions_canonical_id_uuid"),
        ("chat_sessions", "canonical_user_id", "ck_chat_sessions_canonical_user_uuid"),
        ("chat_messages", "canonical_id", "ck_chat_messages_canonical_id_uuid"),
        ("chat_messages", "canonical_session_id", "ck_chat_messages_canonical_session_uuid"),
        ("chat_messages", "content_digest", "ck_chat_messages_content_digest"),
        ("knowledge_source_documents", "canonical_id", "ck_knowledge_source_canonical_id_uuid"),
        ("knowledge_source_documents", "canonical_user_id", "ck_knowledge_source_canonical_user_uuid"),
        ("knowledge_source_documents", "content_digest", "ck_knowledge_source_content_digest"),
        ("knowledge_source_documents", "artifact_digest", "ck_knowledge_source_artifact_digest"),
        ("memory_items", "canonical_id", "ck_memory_items_canonical_id_uuid"),
        ("memory_items", "canonical_user_id", "ck_memory_items_canonical_user_uuid"),
        ("memory_items", "content_digest", "ck_memory_items_content_digest"),
        ("note_templates", "canonical_id", "ck_note_templates_canonical_id_uuid"),
        ("note_templates", "canonical_user_id", "ck_note_templates_canonical_user_uuid"),
        ("note_templates", "content_digest", "ck_note_templates_content_digest"),
        ("notes", "canonical_id", "ck_notes_canonical_id_uuid"),
        ("notes", "canonical_user_id", "ck_notes_canonical_user_uuid"),
        ("notes", "content_digest", "ck_notes_content_digest"),
        ("user_embedding_configs", "canonical_id", "ck_user_embedding_configs_canonical_id_uuid"),
        ("user_embedding_configs", "canonical_user_id", "ck_user_embedding_configs_canonical_user_uuid"),
        ("user_embedding_configs", "content_digest", "ck_user_embedding_configs_content_digest"),
        ("user_model_configs", "canonical_id", "ck_user_model_configs_canonical_id_uuid"),
        ("user_model_configs", "canonical_user_id", "ck_user_model_configs_canonical_user_uuid"),
        ("user_model_configs", "content_digest", "ck_user_model_configs_content_digest"),
        ("skill_run_bindings", "canonical_session_id", "ck_skill_run_bindings_canonical_session_uuid"),
        ("skill_run_bindings", "canonical_user_id", "ck_skill_run_bindings_canonical_user_uuid"),
    ):
        expression = f"{column} IS NULL OR {column} REGEXP '{DIGEST_PATTERN if 'digest' in column else UUID_PATTERN}'"
        op.create_check_constraint(name, table, expression)


def _create_e4_tables() -> None:
    op.create_table(
        "e4_migration_batches",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("migration_batch_id", _ascii(64), nullable=False),
        sa.Column("snapshot_manifest_digest", _digest(), nullable=False),
        sa.Column("schema_revision", _ascii(128), nullable=False),
        sa.Column("correlation_id", _uuid(), nullable=False),
        sa.Column("source_locator_digest", _digest(), nullable=True),
        sa.Column("target_id", _ascii(64), nullable=True),
        sa.Column("restore_target_id", _ascii(64), nullable=True),
        sa.Column("status", _ascii(32), server_default="planned", nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=True),
        sa.Column("started_at", _utc_datetime(), nullable=True),
        sa.Column("finished_at", _utc_datetime(), nullable=True),
        sa.Column("created_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.Column("updated_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_e4_migration_batches_id_uuid"),
        sa.CheckConstraint(
            f"snapshot_manifest_digest REGEXP '{DIGEST_PATTERN}'",
            name="ck_e4_migration_batches_snapshot_digest",
        ),
        sa.CheckConstraint("length(migration_batch_id) > 0", name="ck_e4_migration_batches_batch_id"),
        sa.CheckConstraint("length(schema_revision) > 0", name="ck_e4_migration_batches_schema_revision"),
        sa.CheckConstraint(
            "status IN ('planned', 'validated', 'importing', 'imported', 'reconciled', 'blocked', 'rolled_back')",
            name="ck_e4_migration_batches_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("migration_batch_id", name="uq_e4_migration_batches_batch"),
    )
    op.create_index("ix_e4_migration_batches_status_created", "e4_migration_batches", ["status", "created_at"])
    op.create_index("ix_e4_migration_batches_correlation", "e4_migration_batches", ["correlation_id"])

    op.create_table(
        "e4_migration_entities",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("batch_id", _uuid(), nullable=False),
        sa.Column("source_system", _ascii(64), nullable=False),
        sa.Column("entity_type", _ascii(64), nullable=False),
        sa.Column("source_id", _binary_text(255), nullable=False),
        sa.Column("target_uuid", _uuid(), nullable=True),
        sa.Column("canonical_user_id", _uuid(), nullable=True),
        sa.Column("scope_type", _ascii(32), nullable=False),
        sa.Column("owner_source_key", sa.JSON(), nullable=True),
        sa.Column("entity_content_digest", _digest(), nullable=False),
        sa.Column("artifact_digest", _digest(), nullable=True),
        sa.Column("legacy_md5", _ascii(32), nullable=True),
        sa.Column("status", _ascii(32), server_default="candidate", nullable=False),
        sa.Column("issue_code", _ascii(64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("correlation_id", _uuid(), nullable=False),
        sa.Column("imported_at", _utc_datetime(), nullable=True),
        sa.Column("reconciled_at", _utc_datetime(), nullable=True),
        sa.Column("created_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.Column("updated_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_e4_migration_entities_id_uuid"),
        sa.CheckConstraint(
            f"target_uuid IS NULL OR target_uuid REGEXP '{UUID_PATTERN}'",
            name="ck_e4_migration_entities_target_uuid",
        ),
        sa.CheckConstraint(
            f"canonical_user_id IS NULL OR canonical_user_id REGEXP '{UUID_PATTERN}'",
            name="ck_e4_migration_entities_canonical_user_uuid",
        ),
        sa.CheckConstraint(
            f"entity_content_digest REGEXP '{DIGEST_PATTERN}'",
            name="ck_e4_migration_entities_content_digest",
        ),
        sa.CheckConstraint(
            f"artifact_digest IS NULL OR artifact_digest REGEXP '{DIGEST_PATTERN}'",
            name="ck_e4_migration_entities_artifact_digest",
        ),
        sa.CheckConstraint(
            "legacy_md5 IS NULL OR legacy_md5 REGEXP '^[0-9a-fA-F]{32}$'",
            name="ck_e4_migration_entities_legacy_md5",
        ),
        sa.CheckConstraint(
            "status IN ('candidate', 'validated', 'mapped', 'imported', 'reconciled', 'conflict', 'orphan', 'excluded')",
            name="ck_e4_migration_entities_status",
        ),
        sa.CheckConstraint("scope_type IN ('user', 'global')", name="ck_e4_migration_entities_scope"),
        sa.CheckConstraint(
            "(scope_type = 'global' AND canonical_user_id IS NULL) OR "
            "(scope_type = 'user' AND canonical_user_id IS NOT NULL)",
            name="ck_e4_migration_entities_user_owner",
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["e4_migration_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["canonical_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "batch_id",
            "source_system",
            "entity_type",
            "source_id",
            name="uq_e4_migration_entities_batch_source",
        ),
    )
    op.create_index("ix_e4_migration_entities_batch_status", "e4_migration_entities", ["batch_id", "status"])
    op.create_index("ix_e4_migration_entities_target", "e4_migration_entities", ["target_uuid"])
    op.create_index("ix_e4_migration_entities_canonical_user", "e4_migration_entities", ["canonical_user_id"])
    op.create_index("ix_e4_migration_entities_correlation", "e4_migration_entities", ["correlation_id"])

    op.create_table(
        "media_assets",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("canonical_user_id", _uuid(), nullable=True),
        sa.Column("scope_type", _ascii(32), nullable=False),
        sa.Column("scope_id", _ascii(64), server_default="global", nullable=False),
        sa.Column("source_system", _ascii(64), nullable=False),
        sa.Column("source_id", _binary_text(255), nullable=False),
        sa.Column("migration_batch_id", _ascii(64), nullable=False),
        sa.Column("content_digest", _digest(), nullable=False),
        sa.Column("artifact_digest", _digest(), nullable=False),
        sa.Column("legacy_md5", _ascii(32), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(255), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("content_blob", _long_blob(), nullable=False),
        sa.Column("status", _ascii(32), server_default="active", nullable=False),
        sa.Column("created_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.Column("updated_at", _utc_datetime(), server_default=_now(), nullable=False),
        sa.CheckConstraint(f"id REGEXP '{UUID_PATTERN}'", name="ck_media_assets_id_uuid"),
        sa.CheckConstraint(f"content_digest REGEXP '{DIGEST_PATTERN}'", name="ck_media_assets_content_digest"),
        sa.CheckConstraint(f"artifact_digest REGEXP '{DIGEST_PATTERN}'", name="ck_media_assets_artifact_digest"),
        sa.CheckConstraint("legacy_md5 REGEXP '^[0-9a-fA-F]{32}$'", name="ck_media_assets_legacy_md5"),
        sa.CheckConstraint("scope_type IN ('user', 'global')", name="ck_media_assets_scope"),
        sa.CheckConstraint(
            "(scope_type = 'global' AND canonical_user_id IS NULL AND scope_id = 'global') OR "
            "(scope_type = 'user' AND canonical_user_id IS NOT NULL AND scope_id = canonical_user_id)",
            name="ck_media_assets_scope_owner",
        ),
        sa.CheckConstraint("byte_size >= 0 AND byte_size <= 268435456", name="ck_media_assets_size"),
        sa.CheckConstraint("status IN ('active', 'quarantined')", name="ck_media_assets_status"),
        sa.ForeignKeyConstraint(["canonical_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_system", "source_id", name="uq_media_assets_source"),
        sa.UniqueConstraint("content_digest", "scope_type", "scope_id", name="uq_media_assets_content_scope"),
    )
    op.create_index("ix_media_assets_owner_created", "media_assets", ["canonical_user_id", "created_at"])
    op.create_index("ix_media_assets_batch", "media_assets", ["migration_batch_id"])


def upgrade() -> None:
    _add_business_shadow_columns()
    _create_e4_tables()


def downgrade() -> None:
    raise RuntimeError("E4 business shadow is forward-only; use the separately approved cleanup stage")
