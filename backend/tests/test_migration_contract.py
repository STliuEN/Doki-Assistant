import runpy
from pathlib import Path

from sqlalchemy import UniqueConstraint

from app.db import db_config
from app.models.embedding_config import UserEmbeddingConfig
from app.models.knowledge_document import KnowledgeSourceDocument

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_runtime_database_module_contains_no_schema_mutation() -> None:
    source = (BACKEND_ROOT / "app" / "db" / "db_config.py").read_text(encoding="utf-8")

    assert "create_all" not in source
    assert "ALTER TABLE" not in source
    assert "_migrate_columns" not in source


def test_required_revision_matches_the_alembic_baseline() -> None:
    revision = BACKEND_ROOT / "alembic" / "versions" / "20260817_0001_baseline.py"
    source = revision.read_text(encoding="utf-8")

    assert revision.is_file()
    assert f'revision = "{db_config.DATABASE_SCHEMA_REVISION}"' in source

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
    baseline_constraints = {
        element.name
        for elements in recorder.tables.values()
        for element in elements
        if isinstance(element, UniqueConstraint)
    }
    assert baseline_constraints == expected_constraints
