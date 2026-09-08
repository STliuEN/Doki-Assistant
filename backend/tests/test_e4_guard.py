from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.db.e4_guard import (
    E4_MIGRATION_SWITCH,
    E4_PREFLIGHT_ISSUANCE_SWITCH,
    E4GuardError,
    E4Target,
    allowlist_fingerprint,
    approval_token_fingerprint,
    build_e4_preflight_record,
    database_url_fingerprint,
    e4_target_record,
    issue_e4_preflight_record,
    load_guard_from_config,
    parse_e4_allowlist,
    parse_e4_target,
    validate_preflight_record,
)

ALLOWLIST = {
    "schema_version": 1,
    "targets": [
        {
            "id": "legacy-a",
            "role": "source",
            "host": "127.0.0.1",
            "port": 3307,
            "database": "legacy_a",
            "server_uuid": "uuid-source-a",
            "credential_ref": "secret://e4/source-a",
            "database_username": "e4_source_a",
            "read_only": True,
        },
        {
            "id": "legacy-b",
            "role": "source",
            "host": "127.0.0.1",
            "port": 3308,
            "database": "legacy_b",
            "server_uuid": "uuid-source-b",
            "credential_ref": "secret://e4/source-b",
            "database_username": "e4_source_b",
            "read_only": True,
        },
        {
            "id": "final",
            "role": "target",
            "host": "127.0.0.1",
            "port": 3306,
            "database": "e4_final",
            "server_uuid": "uuid-final",
            "credential_ref": "secret://e4/final",
            "database_username": "e4_app",
        },
        {
            "id": "restore",
            "role": "restore",
            "host": "127.0.0.1",
            "port": 3316,
            "database": "e4_restore",
            "server_uuid": "uuid-restore",
            "credential_ref": "secret://e4/restore",
            "database_username": "e4_restore",
        },
    ],
}

TARGET_URL = "mysql+aiomysql://e4_app:runtime-secret@127.0.0.1:3306/e4_final?charset=utf8mb4"
TOPOLOGY_TARGET_URL = "mysql+aiomysql://doki_e4_app:runtime-secret@127.0.0.1:33427/doki_e4?charset=utf8mb4"

TOPOLOGY_ALLOWLIST = {
    "schema_version": 1,
    "targets": [
        ALLOWLIST["targets"][0],
        {
            **ALLOWLIST["targets"][2],
            "port": 33427,
            "database": "doki_e4",
            "database_username": "doki_e4_app",
            "container_name": "doki-e4-20260903-mysql",
            "container_id": "container-target",
            "image_reference": "mysql:8.4",
            "network": "doki-e4-20260903-net",
            "image_id": "sha256:mysql-target",
        },
        {
            **ALLOWLIST["targets"][3],
            "port": 33428,
            "database": "doki_e4",
            "database_username": "doki_e4_restore",
            "container_name": "doki-e4-20260903-mysql-restore",
            "container_id": "container-restore",
            "image_reference": "mysql:8.4",
            "network": "doki-e4-20260903-net",
            "image_id": "sha256:mysql-restore",
        },
    ],
}

TOPOLOGY_FACTS = {
    "container_name": "doki-e4-20260903-mysql",
    "container_id": "container-target",
    "image_reference": "mysql:8.4",
    "image_id": "sha256:mysql-target",
    "networks": ["doki-e4-20260903-net"],
    "host_ports": [33427],
    "running": True,
    "healthy": True,
}


def _record(now: datetime, *, purposes: list[str] | None = None) -> dict[str, object]:
    return build_e4_preflight_record(
        database_url=TARGET_URL,
        allowlist=ALLOWLIST,
        credential_ref="secret://e4/final",
        target_id="final",
        purpose=(purposes or ["inventory"])[0],
        purposes=purposes or ["inventory"],
        approval_token="approval-token",
        database_facts={"database": "e4_final", "server_uuid": "uuid-final"},
        issued_at=now,
        lifetime_seconds=120,
    )


def test_allowlist_accepts_multiple_read_only_sources_and_generic_3306_target() -> None:
    targets = parse_e4_allowlist(ALLOWLIST)
    assert [target.role for target in targets] == ["source", "source", "target", "restore"]
    assert all(target.read_only for target in targets[:2])
    assert parse_e4_target(TARGET_URL, ALLOWLIST, target_id="final", credential_ref="secret://e4/final").port == 3306


