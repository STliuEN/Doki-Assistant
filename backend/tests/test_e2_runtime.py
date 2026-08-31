from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.db.e2_guard import (
    E2_MIGRATION_SWITCH,
    E2GuardError,
    E2MigrationGuard,
    approval_token_fingerprint,
    database_url_fingerprint,
    parse_e2_target,
    verify_database_fingerprint,
)
from app.jobs.e2_runtime import E2_RUNNER_POOL_SIZE, E2RunnerRuntime, build_e2_runner

SOURCE_URL = "mysql+aiomysql://e2_migrator:secret@127.0.0.1:33317/doki_e2?charset=utf8mb4"
RESTORE_URL = "mysql+aiomysql://e2_migrator:secret@127.0.0.1:33318/doki_e2?charset=utf8mb4"


def _run(coro):
    return asyncio.run(coro)


def _container_facts(*, restore: bool = False) -> dict[str, object]:
    return {
        "container_name": "doki-e2-20260828-mysql-restore" if restore else "doki-e2-20260828-mysql",
        "container_id": "restore-container-id" if restore else "container-id",
        "image_id": "sha256:image",
        "image_reference": "mysql:8.4",
        "running": True,
        "networks": ["doki-e2-20260828-net"],
        "host_ports": [33318 if restore else 33317],
    }


def _preflight(database_url: str = SOURCE_URL, *, purpose: str = "runner", restore: bool = False) -> dict[str, object]:
    now = datetime.now(UTC)
    target = parse_e2_target(database_url)
    token = "approval"
    return {
        "schema_version": 1,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=10)).isoformat(),
        "purposes": [purpose],
        "dsn_sha256": database_url_fingerprint(database_url),
        "approval_token_sha256": approval_token_fingerprint(token),
        "target": {
            "role": target.role,
            "host": target.host,
            "port": target.port,
            "database": target.database,
            "container_name": target.container_name,
        },
        "container": _container_facts(restore=restore),
        "database": {"server_uuid": "server-uuid"},
    }


def _environment(tmp_path, *, database_url: str = SOURCE_URL, purpose: str = "runner", restore: bool = False):
    preflight = tmp_path / ("restore-preflight.json" if restore else "preflight.json")
    preflight.write_text(json.dumps(_preflight(database_url, purpose=purpose, restore=restore)), encoding="utf-8")
    return {
        "E2_RUNNER_ENABLED": "true",
        "E2_MIGRATION_ENABLED": E2_MIGRATION_SWITCH,
        "E2_DATABASE_URL": database_url,
        "E2_APPROVAL_TOKEN": "approval",
        "E2_PREFLIGHT_FILE": str(preflight),
    }


def test_disabled_runner_build_is_inert(monkeypatch) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("disabled E2 runner must not create an engine")

    monkeypatch.setattr("app.jobs.e2_runtime.create_async_engine", forbidden)
    assert build_e2_runner(environ={"E2_RUNNER_ENABLED": "false"}) is None


def test_enabled_runner_rejects_missing_preflight_before_engine_creation(tmp_path, monkeypatch) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("guard failure must happen before engine creation")

    monkeypatch.setattr("app.jobs.e2_runtime.create_async_engine", forbidden)
    values = {
        "E2_RUNNER_ENABLED": "true",
        "E2_MIGRATION_ENABLED": E2_MIGRATION_SWITCH,
        "E2_DATABASE_URL": SOURCE_URL,
        "E2_APPROVAL_TOKEN": "approval",
        "E2_PREFLIGHT_FILE": str(tmp_path / "missing.json"),
    }
    with pytest.raises(RuntimeError, match="preflight file does not exist"):
        build_e2_runner(environ=values)


def test_restore_target_is_rejected_before_engine_creation(tmp_path, monkeypatch) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("restore target must be rejected before engine creation")

    monkeypatch.setattr("app.jobs.e2_runtime.create_async_engine", forbidden)
    values = _environment(tmp_path, database_url=RESTORE_URL, restore=True)
    with pytest.raises(RuntimeError, match="approved source database"):
        build_e2_runner(environ=values, inspector=lambda _name: _container_facts(restore=True))


def test_runner_uses_only_the_explicit_environment_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JOB_LEASE_SECONDS", "999")
    values = _environment(tmp_path)
    values["JOB_LEASE_SECONDS"] = "77"
    runtime = build_e2_runner(environ=values, inspector=lambda _name: _container_facts())
    assert runtime is not None
    try:
        assert runtime.runner.config.lease_seconds == 77
    finally:
        _run(runtime.engine.dispose())


def test_runtime_start_verifies_target_before_runner_start(monkeypatch) -> None:
    order: list[str] = []

    async def verify(_runtime):
        order.append("verify")

    class FakeRunner:
        async def start(self):
            order.append("start")

    runtime = E2RunnerRuntime(
        runner=FakeRunner(),  # type: ignore[arg-type]
        engine=object(),  # type: ignore[arg-type]
        guard=object(),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(E2RunnerRuntime, "verify_target", verify)
    _run(runtime.start())
    assert order == ["verify", "start"]


def test_runner_pool_reserves_lock_and_job_connections(tmp_path) -> None:
    runtime = build_e2_runner(
        environ=_environment(tmp_path),
        inspector=lambda _name: _container_facts(),
    )
    assert runtime is not None
    try:
        pool = runtime.engine.sync_engine.pool
        assert pool.size() >= E2_RUNNER_POOL_SIZE
        assert E2_RUNNER_POOL_SIZE >= 2
    finally:
        _run(runtime.engine.dispose())


class _Result:
    def __init__(self, row):
        self._row = row

    def one(self):
        return self._row


class _Connection:
    def __init__(self, row):
        self.row = row

    def execute(self, _statement):
        return _Result(self.row)


def test_database_fingerprint_drift_is_rejected() -> None:
    record = _preflight()
    guard = E2MigrationGuard(
        database_url=SOURCE_URL,
        target=parse_e2_target(SOURCE_URL),
        preflight=record,
    )
    connection = _Connection(
        ("doki_e2", "different-server", "+00:00", "STRICT_TRANS_TABLES", 256 * 1024 * 1024, "REPEATABLE-READ")
    )
    with pytest.raises(E2GuardError, match="server UUID drifted"):
        verify_database_fingerprint(connection, guard)  # type: ignore[arg-type]
