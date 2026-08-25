from __future__ import annotations

import pytest
from sqlalchemy import JSON, BigInteger, Enum, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import configure_mappers
from sqlalchemy.schema import CreateTable

from app.models.skill_domain import (
    Skill,
    SkillAlias,
    SkillAuditEvent,
    SkillCapabilityGrant,
    SkillImport,
    SkillImportStatus,
    SkillInstallation,
    SkillInstallationStatus,
    SkillPackageFormat,
    SkillRegistryEvent,
    SkillRegistryState,
    SkillRunBinding,
    SkillVersion,
    SkillVersionStatus,
)

SKILL_MODELS = (
    Skill,
    SkillAlias,
    SkillVersion,
    SkillInstallation,
    SkillCapabilityGrant,
    SkillImport,
    SkillAuditEvent,
    SkillRegistryState,
    SkillRegistryEvent,
    SkillRunBinding,
)


def _unique_names(model) -> set[str]:
    return {
        constraint.name
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint) and constraint.name
    }


def _foreign_key_targets(model) -> set[tuple[str, str, str | None]]:
    return {
        (item.parent.name, item.target_fullname, constraint.ondelete)
        for constraint in model.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        for item in constraint.elements
    }


def _index_names(model) -> set[str]:
    return {index.name for index in model.__table__.indexes if index.name}


def test_skill_domain_registers_versioned_tables_and_configures_relationships() -> None:
    configure_mappers()
    assert {model.__tablename__ for model in SKILL_MODELS} == {
        "skills",
        "skill_aliases",
        "skill_versions",
        "skill_installations",
        "skill_capability_grants",
        "skill_imports",
        "skill_audit_events",
        "skill_registry_state",
        "skill_registry_events",
        "skill_run_bindings",
    }

    for model in SKILL_MODELS:
        identifier = (
            model.__table__.c.run_id
            if model is SkillRunBinding
            else model.__table__.c.id
        )
        assert identifier.primary_key
        assert isinstance(identifier.type, String)
        expected_length = 64 if model is SkillRunBinding else 32 if model is SkillRegistryState else 36
        assert identifier.type.length == expected_length


def test_skill_identity_version_and_installation_constraints() -> None:
    assert "uq_skills_canonical_name" in _unique_names(Skill)
    assert {
        "uq_skill_aliases_alias_name",
        "uq_skill_aliases_skill_alias",
    }.issubset(_unique_names(SkillAlias))
    assert {
        "uq_skill_versions_skill_number",
        "uq_skill_versions_skill_id",
        "uq_skill_versions_package_digest",
        "uq_skill_versions_storage_key",
    }.issubset(_unique_names(SkillVersion))
    assert "uq_skill_installations_scope" in _unique_names(SkillInstallation)

    assert ("skill_id", "skills.id", "RESTRICT") in _foreign_key_targets(SkillVersion)
    assert ("parent_version_id", "skill_versions.id", "RESTRICT") in _foreign_key_targets(SkillVersion)
    assert ("active_version_id", "skill_versions.id", "RESTRICT") in _foreign_key_targets(SkillInstallation)
    assert ("draft_version_id", "skill_versions.id", "RESTRICT") in _foreign_key_targets(SkillInstallation)

    assert isinstance(SkillVersion.__table__.c.package_format.type, Enum)
    assert set(SkillVersion.__table__.c.package_format.type.enums) == {
        item.value for item in SkillPackageFormat
    }
    assert set(SkillVersion.__table__.c.status.type.enums) == {
        item.value for item in SkillVersionStatus
    }
    assert isinstance(SkillInstallation.__table__.c.settings.type, JSON)
    assert isinstance(SkillInstallation.__table__.c.revision.type, BigInteger)


def test_skill_version_digest_and_storage_key_are_immutable() -> None:
    version = SkillVersion(
        skill_id="s" * 36,
        version_number=1,
        package_format=SkillPackageFormat.AGENT_SKILLS_V1,
        source="import",
        package_digest="a" * 64,
        storage_key="skills/a/package.zip",
        name="example-skill",
        display_name="Example Skill",
        description="Example",
        manifest={},
        requested_capabilities={},
        status=SkillVersionStatus.READY,
    )

    version.package_digest = "a" * 64
    version.storage_key = "skills/a/package.zip"

    with pytest.raises(ValueError, match="package_digest is immutable"):
        version.package_digest = "b" * 64
    with pytest.raises(ValueError, match="storage_key is immutable"):
        version.storage_key = "skills/b/package.zip"


def test_import_diagnostics_and_audit_snapshots_are_persistent_contracts() -> None:
    import_columns = SkillImport.__table__.c
    assert isinstance(import_columns.diagnostics.type, JSON)
    assert isinstance(import_columns.requested_capabilities.type, JSON)
    assert isinstance(import_columns.target_revision.type, BigInteger)
    assert import_columns.target_revision.nullable
    assert "uq_skill_imports_idempotency_key" in _unique_names(SkillImport)
    assert set(import_columns.status.type.enums) == {item.value for item in SkillImportStatus}

    audit_columns = SkillAuditEvent.__table__.c
    assert isinstance(audit_columns.before_state.type, JSON)
    assert isinstance(audit_columns.after_state.type, JSON)
    assert "updated_at" not in audit_columns
    assert ("import_id", "skill_imports.id", "SET NULL") in _foreign_key_targets(SkillAuditEvent)

    installation = SkillInstallation(
        skill_id="s" * 36,
        active_version_id="v" * 36,
        settings={"default": True, "routable": True},
        revision=3,
        status=SkillInstallationStatus.ENABLED,
    )
    assert installation.revision == 3
    assert installation.settings["routable"] is True


def test_capability_grants_are_version_scoped_and_revocable() -> None:
    columns = SkillCapabilityGrant.__table__.c

    assert "uq_skill_capability_grants_installation_version" in _unique_names(SkillCapabilityGrant)
    assert ("installation_id", "skill_installations.id", "CASCADE") in _foreign_key_targets(SkillCapabilityGrant)
    assert ("skill_version_id", "skill_versions.id", "RESTRICT") in _foreign_key_targets(SkillCapabilityGrant)
    assert isinstance(columns.grants.type, JSON)
    assert isinstance(columns.revision.type, BigInteger)
    assert columns.revoked_at.nullable
    assert {
        "ix_skill_capability_grants_installation_id",
        "ix_skill_capability_grants_skill_version_id",
        "ix_skill_capability_grants_granted_by",
        "ix_skill_capability_grants_version_revoked",
    }.issubset(_index_names(SkillCapabilityGrant))


def test_run_bindings_persist_an_immutable_registry_snapshot() -> None:
    columns = SkillRunBinding.__table__.c

    assert columns.run_id.primary_key
    assert isinstance(columns.registry_revision.type, BigInteger)
    assert isinstance(columns.skill_bindings.type, JSON)
    assert isinstance(columns.effective_grants.type, JSON)
    assert "updated_at" not in columns
    assert _index_names(SkillRunBinding) == {
        "ix_skill_run_bindings_session_created",
        "ix_skill_run_bindings_user_created",
    }


def test_skill_domain_tables_compile_for_mysql() -> None:
    dialect = mysql.dialect()
    for model in SKILL_MODELS:
        ddl = str(CreateTable(model.__table__).compile(dialect=dialect))
        assert f"CREATE TABLE {model.__tablename__}" in ddl