@pytest.mark.parametrize(
    ("changed", "message"),
    [
        ({"targets": [ALLOWLIST["targets"][0]]}, "final target"),
        (
            {
                "targets": [
                    ALLOWLIST["targets"][0],
                    ALLOWLIST["targets"][2],
                    {**ALLOWLIST["targets"][3], "server_uuid": "uuid-final"},
                ]
            },
            "independent MySQL server UUID",
        ),
        (
            {
                "targets": [
                    {**ALLOWLIST["targets"][0], "read_only": False},
                    ALLOWLIST["targets"][2],
                    ALLOWLIST["targets"][3],
                ]
            },
            "read_only",
        ),
        (
            {
                "targets": [
                    ALLOWLIST["targets"][0],
                    ALLOWLIST["targets"][1],
                    ALLOWLIST["targets"][2],
                    ALLOWLIST["targets"][3],
                    {**ALLOWLIST["targets"][3], "id": "restore-copy", "port": 3317},
                ]
            },
            "exactly one independent restore",
        ),
    ],
)
def test_allowlist_rejects_missing_or_ambiguous_roles(changed: dict[str, object], message: str) -> None:
    with pytest.raises(E4GuardError, match=message):
        parse_e4_allowlist(changed)


def test_allowlist_rejects_inline_secret_material_and_duplicate_endpoint() -> None:
    with pytest.raises(E4GuardError, match="credential_ref"):
        parse_e4_allowlist({"targets": [{**ALLOWLIST["targets"][0], "password": "do-not-copy"}]})

    duplicate = {
        "targets": [
            ALLOWLIST["targets"][0],
            ALLOWLIST["targets"][1],
            ALLOWLIST["targets"][2],
            ALLOWLIST["targets"][3],
            {**ALLOWLIST["targets"][1], "id": "duplicate-id", "role": "source"},
        ]
    }
    with pytest.raises(E4GuardError, match="endpoint"):
        parse_e4_allowlist(duplicate)


