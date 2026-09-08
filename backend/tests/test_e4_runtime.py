from types import SimpleNamespace

import pytest

from app.jobs import e4_runtime


def test_e4_disabled_runner_never_inspects_or_creates_engine(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Disabled runner must be inert")
    monkeypatch.setattr(e4_runtime, "load_guard_from_environment", forbidden)
    monkeypatch.setattr(e4_runtime, "create_async_engine", forbidden)
    assert e4_runtime.build_e4_runner(environ={}) is None
    assert e4_runtime.build_e4_runner(environ={"E4_MIGRATION_ENABLED": "enabled", "E4_RUNNER_ENABLED": "false"}) is None


def test_e4_runner_rejects_non_target_before_engine_creation(monkeypatch):
    monkeypatch.setattr(e4_runtime, "load_guard_from_environment", lambda *_args, **_kwargs: SimpleNamespace(target=SimpleNamespace(role="restore")))
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Rejected target must not construct an engine")
    monkeypatch.setattr(e4_runtime, "create_async_engine", forbidden)
    with pytest.raises(RuntimeError, match="target role"):
        e4_runtime.build_e4_runner(environ={"E4_MIGRATION_ENABLED": "enabled"})
