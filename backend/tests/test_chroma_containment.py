from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.core.background_init import _BackgroundInitManager
from app.rag import vector_store
from app.router import note_router
from scripts.backup_restore import create_backup


def _reset_singleton() -> None:
    vector_store.VectorStoreService._instance = None
    vector_store.VectorStoreService._initialized = False
    vector_store.VectorStoreService._restart_required = False
    vector_store.VectorStoreService._projection_health = vector_store.ChromaProjectionHealth(
        status="not_initialized",
        persist_directory=None,
        checked_at=None,
    )


def test_chroma_init_failure_preserves_persisted_directory(tmp_path, monkeypatch) -> None:
    persisted = tmp_path / "chroma"
    persisted.mkdir()
    sentinel = persisted / "sentinel.bin"
    sentinel.write_bytes(b"must-survive")
    monkeypatch.setitem(vector_store.chroma_config, "persist_directory", str(persisted))
    monkeypatch.setattr(vector_store, "get_abstract_path", lambda value: value)
    monkeypatch.setattr(
        vector_store.VectorStoreService,
        "_init_chroma",
        lambda _self, _path: (_ for _ in ()).throw(RuntimeError("corrupt metadata")),
    )
    _reset_singleton()

    with pytest.raises(vector_store.ChromaProjectionUnavailable):
        vector_store.VectorStoreService()

    assert persisted.is_dir()
    assert sentinel.read_bytes() == b"must-survive"
    health = vector_store.VectorStoreService.projection_health()
    assert health["status"] == "quarantined"
    assert health["error_type"] == "RuntimeError"
    assert Path(health["persist_directory"]) == persisted.resolve()


def test_chroma_restart_can_recover_without_deleting_projection(tmp_path, monkeypatch) -> None:
    persisted = tmp_path / "chroma"
    persisted.mkdir()
    sentinel = persisted / "sentinel.bin"
    sentinel.write_bytes(b"projection")
    attempts = iter((RuntimeError("version mismatch"), None))

    def init_projection(service, path):
        outcome = next(attempts)
        if outcome is not None:
            raise outcome
        service.persist_dir = path
        vector_store.VectorStoreService._projection_health = vector_store.ChromaProjectionHealth(
            status="ready",
            persist_directory=str(persisted.resolve()),
            checked_at="now",
        )

    monkeypatch.setitem(vector_store.chroma_config, "persist_directory", str(persisted))
    monkeypatch.setattr(vector_store, "get_abstract_path", lambda value: value)
    monkeypatch.setattr(vector_store.VectorStoreService, "_init_chroma", init_projection)
    _reset_singleton()

    with pytest.raises(vector_store.ChromaProjectionUnavailable):
        vector_store.VectorStoreService()
    _reset_singleton()
    service = vector_store.VectorStoreService()

    assert service.persist_dir == str(persisted)
    assert sentinel.read_bytes() == b"projection"
    assert vector_store.VectorStoreService.projection_health()["status"] == "ready"


@pytest.mark.parametrize(
    ("error", "label"),
    [
        (OSError("permission denied"), "permission"),
        (RuntimeError("incompatible database version"), "version"),
        (KeyError("missing collection"), "missing_collection"),
    ],
)
def test_chroma_failure_modes_quarantine_without_mutation(tmp_path, monkeypatch, error, label) -> None:
    persisted = tmp_path / label
    persisted.mkdir()
    sentinel = persisted / "projection.sqlite3"
    sentinel.write_bytes(b"original-projection")
    monkeypatch.setitem(vector_store.chroma_config, "persist_directory", str(persisted))
    monkeypatch.setattr(vector_store, "get_abstract_path", lambda value: value)

    def fail_init(_service, _path):
        raise error

    monkeypatch.setattr(vector_store.VectorStoreService, "_init_chroma", fail_init)
    _reset_singleton()

    with pytest.raises(vector_store.ChromaProjectionUnavailable):
        vector_store.VectorStoreService()

    assert sentinel.read_bytes() == b"original-projection"
    assert vector_store.VectorStoreService.projection_health()["status"] == "quarantined"