@pytest.mark.parametrize(
    ("changed", "message"),
    [
        (
            {
                "targets": [
                    {key: value for key, value in ALLOWLIST["targets"][0].items() if key != "database_username"},
                    *ALLOWLIST["targets"][2:],
                ]
            },
            "database_username",
        ),
        (
            {
                "targets": [
                    ALLOWLIST["targets"][0],
                    ALLOWLIST["targets"][2],
                    {**ALLOWLIST["targets"][3], "credential_ref": "secret://e4/final"},
                ]
            },
            "credential references",
        ),
    ],
)
def test_allowlist_requires_dedicated_credentials_and_independent_servers(
    changed: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(E4GuardError, match=message):
        parse_e4_allowlist(changed)


def test_allowlist_revalidates_dataclass_entries_and_canonicalizes_dns_case() -> None:
    malformed = E4Target(
        target_id="bad-source",
        role="source",
        host="127.0.0.1",
        port=3307,
        database="legacy_a",
        server_uuid="uuid-source-a",
        credential_ref="secret://e4/source-a",
        database_username="e4_source_a",
        read_only=False,
    )
    with pytest.raises(E4GuardError, match="read_only"):
        parse_e4_allowlist([malformed, *ALLOWLIST["targets"][2:]])

    duplicate_host_case = {
        "targets": [
            {**ALLOWLIST["targets"][0], "host": "LOCALHOST"},
            {**ALLOWLIST["targets"][1], "host": "localhost", "port": 3307, "database": "legacy_a"},
            ALLOWLIST["targets"][2],
            ALLOWLIST["targets"][3],
        ]
    }
    with pytest.raises(E4GuardError, match="endpoint"):
        parse_e4_allowlist(duplicate_host_case)


def test_allowlist_rejects_protected_e1_e2_e3_topology_reuse() -> None:
    for field, value in (
        ("container_name", "doki-e3-20260831-mysql"),
        ("network", "doki-e2-20260828-net"),
    ):
        changed = {
            **TOPOLOGY_ALLOWLIST,
            "targets": [
                TOPOLOGY_ALLOWLIST["targets"][0],
                {**TOPOLOGY_ALLOWLIST["targets"][1], field: value},
                TOPOLOGY_ALLOWLIST["targets"][2],
            ],
        }
        with pytest.raises(E4GuardError, match="protected E1/E2/E3"):
            parse_e4_allowlist(changed)


def test_allowlist_requires_immutable_image_identity_for_container_topology() -> None:
    changed = {
        **TOPOLOGY_ALLOWLIST,
        "targets": [
            TOPOLOGY_ALLOWLIST["targets"][0],
            {key: value for key, value in TOPOLOGY_ALLOWLIST["targets"][1].items() if key != "image_id"},
            TOPOLOGY_ALLOWLIST["targets"][2],
        ],
    }
    with pytest.raises(E4GuardError, match="topology requires.*image_id"):
        parse_e4_allowlist(changed)


def test_parse_target_requires_exact_allowlisted_endpoint_and_credential_reference() -> None:
    for url, kwargs in (
        ("mysql+aiomysql://e4_app:secret@127.0.0.1:3309/e4_final?charset=utf8mb4", {"target_id": "final"}),
        ("mysql+aiomysql://e4_app:secret@127.0.0.1:3306/other?charset=utf8mb4", {"target_id": "final"}),
        (TARGET_URL, {"target_id": "final", "credential_ref": "secret://wrong"}),
        ("mysql+pymysql://e4_app:secret@127.0.0.1:3306/e4_final?charset=utf8mb4", {"target_id": "final"}),
    ):
        with pytest.raises(E4GuardError, match="allowlist|credential|mysql\\+aiomysql"):
            parse_e4_target(url, ALLOWLIST, **kwargs)


def test_parse_target_rejects_privileged_users_and_query_drift() -> None:
    with pytest.raises(E4GuardError, match="dedicated application username"):
        parse_e4_target("mysql+aiomysql://root:secret@127.0.0.1:3306/e4_final?charset=utf8mb4", ALLOWLIST, target_id="final")
    with pytest.raises(E4GuardError, match="query must be exactly"):
        parse_e4_target(TARGET_URL + "&ssl=false", ALLOWLIST, target_id="final")
    with pytest.raises(E4GuardError, match="outside the explicit allowlist"):
        parse_e4_target(
            "mysql+aiomysql://different_app:secret@127.0.0.1:3306/e4_final?charset=utf8mb4",
            ALLOWLIST,
            target_id="final",
        )


def test_preflight_rejects_purposes_outside_target_role() -> None:
    now = datetime(2026, 9, 2, 2, 0, tzinfo=UTC)
    cases = (
        (
            "mysql+aiomysql://e4_source_a:secret@127.0.0.1:3307/legacy_a?charset=utf8mb4",
            "legacy-a",
            "migrate",
            "secret://e4/source-a",
            {"database": "legacy_a", "server_uuid": "uuid-source-a"},
        ),
        (TARGET_URL, "final", "restore-forward", "secret://e4/final", {"database": "e4_final", "server_uuid": "uuid-final"}),
        (
            "mysql+aiomysql://e4_restore:secret@127.0.0.1:3316/e4_restore?charset=utf8mb4",
            "restore",
            "switch",
            "secret://e4/restore",
            {"database": "e4_restore", "server_uuid": "uuid-restore"},
        ),
    )
    for database_url, target_id, purpose, credential_ref, database_facts in cases:
        with pytest.raises(E4GuardError, match="does not authorize purpose"):
            build_e4_preflight_record(
                database_url=database_url,
                allowlist=ALLOWLIST,
                credential_ref=credential_ref,
                target_id=target_id,
                purpose=purpose,
                database_facts=database_facts,
                issued_at=now,
                approval_token="approval-token",
                migration_switch=E4_MIGRATION_SWITCH,
            )


def test_non_container_source_backup_uses_general_resource_identity() -> None:
    now = datetime(2026, 9, 2, 2, 0, tzinfo=UTC)
    source_url = "mysql+aiomysql://e4_source_a:secret@127.0.0.1:3307/legacy_a?charset=utf8mb4"
    record = build_e4_preflight_record(
        database_url=source_url,
        allowlist=ALLOWLIST,
        credential_ref="secret://e4/source-a",
        target_id="legacy-a",
        purpose="backup",
        database_facts={"database": "legacy_a", "server_uuid": "uuid-source-a"},
        issued_at=now,
        approval_token="approval-token",
        migration_switch=E4_MIGRATION_SWITCH,
    )
    assert "container" not in record


def test_preflight_binds_identity_purpose_dsn_allowlist_and_no_plaintext_secret() -> None:
    now = datetime(2026, 9, 2, 2, 0, tzinfo=UTC)
    record = _record(now, purposes=["inventory", "dry-run"])
    encoded = json.dumps(record, sort_keys=True)

    assert record["dsn_sha256"] == database_url_fingerprint(TARGET_URL)
    assert record["allowlist_sha256"] == allowlist_fingerprint(ALLOWLIST)
    assert record["approval_token_sha256"] == approval_token_fingerprint("approval-token")
    assert "runtime-secret" not in encoded
    assert "approval-token" not in encoded
    assert record["target"] == e4_target_record(parse_e4_target(TARGET_URL, ALLOWLIST, target_id="final"))

    target = validate_preflight_record(
        record,
        database_url=TARGET_URL,
        allowlist=ALLOWLIST,
        credential_ref="secret://e4/final",
        target_id="final",
        approval_token="approval-token",
        purpose="dry-run",
        now=now + timedelta(seconds=30),
    )
    assert target.target_id == "final"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("dsn_sha256", "0" * 64, "URL fingerprint"),
        ("allowlist_sha256", "0" * 64, "allowlist fingerprint"),
        ("approval_token_sha256", "0" * 64, "approval token"),
        ("purpose", "restore", "purpose field"),
        ("target", {}, "target"),
        ("database", {"database": "e4_final", "server_uuid": "wrong"}, "database identity"),
    ],
)
def test_preflight_tampering_fails_closed(field: str, value: object, message: str) -> None:
    now = datetime(2026, 9, 2, 2, 0, tzinfo=UTC)
    record = _record(now, purposes=["inventory", "dry-run"])
    record[field] = value
    with pytest.raises(E4GuardError, match=message):
        validate_preflight_record(
            record,
            database_url=TARGET_URL,
            allowlist=ALLOWLIST,
            credential_ref="secret://e4/final",
            target_id="final",
            approval_token="approval-token",
            purpose="inventory",
            now=now + timedelta(seconds=30),
        )

    with pytest.raises(E4GuardError, match="not currently valid"):
        validate_preflight_record(
            _record(now),
            database_url=TARGET_URL,
            allowlist=ALLOWLIST,
            credential_ref="secret://e4/final",
            target_id="final",
            approval_token="approval-token",
            purpose="inventory",
            now=now + timedelta(minutes=3),
        )


