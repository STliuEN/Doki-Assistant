from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.db.e4_guard import (
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
        },
        {
            "id": "restore",
            "role": "restore",
            "host": "127.0.0.1",
            "port": 3316,
            "database": "e4_restore",
            "server_uuid": "uuid-restore",
            "credential_ref": "secret://e4/restore",
        },
    ],
}

TARGET_URL = "mysql+aiomysql://e4_app:runtime-secret@127.0.0.1:3306/e4_final?charset=utf8mb4"


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


def test_allowlist_revalidates_dataclass_entries_and_canonicalizes_dns_case() -> None:
    malformed = E4Target(
        target_id="bad-source",
        role="source",
        host="127.0.0.1",
        port=3307,
        database="legacy_a",
        server_uuid="uuid-source-a",
        credential_ref="secret://e4/source-a",
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


def test_parse_target_requires_exact_allowlisted_endpoint_and_credential_reference() -> None:
    for url, kwargs in (
        ("mysql+aiomysql://e4_app:secret@127.0.0.1:3309/e4_final?charset=utf8mb4", {"target_id": "final"}),
        ("mysql+aiomysql://e4_app:secret@127.0.0.1:3306/other?charset=utf8mb4", {"target_id": "final"}),
        (TARGET_URL, {"target_id": "final", "credential_ref": "secret://wrong"}),
        ("mysql+pymysql://e4_app:secret@127.0.0.1:3306/e4_final?charset=utf8mb4", {"target_id": "final"}),
    ):
        with pytest.raises(E4GuardError, match="allowlist|credential|mysql\\+aiomysql"):
            parse_e4_target(url, ALLOWLIST, **kwargs)


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
