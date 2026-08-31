from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.db.e2_guard import (
    E2_MIGRATION_SWITCH,
    E2_PREFLIGHT_ISSUANCE_SWITCH,
    E2GuardError,
    approval_token_fingerprint,
    build_e2_preflight_record,
    database_url_fingerprint,
    issue_e2_preflight_record,
    load_guard_from_environment,
    parse_e2_target,
    validate_preflight_record,
)

DATABASE_URL = "mysql+aiomysql://e2_migrator:secret@127.0.0.1:33317/doki_e2?charset=utf8mb4"


def _container_facts() -> dict:
    return {
        "container_name": "doki-e2-20260828-mysql",
        "container_id": "container-id",
        "image_id": "sha256:image",
        "image_reference": "mysql:8.4",
        "running": True,
        "networks": ["doki-e2-20260828-net"],
        "host_ports": [33317],
    }


def _record(now: datetime, token: str = "approval") -> dict:
    return {
        "schema_version": 1,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=15)).isoformat(),
        "purposes": ["migrate", "dump"],
        "dsn_sha256": database_url_fingerprint(DATABASE_URL),
        "approval_token_sha256": approval_token_fingerprint(token),
        "target": {
            "role": "source",
            "host": "127.0.0.1",
            "port": 33317,
            "database": "doki_e2",
            "container_name": "doki-e2-20260828-mysql",
        },
        "container": _container_facts(),
        "database": {"server_uuid": "server-uuid"},
    }


def test_target_allowlist_rejects_default_and_e1_style_connections() -> None:
    assert parse_e2_target(DATABASE_URL).role == "source"
    for value in (
        "mysql+aiomysql://root:secret@localhost:3306/chat_history?charset=utf8mb4",
        "mysql+aiomysql://root:secret@127.0.0.1:3306/doki_e2?charset=utf8mb4",
        "mysql+aiomysql://root:secret@127.0.0.1:33317/other?charset=utf8mb4",
        "mysql+pymysql://root:secret@127.0.0.1:33317/doki_e2?charset=utf8mb4",
    ):
        with pytest.raises(E2GuardError, match=r"allowlist|mysql\+aiomysql|privileged shared"):
            parse_e2_target(value)


def test_target_requires_exact_query_and_dedicated_user() -> None:
    for value in (
        "mysql+aiomysql://root:secret@127.0.0.1:33317/doki_e2?charset=utf8mb4",
        "mysql+aiomysql://e2_migrator:secret@127.0.0.1:33317/doki_e2?charset=utf8mb4&unix_socket=/tmp/mysql.sock",
        "mysql+aiomysql://e2_migrator:secret@127.0.0.1:33317/doki_e2?charset=utf8mb4&init_command=SET%20sql_mode%3DSTRICT_TRANS_TABLES",
    ):
        with pytest.raises(E2GuardError):
            parse_e2_target(value)


def test_preflight_binds_target_dsn_token_container_and_lifetime() -> None:
    now = datetime(2026, 8, 28, 2, 0, tzinfo=UTC)
    record = _record(now)

    target = validate_preflight_record(
        record,
        database_url=DATABASE_URL,
        approval_token="approval",
        purpose="migrate",
        now=now + timedelta(minutes=5),
        container_facts=_container_facts(),
    )
    assert target.container_name == "doki-e2-20260828-mysql"

    cases = (
        ({**record, "dsn_sha256": "0" * 64}, "fingerprint"),
        ({**record, "approval_token_sha256": "0" * 64}, "approval token"),
        ({**record, "purposes": ["dump"]}, "does not authorize"),
    )
    for changed, message in cases:
        with pytest.raises(E2GuardError, match=message):
            validate_preflight_record(
                changed,
                database_url=DATABASE_URL,
                approval_token="approval",
                purpose="migrate",
                now=now + timedelta(minutes=5),
                container_facts=_container_facts(),
            )

    with pytest.raises(E2GuardError, match="not currently valid"):
        validate_preflight_record(
            record,
            database_url=DATABASE_URL,
            approval_token="approval",
            purpose="migrate",
            now=now + timedelta(minutes=15),
            container_facts=_container_facts(),
        )


def test_environment_guard_requires_explicit_switch_and_preflight(tmp_path) -> None:
    now = datetime.now(UTC)
    preflight = tmp_path / "preflight.json"
    preflight.write_text(json.dumps(_record(now)), encoding="utf-8")
    environment = {
        "E2_DATABASE_URL": DATABASE_URL,
        "E2_APPROVAL_TOKEN": "approval",
        "E2_PREFLIGHT_FILE": str(preflight),
    }
    with pytest.raises(E2GuardError, match="switch"):
        load_guard_from_environment("migrate", environ=environment, inspector=lambda _name: _container_facts())

    environment["E2_MIGRATION_ENABLED"] = E2_MIGRATION_SWITCH
    guard = load_guard_from_environment("migrate", environ=environment, inspector=lambda _name: _container_facts())
    assert guard.database_url == DATABASE_URL