def test_issue_requires_explicit_inspector_and_supports_async_inspector() -> None:
    called: list[str] = []

    async def inspector(target):
        called.append(target.target_id)
        return {"database": "e4_final", "server_uuid": "uuid-final"}

    record = asyncio.run(
        issue_e4_preflight_record(
            database_url=TARGET_URL,
            allowlist=ALLOWLIST,
            credential_ref="secret://e4/final",
            target_id="final",
            purpose="inventory",
            issuance_switch=E4_PREFLIGHT_ISSUANCE_SWITCH,
            database_inspector=inspector,
            approval_token="approval-token",
            lifetime_seconds=60,
        )
    )
    assert called == ["final"]
    assert record["database"] == {"database": "e4_final", "server_uuid": "uuid-final"}

    with pytest.raises(E4GuardError, match="explicit database inspector"):
        asyncio.run(
            issue_e4_preflight_record(
                database_url=TARGET_URL,
                allowlist=ALLOWLIST,
                credential_ref="secret://e4/final",
                target_id="final",
                purpose="inventory",
                issuance_switch=E4_PREFLIGHT_ISSUANCE_SWITCH,
            )
        )


def test_load_guard_uses_explicit_config_path_and_does_not_need_environment(tmp_path) -> None:
    now = datetime(2026, 9, 2, 2, 0, tzinfo=UTC)
    record = _record(now)
    preflight_path = tmp_path / "e4-preflight.json"
    preflight_path.write_text(json.dumps(record), encoding="utf-8")

    guard = load_guard_from_config(
        "inventory",
        database_url=TARGET_URL,
        allowlist=ALLOWLIST,
        credential_ref="secret://e4/final",
        target_id="final",
        preflight=preflight_path,
        approval_token="approval-token",
        now=now + timedelta(seconds=1),
    )
    assert guard.database_url == TARGET_URL
    assert guard.target.target_id == "final"
    assert len(guard.allowlist) == 4


