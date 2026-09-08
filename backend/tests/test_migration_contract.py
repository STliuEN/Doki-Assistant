import asyncio
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import CheckConstraint, Column, ForeignKeyConstraint, UniqueConstraint

from alembic import context
from app.db import db_config, e4_guard
from app.models.chat_history import ChatMessage, ChatSession
from app.models.e4_migration import E4MigrationBatch, E4MigrationEntity, MediaAsset
from app.models.embedding_config import UserEmbeddingConfig
from app.models.identity_domain import AuthSession, MigrationMap, RefreshToken, Role, RoleBinding, TokenRevocation, User
from app.models.job_domain import AuditEvent, Job, JobAttempt
from app.models.knowledge_document import KnowledgeSourceDocument
from app.models.memory_item import MemoryItem
from app.models.model_config import UserModelConfig
from app.models.note import Note
from app.models.note_template import NoteTemplate
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


def test_e4_runtime_guard_receives_fresh_container_inspector(monkeypatch):
    captured = {}

    def stop_at_guard(purpose, **options):
        captured.update({"purpose": purpose, **options})
        raise RuntimeError("stop before database access")

    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setattr(db_config, "E4_PROCESS_ENVIRONMENT", {"E4_MIGRATION_ENABLED": e4_guard.E4_MIGRATION_SWITCH})
    monkeypatch.setattr(db_config, "load_guard_from_environment", stop_at_guard)
    monkeypatch.setattr(db_config, "inspect_e4_container", e4_guard.inspect_e4_container, raising=False)
    with pytest.raises(RuntimeError, match="stop before database access"):
        asyncio.run(db_config.verify_database_schema())
    assert captured["purpose"] == "runtime"
    assert captured.get("container_inspector") is e4_guard.inspect_e4_container


def test_e4_alembic_guard_receives_fresh_container_inspector(monkeypatch):
    captured = {}

    def stop_at_guard(purpose, **options):
        captured.update({"purpose": purpose, **options})
        raise RuntimeError("stop before database access")

    monkeypatch.setenv("E4_MIGRATION_ENABLED", e4_guard.E4_MIGRATION_SWITCH)
    monkeypatch.setattr(e4_guard, "load_guard_from_environment", stop_at_guard)
    monkeypatch.setattr(context, "config", SimpleNamespace(), raising=False)
    with pytest.raises(RuntimeError, match="stop before database access"):
        runpy.run_path(str(BACKEND_ROOT / "alembic" / "env.py"))
    assert captured["purpose"] == "migrate"
    assert captured.get("container_inspector") is e4_guard.inspect_e4_container


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
    assert namespace["revision"] == db_config.E3_DATABASE_SCHEMA_REVISION

    e4_revision = runpy.run_path(str(BACKEND_ROOT / "alembic" / "versions" / "20260905_0008_e4_business_shadow.py"))
    assert e4_revision["down_revision"] == db_config.E3_DATABASE_SCHEMA_REVISION
    assert e4_revision["revision"] == db_config.DATABASE_SCHEMA_REVISION


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
        if isinstance(constraint, UniqueConstraint) and constraint.name in {"uq_knowledge_source_user_md5", "uq_user_embedding_config_user_id"}
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
    historical_only_columns = {
        "skill_run_bindings": {"canonical_session_id", "canonical_user_id"},
    }
    assert set(recorder.tables) == {model.__tablename__ for model in models}

    for model in models:
        elements = recorder.tables[model.__tablename__]
        migration_columns = {element.name for element in elements if isinstance(element, Column)}
        model_columns = set(model.__table__.columns.keys()) - historical_only_columns.get(model.__tablename__, set())
        assert migration_columns == model_columns

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
            and all(item.parent.name not in historical_only_columns.get(model.__tablename__, set()) for item in element.elements)
        }
        assert migration_foreign_keys == model_foreign_keys

        migration_indexes = {name for table, name in recorder.indexes if table == model.__tablename__}
        model_indexes = {
            index.name
            for index in model.__table__.indexes
            if not any(column.name in historical_only_columns.get(model.__tablename__, set()) for column in index.columns)
        }
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