def test_container_drift_is_rejected() -> None:
    now = datetime(2026, 8, 28, 2, 0, tzinfo=UTC)
    facts = _container_facts()
    facts["image_id"] = "sha256:changed"
    with pytest.raises(E2GuardError, match="image_id drifted"):
        validate_preflight_record(
            _record(now),
            database_url=DATABASE_URL,
            approval_token="approval",
            purpose="migrate",
            now=now + timedelta(minutes=1),
            container_facts=facts,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("purposes", "runner", "purposes must be a list"),
        ("purposes", [1], "purposes must be a list"),
        ("target", [], "target does not match"),
        ("container", [], "container facts are missing"),
        ("database", [], "database facts are missing"),
        ("database", {"server_uuid": ""}, "server_uuid must be a non-empty string"),
        ("database", {"server_uuid": 123}, "server_uuid must be a non-empty string"),
    ],
)
def test_malformed_preflight_records_fail_closed(field: str, value: object, message: str) -> None:
    now = datetime(2026, 8, 28, 2, 0, tzinfo=UTC)
    record = _record(now)
    record[field] = value
    with pytest.raises(E2GuardError, match=message):
        validate_preflight_record(
            record,
            database_url=DATABASE_URL,
            approval_token="approval",
            purpose="migrate",
            now=now + timedelta(minutes=1),
            container_facts=_container_facts(),
        )


def test_non_object_preflight_record_fails_before_container_inspection() -> None:
    called = False

    def inspector(_name: str):
        nonlocal called
        called = True
        return _container_facts()

    with pytest.raises(E2GuardError, match="JSON object"):
        validate_preflight_record(
            [],  # type: ignore[arg-type]
            database_url=DATABASE_URL,
            approval_token="approval",
            purpose="migrate",
            container_inspector=inspector,
        )
    assert called is False


def test_build_preflight_record_binds_inspected_facts_and_limits_lifetime() -> None:
    issued_at = datetime(2026, 8, 28, 2, 0, tzinfo=UTC)
    record = build_e2_preflight_record(
        database_url=DATABASE_URL,
        approval_token="approval",
        purposes=["dump", "inventory"],
        container_facts=_container_facts(),
        database_facts={"server_uuid": "server-uuid"},
        issued_at=issued_at,
        lifetime_seconds=60,
    )

    assert record["issued_at"] == issued_at.isoformat()
    assert record["expires_at"] == (issued_at + timedelta(seconds=60)).isoformat()
    assert record["target"]["role"] == "source"
    assert record["database"] == {"server_uuid": "server-uuid"}

    with pytest.raises(E2GuardError, match="between 1 and 900"):
        build_e2_preflight_record(
            database_url=DATABASE_URL,
            approval_token="approval",
            purposes=["dump"],
            container_facts=_container_facts(),
            database_facts={"server_uuid": "server-uuid"},
            issued_at=issued_at,
            lifetime_seconds=901,
        )


def test_issue_preflight_inspects_container_and_database_before_issuing(monkeypatch) -> None:
    class Result:
        def one(self):
            return ("doki_e2", "server-uuid", "+00:00", "STRICT_TRANS_TABLES", 256 * 1024 * 1024, "REPEATABLE-READ")

    class SyncConnection:
        def execute(self, _statement):
            return Result()

    class AsyncConnection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def run_sync(self, callback):
            return callback(SyncConnection())

    class Engine:
        def connect(self):
            return AsyncConnection()

        async def dispose(self):
            return None

    created: list[str] = []

    def fake_engine(url, **_kwargs):
        created.append(url)
        return Engine()

    monkeypatch.setattr("sqlalchemy.ext.asyncio.create_async_engine", fake_engine)
    record = asyncio.run(
        issue_e2_preflight_record(
            database_url=DATABASE_URL,
            approval_token="approval",
            purposes=["dump", "runner"],
            issuance_switch=E2_PREFLIGHT_ISSUANCE_SWITCH,
            lifetime_seconds=120,
            inspector=lambda _name: _container_facts(),
        )
    )

    assert created == [DATABASE_URL]
    assert record["purposes"] == ["dump", "runner"]
    assert record["database"]["server_uuid"] == "server-uuid"


def test_issue_preflight_rejects_missing_issuance_switch_before_inspection() -> None:
    called = False

    def inspector(_name: str):
        nonlocal called
        called = True
        return _container_facts()

    with pytest.raises(E2GuardError, match="issuance switch"):
        asyncio.run(
            issue_e2_preflight_record(
                database_url=DATABASE_URL,
                approval_token="approval",
                purposes=["dump"],
                issuance_switch="wrong-switch",
                inspector=inspector,
            )
        )
    assert called is False