def test_explicit_projection_rebuild_requires_manifest_and_marks_restart(tmp_path, monkeypatch) -> None:
    source = tmp_path / "fixture"
    source.mkdir()
    (source / "chroma.sqlite3").write_bytes(b"rebuilt projection")
    bundle = tmp_path / "bundle"
    create_backup(artifact_kind="chroma-projection", source=source, output=bundle)
    target = tmp_path / "target"
    monkeypatch.setitem(vector_store.chroma_config, "persist_directory", str(target))

    _reset_singleton()
    result = vector_store.VectorStoreService.rebuild_projection_from_backup(bundle, target)

    assert (target / "chroma.sqlite3").read_bytes() == b"rebuilt projection"
    assert result["artifact_kind"] == "chroma-projection"
    health = vector_store.VectorStoreService.projection_health()
    assert health["status"] == "rebuild_pending_restart"
    assert Path(health["persist_directory"]) == target.resolve()


def test_explicit_projection_rebuild_does_not_retarget_active_client(tmp_path, monkeypatch) -> None:
    target = tmp_path / "target"
    target.mkdir()
    marker = target / "marker"
    marker.write_bytes(b"must-survive")
    bundle = tmp_path / "bundle"
    source = tmp_path / "source"
    source.mkdir()
    (source / "chroma.sqlite3").write_bytes(b"candidate")
    create_backup(artifact_kind="chroma-projection", source=source, output=bundle)
    monkeypatch.setitem(vector_store.chroma_config, "persist_directory", str(target))

    active = type("Active", (), {"persist_dir": str(target)})()
    vector_store.VectorStoreService._instance = active
    vector_store.VectorStoreService._initialized = True
    with pytest.raises(vector_store.ChromaProjectionUnavailable, match="restart"):
        vector_store.VectorStoreService.rebuild_projection_from_backup(bundle, target)
    assert marker.read_bytes() == b"must-survive"
    _reset_singleton()


def test_projection_rebuild_requires_restart_before_reinitialization(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "chroma.sqlite3").write_bytes(b"candidate")
    bundle = tmp_path / "bundle"
    create_backup(artifact_kind="chroma-projection", source=source, output=bundle)
    target = tmp_path / "target"
    monkeypatch.setitem(vector_store.chroma_config, "persist_directory", str(target))

    _reset_singleton()
    vector_store.VectorStoreService.rebuild_projection_from_backup(bundle, target)

    with pytest.raises(vector_store.ChromaProjectionUnavailable, match="restart"):
        vector_store.VectorStoreService()
    assert vector_store.VectorStoreService.projection_health()["status"] == "rebuild_pending_restart"
    _reset_singleton()


def test_projection_rebuild_rejects_unconfigured_target_without_mutation(tmp_path, monkeypatch) -> None:
    configured = tmp_path / "configured"
    target = tmp_path / "wrong-target"
    monkeypatch.setitem(vector_store.chroma_config, "persist_directory", str(configured))

    with pytest.raises(vector_store.ChromaProjectionUnavailable, match="configured persist directory"):
        vector_store.VectorStoreService.rebuild_projection_from_backup(tmp_path / "bundle", target)

    assert not target.exists()


def test_reset_collection_failure_fails_closed() -> None:
    class BrokenStore:
        def reset_collection(self):
            raise RuntimeError("reset failed")

    service = object.__new__(vector_store.VectorStoreService)
    with pytest.raises(RuntimeError, match="reset failed"):
        service._reset_store(BrokenStore())


def test_note_dependency_returns_503_after_chroma_failure(monkeypatch) -> None:
    manager = _BackgroundInitManager()
    manager._started = True
    manager.note_service_error = "corrupt projection"
    manager.note_service_init_done.set()
    monkeypatch.setattr(note_router, "init_manager", manager)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(note_router.ensure_note_service())

    assert exc_info.value.status_code == 503
    assert "unavailable" in exc_info.value.detail


def test_background_model_failure_releases_note_dependency(monkeypatch) -> None:
    manager = _BackgroundInitManager()

    async def fail_models():
        raise RuntimeError("model fixture failed")

    manager._init_models = fail_models
    asyncio.run(manager._initialize_all())

    assert manager.note_service_init_done.is_set()
    assert manager.note_service_error.startswith("model initialization failed:")

    monkeypatch.setattr(note_router, "init_manager", manager)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(note_router.ensure_note_service())
    assert exc_info.value.status_code == 503