def test_e4_revision_matches_shadow_columns_and_new_table_contract() -> None:
    revision = BACKEND_ROOT / "alembic" / "versions" / "20260905_0008_e4_business_shadow.py"

    class OperationRecorder:
        def __init__(self) -> None:
            self.tables: dict[str, tuple] = {}
            self.added_columns: dict[str, set[str]] = {}
            self.indexes: set[tuple[str, str]] = set()
            self.uniques: set[tuple[str, str]] = set()
            self.foreign_keys: set[tuple[str, str, str, tuple[str, ...], tuple[str, ...], str | None]] = set()
            self.checks: set[tuple[str, str, str]] = set()

        def create_table(self, name: str, *elements) -> None:
            self.tables[name] = elements
            self.checks.update(
                (name, element.name, str(element.sqltext))
                for element in elements
                if isinstance(element, CheckConstraint) and element.name
            )

        def add_column(self, table_name: str, column) -> None:
            self.added_columns.setdefault(table_name, set()).add(column.name)

        def create_index(self, name: str, table_name: str, *args, **kwargs) -> None:
            del args, kwargs
            self.indexes.add((table_name, name))

        def create_unique_constraint(self, name: str, table_name: str, columns) -> None:
            self.uniques.add((table_name, name))

        def create_foreign_key(
            self,
            name: str,
            source_table: str,
            referent_table: str,
            local_cols,
            remote_cols,
            **kwargs,
        ) -> None:
            self.foreign_keys.add(
                (
                    source_table,
                    referent_table,
                    name,
                    tuple(local_cols),
                    tuple(remote_cols),
                    kwargs.get("ondelete"),
                )
            )

        def create_check_constraint(self, name: str, table_name: str, condition: str) -> None:
            self.checks.add((table_name, name, str(condition)))

    recorder = OperationRecorder()
    namespace = runpy.run_path(str(revision))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["upgrade"]()

    assert recorder.added_columns == {
        "chat_sessions": {"canonical_id", "canonical_user_id"},
        "chat_messages": {"canonical_id", "canonical_session_id", "content_digest"},
        "knowledge_source_documents": {"canonical_id", "canonical_user_id", "content_digest", "artifact_digest"},
        "memory_items": {"canonical_id", "canonical_user_id", "content_digest"},
        "note_templates": {"canonical_id", "canonical_user_id", "content_digest"},
        "notes": {"canonical_id", "canonical_user_id", "content_digest"},
        "user_embedding_configs": {"canonical_id", "canonical_user_id", "content_digest"},
        "user_model_configs": {"canonical_id", "canonical_user_id", "content_digest", "api_key_key_version"},
        "skill_run_bindings": {"canonical_session_id", "canonical_user_id"},
    }

    models = (E4MigrationBatch, E4MigrationEntity, MediaAsset)
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
                model.__tablename__,
                item.target_fullname.split(".")[0],
                "",
                tuple(element.column_keys),
                tuple(foreign_key.target_fullname.split(".")[-1] for foreign_key in element.elements),
                element.ondelete,
            )
            for element in elements
            if isinstance(element, ForeignKeyConstraint)
            for item in element.elements[:1]
        }
        model_foreign_keys = {
            (
                model.__tablename__,
                item.target_fullname.split(".")[0],
                "",
                tuple(element.column_keys),
                tuple(foreign_key.target_fullname.split(".")[-1] for foreign_key in element.elements),
                element.ondelete,
            )
            for element in model.__table__.constraints
            if isinstance(element, ForeignKeyConstraint)
            for item in element.elements[:1]
        }
        assert migration_foreign_keys == model_foreign_keys
        migration_indexes = {name for table, name in recorder.indexes if table == model.__tablename__}
        assert migration_indexes == {index.name for index in model.__table__.indexes}

    expected_existing_uniques = {
        (table, name)
        for table, name in (
            ("chat_sessions", "uq_chat_sessions_canonical_id"),
            ("chat_messages", "uq_chat_messages_canonical_id"),
            ("knowledge_source_documents", "uq_knowledge_source_canonical_id"),
            ("memory_items", "uq_memory_items_canonical_id"),
            ("note_templates", "uq_note_templates_canonical_id"),
            ("notes", "uq_notes_canonical_id"),
            ("user_embedding_configs", "uq_user_embedding_configs_canonical_id"),
            ("user_model_configs", "uq_user_model_configs_canonical_id"),
        )
    }
    assert expected_existing_uniques <= recorder.uniques
    assert ("skill_run_bindings", "fk_skill_run_bindings_canonical_user") in {
        (table, name) for table, _referent, name, _local, _remote, _ondelete in recorder.foreign_keys
    }

    shadow_models = (
        ChatSession,
        ChatMessage,
        KnowledgeSourceDocument,
        MemoryItem,
        NoteTemplate,
        Note,
        UserEmbeddingConfig,
        UserModelConfig,
        SkillRunBinding,
    )
    expected_checks = {
        (model.__tablename__, constraint.name, str(constraint.sqltext))
        for model in (*shadow_models, *models)
        for constraint in model.__table__.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name
    }
    assert recorder.checks == expected_checks
