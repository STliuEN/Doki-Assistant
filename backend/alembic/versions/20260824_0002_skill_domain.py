"""Add the versioned Skill domain schema.

Revision ID: 20260824_0002
Revises: 20260817_0001
"""

import sqlalchemy as sa

from alembic import op

revision = "20260824_0002"
down_revision = "20260817_0001"
branch_labels = None
depends_on = None


def _enum(*values: str, name: str) -> sa.Enum:
    return sa.Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=True,
    )


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", sa.String(length=36), nullable=False, comment="UUID"),
        sa.Column("canonical_name", sa.String(length=128), nullable=False, comment="Stable canonical Skill name"),
        sa.Column(
            "status",
            _enum("active", "archived", name="skill_lifecycle_status"),
            server_default="active",
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_name", name="uq_skills_canonical_name"),
    )
    op.create_index("ix_skills_created_by", "skills", ["created_by"])
    op.create_index("ix_skills_status", "skills", ["status"])

    op.create_table(
        "skill_aliases",
        sa.Column("id", sa.String(length=36), nullable=False, comment="UUID"),
        sa.Column("skill_id", sa.String(length=36), nullable=False),
        sa.Column("alias_name", sa.String(length=128), nullable=False),
        sa.Column("alias_type", sa.String(length=32), server_default="legacy", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alias_name", name="uq_skill_aliases_alias_name"),
        sa.UniqueConstraint("skill_id", "alias_name", name="uq_skill_aliases_skill_alias"),
    )
    op.create_index("ix_skill_aliases_skill_id", "skill_aliases", ["skill_id"])

    op.create_table(
        "skill_versions",
        sa.Column("id", sa.String(length=36), nullable=False, comment="UUID"),
        sa.Column("skill_id", sa.String(length=36), nullable=False),
        sa.Column("parent_version_id", sa.String(length=36), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "package_format",
            _enum("agent_skills_v1", name="skill_package_format"),
            nullable=False,
        ),
        sa.Column("schema_version", sa.String(length=32), server_default="1", nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, comment="import/editor/legacy/system"),
        sa.Column("package_digest", sa.String(length=64), nullable=False, comment="Immutable SHA-256 digest"),
        sa.Column("storage_key", sa.String(length=500), nullable=False, comment="Immutable canonical Storage object key"),
        sa.Column("package_size_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("requested_capabilities", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            _enum(
                "draft",
                "validating",
                "ready",
                "rejected",
                "quarantined",
                "retired",
                name="skill_version_status",
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["parent_version_id"], ["skill_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("package_digest", name="uq_skill_versions_package_digest"),
        sa.UniqueConstraint("skill_id", "id", name="uq_skill_versions_skill_id"),
        sa.UniqueConstraint("skill_id", "version_number", name="uq_skill_versions_skill_number"),
        sa.UniqueConstraint("storage_key", name="uq_skill_versions_storage_key"),
    )
    op.create_index("ix_skill_versions_created_by", "skill_versions", ["created_by"])
    op.create_index("ix_skill_versions_parent_version_id", "skill_versions", ["parent_version_id"])
    op.create_index("ix_skill_versions_skill_id", "skill_versions", ["skill_id"])
    op.create_index("ix_skill_versions_skill_status", "skill_versions", ["skill_id", "status"])
    op.create_index("ix_skill_versions_status", "skill_versions", ["status"])

    op.create_table(
        "skill_installations",
        sa.Column("id", sa.String(length=36), nullable=False, comment="UUID"),
        sa.Column("skill_id", sa.String(length=36), nullable=False),
        sa.Column("active_version_id", sa.String(length=36), nullable=True),
        sa.Column("draft_version_id", sa.String(length=36), nullable=True),
        sa.Column("scope_type", sa.String(length=32), server_default="system", nullable=False),
        sa.Column("scope_key", sa.String(length=128), server_default="global", nullable=False),
        sa.Column(
            "status",
            _enum("enabled", "disabled", name="skill_installation_status"),
            server_default="disabled",
            nullable=False,
        ),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("revision", sa.BigInteger(), server_default="1", nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("updated_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(
            ["skill_id", "active_version_id"],
            ["skill_versions.skill_id", "skill_versions.id"],
            name="fk_skill_installations_active_skill_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id", "draft_version_id"],
            ["skill_versions.skill_id", "skill_versions.id"],
            name="fk_skill_installations_draft_skill_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("skill_id", "scope_type", "scope_key", name="uq_skill_installations_scope"),
    )
    op.create_index("ix_skill_installations_active_version_id", "skill_installations", ["active_version_id"])
    op.create_index("ix_skill_installations_draft_version_id", "skill_installations", ["draft_version_id"])
    op.create_index("ix_skill_installations_scope_status", "skill_installations", ["scope_type", "scope_key", "status"])
    op.create_index("ix_skill_installations_skill_id", "skill_installations", ["skill_id"])

    op.create_table(
        "skill_imports",
        sa.Column("id", sa.String(length=36), nullable=False, comment="UUID"),
        sa.Column("requested_by", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "request_archive_digest",
            sa.String(length=64),
            nullable=False,
            comment="SHA-256 of the exact uploaded archive bytes",
        ),
        sa.Column("source_kind", sa.String(length=32), nullable=False, comment="upload/editor/legacy/system"),
        sa.Column("source_reference", sa.String(length=500), nullable=True),
        sa.Column("staged_storage_key", sa.String(length=500), nullable=True),
        sa.Column("package_digest", sa.String(length=64), nullable=True),
        sa.Column("package_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("discovered_canonical_name", sa.String(length=128), nullable=True),
        sa.Column(
            "status",
            _enum(
                "received",
                "staged",
                "validation_queued",
                "validating",
                "rejected",
                "quarantined",
                "awaiting_approval",
                "publishing",
                "published",
                "failed_retryable",
                name="skill_import_status",
            ),
            server_default="received",
            nullable=False,
        ),
        sa.Column("diagnostics", sa.JSON(), nullable=False),
        sa.Column("requested_capabilities", sa.JSON(), nullable=False),
        sa.Column("target_revision", sa.BigInteger(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("skill_id", sa.String(length=36), nullable=True),
        sa.Column("skill_version_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["skill_version_id"], ["skill_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_skill_imports_idempotency_key"),
    )
    op.create_index("ix_skill_imports_package_digest", "skill_imports", ["package_digest"])
    op.create_index("ix_skill_imports_requested_by", "skill_imports", ["requested_by"])
    op.create_index("ix_skill_imports_skill_id", "skill_imports", ["skill_id"])
    op.create_index("ix_skill_imports_skill_version_id", "skill_imports", ["skill_version_id"])
    op.create_index("ix_skill_imports_status_created", "skill_imports", ["status", "created_at"])

    op.create_table(
        "skill_capability_grants",
        sa.Column("id", sa.String(length=36), nullable=False, comment="UUID"),
        sa.Column("installation_id", sa.String(length=36), nullable=False),
        sa.Column("skill_version_id", sa.String(length=36), nullable=False),
        sa.Column("grants", sa.JSON(), nullable=False),
        sa.Column("revision", sa.BigInteger(), server_default="1", nullable=False),
        sa.Column("granted_by", sa.String(length=64), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["installation_id"], ["skill_installations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_version_id"], ["skill_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "installation_id",
            "skill_version_id",
            name="uq_skill_capability_grants_installation_version",
        ),
    )
    op.create_index(
        "ix_skill_capability_grants_installation_id",
        "skill_capability_grants",
        ["installation_id"],
    )
    op.create_index(
        "ix_skill_capability_grants_skill_version_id",
        "skill_capability_grants",
        ["skill_version_id"],
    )
    op.create_index(
        "ix_skill_capability_grants_granted_by",
        "skill_capability_grants",
        ["granted_by"],
    )
    op.create_index(
        "ix_skill_capability_grants_version_revoked",
        "skill_capability_grants",
        ["skill_version_id", "revoked_at"],
    )

    op.create_table(
        "skill_audit_events",
        sa.Column("id", sa.String(length=36), nullable=False, comment="UUID"),
        sa.Column("skill_id", sa.String(length=36), nullable=True),
        sa.Column("skill_version_id", sa.String(length=36), nullable=True),
        sa.Column("installation_id", sa.String(length=36), nullable=True),
        sa.Column("import_id", sa.String(length=36), nullable=True),
        sa.Column("actor_type", sa.String(length=32), server_default="user", nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["import_id"], ["skill_imports.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["installation_id"], ["skill_installations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["skill_version_id"], ["skill_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_skill_audit_events_action_created", "skill_audit_events", ["action", "created_at"])
    op.create_index("ix_skill_audit_events_actor_id", "skill_audit_events", ["actor_id"])
    op.create_index("ix_skill_audit_events_correlation_id", "skill_audit_events", ["correlation_id"])
    op.create_index("ix_skill_audit_events_skill_created", "skill_audit_events", ["skill_id", "created_at"])

    op.create_table(
        "skill_registry_state",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("revision", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(sa.text("INSERT INTO skill_registry_state (id, revision) VALUES ('global', 0)"))

    op.create_table(
        "skill_registry_events",
        sa.Column("id", sa.String(length=36), nullable=False, comment="UUID"),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("skill_id", sa.String(length=36), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("revision", name="uq_skill_registry_events_revision"),
    )
    op.create_index("ix_skill_registry_events_skill_id", "skill_registry_events", ["skill_id"])
    op.create_index(
        "ix_skill_registry_events_processed_created",
        "skill_registry_events",
        ["processed_at", "created_at"],
    )

    op.create_table(
        "skill_run_bindings",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("registry_revision", sa.BigInteger(), nullable=False),
        sa.Column("skill_bindings", sa.JSON(), nullable=False),
        sa.Column("effective_grants", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        "ix_skill_run_bindings_user_created",
        "skill_run_bindings",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_skill_run_bindings_session_created",
        "skill_run_bindings",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_skill_run_bindings_session_created", table_name="skill_run_bindings")
    op.drop_index("ix_skill_run_bindings_user_created", table_name="skill_run_bindings")
    op.drop_table("skill_run_bindings")

    op.drop_index("ix_skill_registry_events_processed_created", table_name="skill_registry_events")
    op.drop_index("ix_skill_registry_events_skill_id", table_name="skill_registry_events")
    op.drop_table("skill_registry_events")
    op.drop_table("skill_registry_state")

    for index_name in (
        "ix_skill_audit_events_skill_created",
        "ix_skill_audit_events_correlation_id",
        "ix_skill_audit_events_actor_id",
        "ix_skill_audit_events_action_created",
    ):
        op.drop_index(index_name, table_name="skill_audit_events")
    op.drop_table("skill_audit_events")

    for index_name in (
        "ix_skill_capability_grants_version_revoked",
        "ix_skill_capability_grants_granted_by",
        "ix_skill_capability_grants_skill_version_id",
        "ix_skill_capability_grants_installation_id",
    ):
        op.drop_index(index_name, table_name="skill_capability_grants")
    op.drop_table("skill_capability_grants")

    for index_name in (
        "ix_skill_imports_status_created",
        "ix_skill_imports_skill_version_id",
        "ix_skill_imports_skill_id",
        "ix_skill_imports_requested_by",
        "ix_skill_imports_package_digest",
    ):
        op.drop_index(index_name, table_name="skill_imports")
    op.drop_table("skill_imports")

    for index_name in (
        "ix_skill_installations_skill_id",
        "ix_skill_installations_scope_status",
        "ix_skill_installations_draft_version_id",
        "ix_skill_installations_active_version_id",
    ):
        op.drop_index(index_name, table_name="skill_installations")
    op.drop_table("skill_installations")

    for index_name in (
        "ix_skill_versions_status",
        "ix_skill_versions_skill_status",
        "ix_skill_versions_skill_id",
        "ix_skill_versions_parent_version_id",
        "ix_skill_versions_created_by",
    ):
        op.drop_index(index_name, table_name="skill_versions")
    op.drop_table("skill_versions")

    op.drop_index("ix_skill_aliases_skill_id", table_name="skill_aliases")
    op.drop_table("skill_aliases")

    op.drop_index("ix_skills_status", table_name="skills")
    op.drop_index("ix_skills_created_by", table_name="skills")
    op.drop_table("skills")