def test_migration_preflight_requires_switch_token_and_complete_topology() -> None:
    now = datetime(2026, 9, 2, 2, 0, tzinfo=UTC)
    common = {
        "database_url": TOPOLOGY_TARGET_URL,
        "allowlist": TOPOLOGY_ALLOWLIST,
        "credential_ref": "secret://e4/final",
        "target_id": "final",
        "purpose": "migrate",
        "database_facts": {"database": "doki_e4", "server_uuid": "uuid-final"},
        "container_facts": TOPOLOGY_FACTS,
        "issued_at": now,
        "approval_token": "approval-token",
    }
    with pytest.raises(E4GuardError, match="migration switch"):
        build_e4_preflight_record(**common)

    record = build_e4_preflight_record(**common, migration_switch=E4_MIGRATION_SWITCH)
    assert record["migration_switch_sha256"]
    assert record["container"]["container_id"] == "container-target"
    assert record["container"]["networks"] == ["doki-e4-20260903-net"]
    assert record["container"]["running"] is True
    assert record["container"]["healthy"] is True
    validate_preflight_record(
        record,
        database_url=TOPOLOGY_TARGET_URL,
        allowlist=TOPOLOGY_ALLOWLIST,
        credential_ref="secret://e4/final",
        target_id="final",
        purpose="migrate",
        approval_token="approval-token",
        migration_switch=E4_MIGRATION_SWITCH,
        container_facts=TOPOLOGY_FACTS,
        now=now + timedelta(seconds=30),
    )

    with pytest.raises(E4GuardError, match="database name is missing"):
        build_e4_preflight_record(
            **{**common, "database_facts": {"server_uuid": "uuid-final"}},
            migration_switch=E4_MIGRATION_SWITCH,
        )


def test_issue_migration_preflight_requires_explicit_container_inspector() -> None:
    database_inspections = 0
    container_inspections = 0

    async def database_inspector(_target):
        nonlocal database_inspections
        database_inspections += 1
        return {"database": "doki_e4", "server_uuid": "uuid-final", "container": TOPOLOGY_FACTS}

    async def container_inspector(_target):
        nonlocal container_inspections
        container_inspections += 1
        return TOPOLOGY_FACTS

    for extra, message in (({}, "approval token"), ({"approval_token": "approval-token", "lifetime_seconds": 0}, "lifetime")):
        with pytest.raises(E4GuardError, match=message):
            asyncio.run(
                issue_e4_preflight_record(
                    database_url=TOPOLOGY_TARGET_URL,
                    allowlist=TOPOLOGY_ALLOWLIST,
                    credential_ref="secret://e4/final",
                    target_id="final",
                    purpose="migrate",
                    issuance_switch=E4_PREFLIGHT_ISSUANCE_SWITCH,
                    database_inspector=database_inspector,
                    container_inspector=container_inspector,
                    migration_switch=E4_MIGRATION_SWITCH,
                    **extra,
                )
            )
    assert database_inspections == 0
    assert container_inspections == 0

    with pytest.raises(E4GuardError, match="container inspector"):
        asyncio.run(
            issue_e4_preflight_record(
                database_url=TOPOLOGY_TARGET_URL,
                allowlist=TOPOLOGY_ALLOWLIST,
                credential_ref="secret://e4/final",
                target_id="final",
                purpose="migrate",
                issuance_switch=E4_PREFLIGHT_ISSUANCE_SWITCH,
                database_inspector=database_inspector,
                approval_token="approval-token",
                migration_switch=E4_MIGRATION_SWITCH,
            )
        )
    assert database_inspections == 0

    async def drifted_container_inspector(_target):
        return {**TOPOLOGY_FACTS, "container_id": "unexpected-container"}

    with pytest.raises(E4GuardError, match="container identity"):
        asyncio.run(
            issue_e4_preflight_record(
                database_url=TOPOLOGY_TARGET_URL,
                allowlist=TOPOLOGY_ALLOWLIST,
                credential_ref="secret://e4/final",
                target_id="final",
                purpose="migrate",
                issuance_switch=E4_PREFLIGHT_ISSUANCE_SWITCH,
                database_inspector=database_inspector,
                container_inspector=drifted_container_inspector,
                approval_token="approval-token",
                migration_switch=E4_MIGRATION_SWITCH,
            )
        )
    assert database_inspections == 0

    record = asyncio.run(
        issue_e4_preflight_record(
            database_url=TOPOLOGY_TARGET_URL,
            allowlist=TOPOLOGY_ALLOWLIST,
            credential_ref="secret://e4/final",
            target_id="final",
            purpose="migrate",
            issuance_switch=E4_PREFLIGHT_ISSUANCE_SWITCH,
            database_inspector=database_inspector,
            container_inspector=container_inspector,
            approval_token="approval-token",
            migration_switch=E4_MIGRATION_SWITCH,
        )
    )
    assert database_inspections == 1
    assert container_inspections == 1
    assert record["container"]["networks"] == ["doki-e4-20260903-net"]


