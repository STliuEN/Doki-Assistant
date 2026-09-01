from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.db.e3_guard import (
    E3_MIGRATION_SWITCH,
    E3_PREFLIGHT_ISSUANCE_SWITCH,
    E3GuardError,
    approval_token_fingerprint,
    build_e3_preflight_record,
    database_url_fingerprint,
    issue_e3_preflight_record,
    load_guard_from_environment,
    parse_e3_target,
    validate_preflight_record,
)

DATABASE_URL = "mysql+aiomysql://doki_e3_app:secret@127.0.0.1:33327/doki_e3?charset=utf8mb4"


def _container_facts() -> dict[str, object]:
    return {
        "container_name": "doki-e3-20260831-mysql",
        "container_id": "container-id",
        "image_id": "sha256:image",
        "image_reference": "mysql:8.4",
        "running": True,
        "healthy": True,
        "networks": ["doki-e3-20260831-net"],
        "host_ports": [33327],
    }


def _record(now: datetime) -> dict[str, object]:
    return build_e3_preflight_record(
        database_url=DATABASE_URL,
        approval_token="approval",
        purposes=["migrate", "runtime", "import"],
        container_facts=_container_facts(),
        database_facts={"server_uuid": "server-uuid"},
        issued_at=now,
    )


def test_e3_target_allowlist_rejects_shared_or_wrong_databases() -> None:
    assert parse_e3_target(DATABASE_URL).role == "target"
    for value in (
        "mysql+aiomysql://root:secret@127.0.0.1:33327/doki_e3?charset=utf8mb4",
        "mysql+aiomysql://doki_e3_app:secret@127.0.0.1:3306/doki_e3?charset=utf8mb4",
        "mysql+pymysql://doki_e3_app:secret@127.0.0.1:33327/doki_e3?charset=utf8mb4",
        DATABASE_URL + "&unix_socket=/tmp/mysql.sock",
    ):
        with pytest.raises(E3GuardError):
            parse_e3_target(value)


def test_e3_preflight_binds_target_token_container_and_lifetime() -> None:
    now = datetime(2026, 9, 1, tzinfo=UTC)
    record = _record(now)
    target = validate_preflight_record(
        record,
        database_url=DATABASE_URL,
        approval_token="approval",
        purpose="runtime",
        now=now + timedelta(minutes=1),
        container_facts=_container_facts(),
    )
    assert target.role == "target"

    for field, value in (
        ("dsn_sha256", database_url_fingerprint(DATABASE_URL + "x")),
        ("approval_token_sha256", approval_token_fingerprint("wrong")),
        ("target", []),
        ("container", []),
        ("database", []),
        ("purposes", "runtime"),
    ):
        changed = dict(record)
        changed[field] = value
        with pytest.raises(E3GuardError):
            validate_preflight_record(
                changed,
                database_url=DATABASE_URL,
                approval_token="approval",
                purpose="runtime",
                now=now + timedelta(minutes=1),
                container_facts=_container_facts(),
            )


def test_non_object_preflight_fails_before_container_inspection() -> None:
    called = False

    def inspector(_name: str):
        nonlocal called
        called = True
        return _container_facts()

    with pytest.raises(E3GuardError, match="JSON object"):
        validate_preflight_record(
            [],  # type: ignore[arg-type]
            database_url=DATABASE_URL,
            approval_token="approval",
            purpose="runtime",
            container_inspector=inspector,
        )
    assert called is False


def test_environment_guard_requires_explicit_switch_and_valid_json_object(tmp_path) -> None:
    preflight = tmp_path / "preflight.json"
    preflight.write_text(json.dumps(_record(datetime.now(UTC))), encoding="utf-8")
    environment = {
        "E3_DATABASE_URL": DATABASE_URL,
        "E3_APPROVAL_TOKEN": "approval",
        "E3_PREFLIGHT_FILE": str(preflight),
    }
    with pytest.raises(E3GuardError, match="switch"):
        load_guard_from_environment("runtime", environ=environment, inspector=lambda _name: _container_facts())
    environment["E3_MIGRATION_ENABLED"] = E3_MIGRATION_SWITCH
    guard = load_guard_from_environment("runtime", environ=environment, inspector=lambda _name: _container_facts())
    assert guard.database_url == DATABASE_URL

    preflight.write_text("[]", encoding="utf-8")
    with pytest.raises(E3GuardError, match="JSON object"):
        load_guard_from_environment("runtime", environ=environment, inspector=lambda _name: _container_facts())


def test_issue_preflight_rejects_missing_switch_before_inspection() -> None:
    called = False

    def inspector(_name: str):
        nonlocal called
        called = True
        return _container_facts()

    with pytest.raises(E3GuardError, match="issuance switch"):
        asyncio.run(
            issue_e3_preflight_record(
                database_url=DATABASE_URL,
                approval_token="approval",
                purposes=["runtime"],
                issuance_switch="wrong",
                inspector=inspector,
            )
        )
    assert called is False
    assert E3_PREFLIGHT_ISSUANCE_SWITCH != E3_MIGRATION_SWITCH
