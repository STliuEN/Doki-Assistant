import runpy
from pathlib import Path

from sqlalchemy import CheckConstraint, Column, ForeignKeyConstraint, UniqueConstraint

from app.db import db_config
from app.models.embedding_config import UserEmbeddingConfig
from app.models.identity_domain import AuthSession, MigrationMap, RefreshToken, Role, RoleBinding, TokenRevocation, User
from app.models.job_domain import AuditEvent, Job, JobAttempt
from app.models.knowledge_document import KnowledgeSourceDocument
from app.models.projection_domain import RagGeneration, RagGenerationHead, SkillPackage, SkillPackageUpload
from app.models.skill_domain import (
    Skill,
    SkillAlias,
    SkillAuditEvent,
    SkillCapabilityGrant,
    SkillImport,
    SkillInstallation,
    SkillRegistryEvent,
    SkillRegistryState,
    SkillRunBinding,
    SkillVersion,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_runtime_database_module_contains_no_schema_mutation() -> None:
    source = (BACKEND_ROOT / "app" / "db" / "db_config.py").read_text(encoding="utf-8")

    assert "create_all" not in source
    assert "ALTER TABLE" not in source
    assert "_migrate_columns" not in source


def test_required_revision_matches_the_alembic_head() -> None:
    chain = (
        ("20260828_0003_identity_auth.py", "20260824_0002"),
        ("20260828_0004_jobs_audit.py", "20260828_0003_identity_auth"),
        ("20260828_0005_rag_skill.py", "20260828_0004_jobs_audit"),
    )

    namespaces = []
    for filename, expected_parent in chain:
        revision = BACKEND_ROOT / "alembic" / "versions" / filename
        namespace = runpy.run_path(str(revision))
        assert revision.is_file()
        assert namespace["down_revision"] == expected_parent
        namespaces.append(namespace)

    assert namespaces[-1]["revision"] == db_config.E2_DATABASE_SCHEMA_REVISION

    e3_chain = (
        ("20260831_0006_e3_auth_runtime.py", db_config.E2_DATABASE_SCHEMA_REVISION),
        ("20260901_0007_e3_auth_constraints.py", "20260831_0006_e3_auth_runtime"),
    )
    for filename, expected_parent in e3_chain:
        namespace = runpy.run_path(str(BACKEND_ROOT / "alembic" / "versions" / filename))
        assert namespace["down_revision"] == expected_parent
    assert namespace["revision"] == db_config.DATABASE_SCHEMA_REVISION


def test_baseline_unique_constraints_match_original_models() -> None:
    revision = BACKEND_ROOT / "alembic" / "versions" / "20260817_0001_baseline.py"

    assert revision.is_file()

    class OperationRecorder:
        def __init__(self) -> None:
            self.tables: dict[str, tuple] = {}

        def create_table(self, name: str, *elements) -> None:
            self.tables[name] = elements

        def create_index(self, *args, **kwargs) -> None:
            return None

    recorder = OperationRecorder()
    namespace = runpy.run_path(str(revision))
    upgrade = namespace["upgrade"]
    upgrade.__globals__["op"] = recorder
    upgrade()

    expected_constraints = {
        constraint.name
        for table in (KnowledgeSourceDocument.__table__, UserEmbeddingConfig.__table__)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    baseline_constraints = {element.name for elements in recorder.tables.values() for element in elements if isinstance(element, UniqueConstraint)}
    assert baseline_constraints == expected_constraints


def test_skill_domain_migration_matches_model_contract() -> None:
    revision = BACKEND_ROOT / "alembic" / "versions" / "20260824_0002_skill_domain.py"

    class OperationRecorder:
        def __init__(self) -> None:
            self.tables: dict[str, tuple] = {}
            self.indexes: set[tuple[str, str]] = set()

        def create_table(self, name: str, *elements) -> None:
            self.tables[name] = elements

        def create_index(self, name: str, table_name: str, *args, **kwargs) -> None:
            self.indexes.add((table_name, name))

        def execute(self, *args, **kwargs) -> None:
            return None

    recorder = OperationRecorder()
    namespace = runpy.run_path(str(revision))
    upgrade = namespace["upgrade"]
    upgrade.__globals__["op"] = recorder
    upgrade()

    models = (
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
    assert set(recorder.tables) == {model.__tablename__ for model in models}

    for model in models:
        elements = recorder.tables[model.__tablename__]
        migration_columns = {element.name for element in elements if isinstance(element, Column)}
        assert migration_columns == set(model.__table__.columns.keys())

        migration_unique = {element.name for element in elements if isinstance(element, UniqueConstraint) and element.name}
        model_unique = {element.name for element in model.__table__.constraints if isinstance(element, UniqueConstraint) and element.name}
        assert migration_unique == model_unique

        migration_foreign_keys = {
            (
                tuple(element.column_keys),
                tuple(item.target_fullname for item in element.elements),
                element.ondelete,
            )
            for element in elements
            if isinstance(element, ForeignKeyConstraint)
        }
        model_foreign_keys = {
            (
                tuple(element.column_keys),
                tuple(item.target_fullname for item in element.elements),
                element.ondelete,
            )
            for element in model.__table__.constraints
            if isinstance(element, ForeignKeyConstraint)
        }
        assert migration_foreign_keys == model_foreign_keys

        migration_indexes = {name for table, name in recorder.indexes if table == model.__tablename__}
        model_indexes = {index.name for index in model.__table__.indexes}
        assert migration_indexes == model_indexes


def test_e2_foundation_migrations_match_model_contract_without_altering_legacy_tables() -> None:
    revisions = (
        (
            "20260828_0003_identity_auth.py",
            (User, AuthSession, RefreshToken, TokenRevocation, Role, RoleBinding, MigrationMap),
        ),
        ("20260828_0004_jobs_audit.py", (Job, JobAttempt, AuditEvent)),
        ("20260828_0005_rag_skill.py", (RagGeneration, RagGenerationHead, SkillPackage, SkillPackageUpload)),
    )

    class OperationRecorder:
        def __init__(self) -> None:
            self.tables: dict[str, tuple] = {}
            self.indexes: set[tuple[str, str]] = set()

        def create_table(self, name: str, *elements) -> None:
            self.tables[name] = elements

        def create_index(self, name: str, table_name: str, *args, **kwargs) -> None:
            self.indexes.add((table_name, name))

        def alter_column(self, *args, **kwargs) -> None:
            raise AssertionError("E2 revisions must not alter legacy tables")

        def add_column(self, *args, **kwargs) -> None:
            raise AssertionError("E2 revisions must not add columns to legacy tables")

    for filename, models in revisions:
        namespace = runpy.run_path(str(BACKEND_ROOT / "alembic" / "versions" / filename))
        recorder = OperationRecorder()
        upgrade = namespace["upgrade"]
        upgrade.__globals__["op"] = recorder
        upgrade()

        assert set(recorder.tables) == {model.__tablename__ for model in models}
        for model in models:
            elements = recorder.tables[model.__tablename__]
            migration_columns = {element.name: element for element in elements if isinstance(element, Column)}
            assert set(migration_columns) == set(model.__table__.columns.keys())
            for name, model_column in model.__table__.columns.items():
                assert migration_columns[name].nullable == model_column.nullable

            for constraint_type in (UniqueConstraint, CheckConstraint):
                migration_names = {element.name for element in elements if isinstance(element, constraint_type) and element.name}
                model_names = {element.name for element in model.__table__.constraints if isinstance(element, constraint_type) and element.name}
                if model is User and constraint_type is UniqueConstraint:
                    model_names.remove("uq_users_username")
                assert migration_names == model_names

            migration_foreign_keys = {
                (tuple(element.column_keys), tuple(item.target_fullname for item in element.elements), element.ondelete)
                for element in elements
                if isinstance(element, ForeignKeyConstraint)
            }
            model_foreign_keys = {
                (tuple(element.column_keys), tuple(item.target_fullname for item in element.elements), element.ondelete)
                for element in model.__table__.constraints
                if isinstance(element, ForeignKeyConstraint)
            }
            assert migration_foreign_keys == model_foreign_keys

            migration_indexes = {name for table, name in recorder.indexes if table == model.__tablename__}
            model_indexes = {index.name for index in model.__table__.indexes}
            assert migration_indexes == model_indexes
