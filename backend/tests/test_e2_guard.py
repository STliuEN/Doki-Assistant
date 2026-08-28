from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.db.e2_guard import (
    E2_MIGRATION_SWITCH,
    E2GuardError,
    approval_token_fingerprint,
    database_url_fingerprint,
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
        with pytest.raises(E2GuardError, match=r"allowlist|mysql\+aiomysql"):
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
