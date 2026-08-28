from __future__ import annotations

from sqlalchemy import CheckConstraint, Enum, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from app.models.identity_domain import AuthSession, MigrationMap, RefreshToken, Role, RoleBinding, TokenRevocation, User
from app.models.job_domain import AuditEvent, Job, JobAttempt
from app.models.projection_domain import RagGeneration, RagGenerationHead, SkillPackage, SkillPackageUpload

IDENTITY_MODELS = (User, AuthSession, RefreshToken, TokenRevocation, Role, RoleBinding, MigrationMap)
JOB_MODELS = (Job, JobAttempt, AuditEvent)
PROJECTION_MODELS = (RagGeneration, RagGenerationHead, SkillPackage, SkillPackageUpload)
FOUNDATION_MODELS = (*IDENTITY_MODELS, *JOB_MODELS, *PROJECTION_MODELS)


def _unique_names(model) -> set[str]:
    return {constraint.name for constraint in model.__table__.constraints if isinstance(constraint, UniqueConstraint) and constraint.name}


def _check_names(model) -> set[str]:
    return {constraint.name for constraint in model.__table__.constraints if isinstance(constraint, CheckConstraint) and constraint.name}


def _foreign_key_targets(model) -> set[tuple[str, str, str | None]]:
    return {
        (item.parent.name, item.target_fullname, constraint.ondelete)
        for constraint in model.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        for item in constraint.elements
    }


def test_foundation_registers_only_the_frozen_e2_table_names() -> None:
    assert {model.__tablename__ for model in FOUNDATION_MODELS} == {
        "users",
        "auth_sessions",
        "refresh_tokens",
        "token_revocations",
        "roles",
        "role_bindings",
        "migration_maps",
        "jobs",
        "job_attempts",
        "audit_events",
        "rag_generations",
        "rag_generation_heads",
        "skill_packages",
        "skill_package_uploads",
    }


def test_machine_state_uses_varchar_checks_instead_of_native_enum() -> None:
    for model in FOUNDATION_MODELS:
        for column in model.__table__.columns:
            assert not isinstance(column.type, Enum)
    assert "ck_jobs_status" in _check_names(Job)
    assert "ck_auth_sessions_status" in _check_names(AuthSession)
    assert "ck_rag_generations_status" in _check_names(RagGeneration)


def test_identity_constraints_preserve_session_family_and_scoped_role_contracts() -> None:
    assert {"uq_users_email_normalized", "uq_users_phone_e164"}.issubset(_unique_names(User))
    assert {"uq_refresh_tokens_token_digest", "uq_refresh_tokens_jti_digest"}.issubset(_unique_names(RefreshToken))
    assert "uq_token_revocations_scope_key" in _unique_names(TokenRevocation)
    assert "uq_role_bindings_subject_scope" in _unique_names(RoleBinding)
    assert "uq_migration_maps_source" in _unique_names(MigrationMap)
    assert ("user_id", "users.id", "RESTRICT") in _foreign_key_targets(AuthSession)
    assert ("session_id", "auth_sessions.id", "RESTRICT") in _foreign_key_targets(RefreshToken)


def test_job_constraints_bind_idempotency_attempts_audit_and_fencing() -> None:
    assert "uq_jobs_idempotency_scope" in _unique_names(Job)
    assert "uq_job_attempts_job_number" in _unique_names(JobAttempt)
    assert {"ck_jobs_status", "ck_jobs_attempts", "ck_jobs_fencing_token"}.issubset(_check_names(Job))
    assert ("job_id", "jobs.id", "CASCADE") in _foreign_key_targets(JobAttempt)
    assert ("job_id", "jobs.id", "RESTRICT") in _foreign_key_targets(AuditEvent)
    assert "updated_at" not in AuditEvent.__table__.columns


def test_rag_head_and_skill_double_archive_constraints_are_explicit() -> None:
    assert "uq_rag_generation_heads_owner_index" in _unique_names(RagGenerationHead)
    assert ("active_generation_id", "rag_generations.id", "RESTRICT") in _foreign_key_targets(RagGenerationHead)
    assert ("staging_generation_id", "rag_generations.id", "RESTRICT") in _foreign_key_targets(RagGenerationHead)
    assert "uq_skill_packages_package_digest" in _unique_names(SkillPackage)
    assert "uq_skill_package_uploads_request_digest" in _unique_names(SkillPackageUpload)
    assert ("package_id", "skill_packages.id", "RESTRICT") in _foreign_key_targets(SkillPackageUpload)


def test_foundation_tables_compile_to_mysql_char_datetime6_and_longblob() -> None:
    dialect = mysql.dialect()
    for model in FOUNDATION_MODELS:
        ddl = str(CreateTable(model.__table__).compile(dialect=dialect))
        assert f"CREATE TABLE {model.__tablename__}" in ddl
        assert "CHAR(36) CHARACTER SET ascii COLLATE ascii_bin" in ddl

    job_ddl = str(CreateTable(Job.__table__).compile(dialect=dialect))
    package_ddl = str(CreateTable(SkillPackage.__table__).compile(dialect=dialect))
    upload_ddl = str(CreateTable(SkillPackageUpload.__table__).compile(dialect=dialect))
    assert "DATETIME(6)" in job_ddl
    assert "LONGBLOB" in package_ddl
    assert "LONGBLOB" in upload_ddl
    assert isinstance(Job.__table__.c.status.type, String)


def test_migration_target_uuid_is_immutable() -> None:
    mapping = MigrationMap(
        migration_batch_id="batch-1",
        source_system="legacy",
        entity_type="user",
        source_id="legacy-1",
        target_uuid="11111111-1111-4111-8111-111111111111",
        source_digest="a" * 64,
    )
    mapping.target_uuid = "11111111-1111-4111-8111-111111111111"

    try:
        mapping.target_uuid = "22222222-2222-4222-8222-222222222222"
    except ValueError as exc:
        assert str(exc) == "target_uuid is immutable"
    else:
        raise AssertionError("target_uuid mutation must be rejected")