def test_load_container_guard_requires_fresh_inspection_after_static_validation() -> None:
    now = datetime(2026, 9, 2, 2, 0, tzinfo=UTC)
    record = build_e4_preflight_record(
        database_url=TOPOLOGY_TARGET_URL,
        allowlist=TOPOLOGY_ALLOWLIST,
        credential_ref="secret://e4/final",
        target_id="final",
        purpose="migrate",
        database_facts={"database": "doki_e4", "server_uuid": "uuid-final"},
        container_facts=TOPOLOGY_FACTS,
        issued_at=now,
        approval_token="approval-token",
        migration_switch=E4_MIGRATION_SWITCH,
    )
    unhealthy = {**TOPOLOGY_FACTS, "healthy": False}
    container_inspections = 0

    def unhealthy_inspector(_target):
        nonlocal container_inspections
        container_inspections += 1
        return unhealthy

    with pytest.raises(E4GuardError, match="not currently valid"):
        load_guard_from_config(
            "migrate",
            database_url=TOPOLOGY_TARGET_URL,
            allowlist=TOPOLOGY_ALLOWLIST,
            credential_ref="secret://e4/final",
            target_id="final",
            preflight=record,
            approval_token="approval-token",
            migration_switch=E4_MIGRATION_SWITCH,
            container_inspector=unhealthy_inspector,
            now=now + timedelta(minutes=16),
        )
    assert container_inspections == 0

    tampered_record = {**record, "container": {**record["container"], "container_id": "tampered-container"}}
    with pytest.raises(E4GuardError, match="container identity"):
        load_guard_from_config(
            "migrate",
            database_url=TOPOLOGY_TARGET_URL,
            allowlist=TOPOLOGY_ALLOWLIST,
            credential_ref="secret://e4/final",
            target_id="final",
            preflight=tampered_record,
            approval_token="approval-token",
            migration_switch=E4_MIGRATION_SWITCH,
            container_inspector=unhealthy_inspector,
            now=now + timedelta(seconds=1),
        )
    assert container_inspections == 0

    with pytest.raises(E4GuardError, match="explicit container inspector"):
        load_guard_from_config(
            "migrate",
            database_url=TOPOLOGY_TARGET_URL,
            allowlist=TOPOLOGY_ALLOWLIST,
            credential_ref="secret://e4/final",
            target_id="final",
            preflight=record,
            approval_token="approval-token",
            migration_switch=E4_MIGRATION_SWITCH,
            now=now + timedelta(seconds=1),
        )

    with pytest.raises(TypeError, match="container_facts"):
        load_guard_from_config(
            "migrate",
            database_url=TOPOLOGY_TARGET_URL,
            allowlist=TOPOLOGY_ALLOWLIST,
            credential_ref="secret://e4/final",
            target_id="final",
            preflight=record,
            approval_token="approval-token",
            migration_switch=E4_MIGRATION_SWITCH,
            now=now + timedelta(seconds=1),
            **{"container_facts": TOPOLOGY_FACTS},
        )

    with pytest.raises(E4GuardError, match="running and healthy"):
        load_guard_from_config(
            "migrate",
            database_url=TOPOLOGY_TARGET_URL,
            allowlist=TOPOLOGY_ALLOWLIST,
            credential_ref="secret://e4/final",
            target_id="final",
            preflight=record,
            approval_token="approval-token",
            migration_switch=E4_MIGRATION_SWITCH,
            container_inspector=unhealthy_inspector,
            now=now + timedelta(seconds=1),
        )
    assert container_inspections == 1

    guard = load_guard_from_config(
        "migrate",
        database_url=TOPOLOGY_TARGET_URL,
        allowlist=TOPOLOGY_ALLOWLIST,
        credential_ref="secret://e4/final",
        target_id="final",
        preflight=record,
        approval_token="approval-token",
        migration_switch=E4_MIGRATION_SWITCH,
        container_inspector=lambda _target: TOPOLOGY_FACTS,
        now=now + timedelta(seconds=1),
    )
    assert guard.target.target_id == "final"
