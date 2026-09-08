from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.e4.identity import (
    IdentityDryRunError,
    SourceKey,
    build_identity_dry_run,
    deterministic_target_uuid,
    identity_report_to_dict,
    write_identity_report,
)

SNAPSHOT_DIGEST = "a" * 64
USER_DIGEST = "b" * 64
SESSION_DIGEST = "c" * 64
MESSAGE_DIGEST = "d" * 64
CORRELATION_ID = "aaaaaaaa-1111-4111-8111-111111111111"


def _key(source_system: str, entity_type: str, source_id: str | int) -> dict[str, object]:
    return {"source_system": source_system, "entity_type": entity_type, "source_id": source_id}


def _document(*entities: dict[str, object], **extra: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "migration_batch_id": "e4-batch-001",
        "snapshot_manifest_digest": SNAPSHOT_DIGEST,
        "schema_revision": "20260901_0007_e3_auth",
        "correlation_id": CORRELATION_ID,
        "entities": list(entities),
        **extra,
    }


def _user() -> dict[str, object]:
    return {
        **_key("django", "user", "legacy-user-1"),
        "entity_content_digest": USER_DIGEST,
        "scope": "global",
    }


def _session() -> dict[str, object]:
    return {
        **_key("fastapi_legacy", "session", "0001"),
        "entity_content_digest": SESSION_DIGEST,
        "scope": "user",
        "owner": _key("django", "user", "legacy-user-1"),
    }


def _message() -> dict[str, object]:
    return {
        **_key("fastapi_legacy", "message", 2),
        "entity_content_digest": MESSAGE_DIGEST,
        "scope": "user",
        "owner": _key("django", "user", "legacy-user-1"),
        "foreign_keys": [{**_key("fastapi_legacy", "session", "1")}],
    }


def test_clean_dry_run_is_deterministic_sorted_and_uses_frozen_uuidv5() -> None:
    document = _document(_message(), _user(), _session())

    first = build_identity_dry_run(document)
    second = build_identity_dry_run(deepcopy(document))

    assert first == second
    assert first.blocked is False
    assert first.counts == {
        "source_key_total": 3,
        "normalized_count": 3,
        "invalid_count": 0,
        "duplicate_count": 0,
        "validated_count": 3,
        "already_mapped_count": 0,
        "conflict_count": 0,
        "orphan_count": 0,
        "target_uuid_collision_count": 0,
        "unique_conflict_count": 0,
        "expected_inserts": 3,
        "expected_noops": 0,
    }
    assert [decision.key.source_id for decision in first.decisions] == ["legacy-user-1", "2", "1"]
    assert all(decision.status == "validated" for decision in first.decisions)
    user = first.decisions[0]
    assert user.target_uuid == deterministic_target_uuid(_key("django", "user", "legacy-user-1"))
    rendered = json.dumps(identity_report_to_dict(first), sort_keys=True)
    assert "legacy-user-1" not in rendered
    assert "source_key_token" in rendered


def test_replay_with_same_mapping_is_a_noop_and_different_digest_blocks() -> None:
    user_key = _key("django", "user", "legacy-user-1")
    document = _document(
        _user(),
        existing_mappings=[
            {
                **user_key,
                "target_uuid": deterministic_target_uuid(user_key),
                "source_digest": USER_DIGEST,
                "status": "mapped",
            }
        ],
    )
    replay = build_identity_dry_run(document)
    assert replay.blocked is False
    assert replay.decisions[0].status == "mapped"
    assert replay.decisions[0].action == "already_mapped"
    assert replay.counts["expected_noops"] == 1

    changed = deepcopy(document)
    changed["entities"] = [{**_user(), "entity_content_digest": "e" * 64}]
    conflict = build_identity_dry_run(changed)
    assert conflict.blocked is True
    assert conflict.decisions[0].status == "conflict"
    assert "source_digest_conflict" in conflict.decisions[0].issue_codes


def test_duplicate_source_keys_are_retained_and_counted_as_conflicts() -> None:
    report = build_identity_dry_run(_document(_user(), _user()))

    assert report.blocked is True
    assert len(report.decisions) == 2
    assert all(decision.status == "conflict" for decision in report.decisions)
    assert report.counts["duplicate_count"] == 2
    assert report.counts["conflict_count"] == 2


def test_missing_owner_and_fk_propagate_orphan_status() -> None:
    missing_owner = {
        **_key("fastapi_legacy", "session", "1"),
        "entity_content_digest": SESSION_DIGEST,
        "scope": "user",
        "owner": _key("django", "user", "does-not-exist"),
    }
    dependent = {
        **_key("fastapi_legacy", "message", "2"),
        "entity_content_digest": MESSAGE_DIGEST,
        "scope": "user",
        "owner": _key("django", "user", "does-not-exist"),
        "foreign_keys": [{**_key("fastapi_legacy", "session", "1")}],
    }
    report = build_identity_dry_run(_document(dependent, missing_owner))

    assert report.blocked is True
    assert report.counts["orphan_count"] == 2
    assert all("missing_reference" in decision.issue_codes for decision in report.decisions)


def test_target_and_unique_collisions_fail_closed() -> None:
    first_key = _key("fastapi_legacy", "note", "1")
    collided_target = deterministic_target_uuid(first_key)
    first = {
        **first_key,
        "entity_content_digest": "1" * 64,
        "scope": "global",
        "unique_key": "canonical-note-key",
    }
    second = {
        **_key("fastapi_legacy", "note", collided_target),
        "entity_content_digest": "2" * 64,
        "scope": "global",
        "unique_key": "canonical-note-key",
    }
    report = build_identity_dry_run(_document(first, second))

    assert report.blocked is True
    assert report.counts["target_uuid_collision_count"] == 2
    assert report.counts["unique_conflict_count"] == 2
    assert all({"target_uuid_collision", "unique_key_conflict"} <= set(decision.issue_codes) for decision in report.decisions)


def test_existing_target_without_mapping_is_not_silently_reused() -> None:
    user = _user()
    target_uuid = deterministic_target_uuid(_key("django", "user", "legacy-user-1"))
    report = build_identity_dry_run(
        _document(
            user,
            existing_targets=[{"target_uuid": target_uuid}],
        )
    )

    assert report.blocked is True
    assert "target_exists_without_mapping" in report.decisions[0].issue_codes


def test_secret_material_and_invalid_snapshot_values_are_rejected() -> None:
    with pytest.raises(IdentityDryRunError, match="inline secret"):
        build_identity_dry_run({**_document(_user()), "password": "must-not-appear"})
    with pytest.raises(IdentityDryRunError, match="lowercase UUID"):
        build_identity_dry_run({**_document(_user()), "correlation_id": CORRELATION_ID.upper()})
    with pytest.raises(IdentityDryRunError, match="E3 UUIDv5"):
        build_identity_dry_run({**_document({**_user(), "target_uuid": "22222222-2222-4222-8222-222222222222"})})


def test_report_writer_is_new_file_only_and_keeps_redaction(tmp_path: Path) -> None:
    report = build_identity_dry_run(_document(_user()))
    output = tmp_path / "identity-report.json"
    assert write_identity_report(report, output) == output
    assert "legacy-user-1" not in output.read_text(encoding="utf-8")
    with pytest.raises(IdentityDryRunError, match="already exists"):
        write_identity_report(report, output)


def test_standard_uuid_source_is_canonicalized_and_retained_as_target() -> None:
    source_uuid = "ABCDEFAB-CDEF-4ABC-8DEF-ABCDEFABCDEF"
    entity = {
        **_key("filesystem", "image", source_uuid),
        "entity_content_digest": "f" * 64,
        "artifact_digest": "e" * 64,
        "scope": "global",
    }
    report = build_identity_dry_run(_document(entity))

    decision = report.decisions[0]
    assert decision.key.source_id == source_uuid.lower()
    assert decision.target_uuid == source_uuid.lower()
    assert decision.artifact_digest == "e" * 64
    rendered = identity_report_to_dict(report)
    assert rendered["decisions"][0]["artifact_digest"] == "e" * 64
    unsigned = identity_report_to_dict(report, include_digest=False)
    canonical = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == report.report_sha256


def test_source_key_dataclass_is_revalidated_and_canonicalized() -> None:
    source_uuid = "ABCDEFAB-CDEF-4ABC-8DEF-ABCDEFABCDEF"
    assert deterministic_target_uuid(SourceKey("FILESYSTEM", "IMAGE", source_uuid)) == source_uuid.lower()
    with pytest.raises(IdentityDryRunError, match="source_system is unsupported"):
        deterministic_target_uuid(SourceKey("unknown", "image", "one"))


def test_django_uuid_like_shortuuid_preserves_case_and_uses_e3_uuid5() -> None:
    source_id = "ABCDEFAB-CDEF-4ABC-8DEF-ABCDEFABCDEF"
    entity = {
        **_key("django", "user", source_id),
        "entity_content_digest": USER_DIGEST,
        "scope": "global",
    }
    report = build_identity_dry_run(_document(entity))

    decision = report.decisions[0]
    assert decision.key.source_id == source_id
    assert decision.target_uuid == deterministic_target_uuid(entity)
    assert decision.target_uuid != source_id.lower()


def test_existing_mappings_cannot_reuse_one_target_uuid_for_different_sources() -> None:
    first = _key("filesystem", "image", "first")
    target_uuid = deterministic_target_uuid(first)
    second = _key("filesystem", "image", target_uuid)
    with pytest.raises(IdentityDryRunError, match="reuses one target UUID"):
        build_identity_dry_run(
            _document(
                {
                    **first,
                    "entity_content_digest": "1" * 64,
                    "scope": "global",
                },
                existing_mappings=[
                    {
                        **first,
                        "target_uuid": target_uuid,
                        "source_digest": "1" * 64,
                        "status": "mapped",
                    },
                    {
                        **second,
                        "target_uuid": target_uuid,
                        "source_digest": "2" * 64,
                        "status": "mapped",
                    },
                ],
            )
        )


def test_existing_mapping_rejects_non_deterministic_target_uuid() -> None:
    key = _key("filesystem", "image", "first")
    with pytest.raises(IdentityDryRunError, match="existing mapping.*deterministic"):
        build_identity_dry_run(
            _document(
                {
                    **key,
                    "entity_content_digest": "1" * 64,
                    "scope": "global",
                },
                existing_mappings=[
                    {
                        **key,
                        "target_uuid": "22222222-2222-4222-8222-222222222222",
                        "source_digest": "1" * 64,
                        "status": "mapped",
                    }
                ],
            )
        )


def test_legacy_source_rejects_non_deterministic_explicit_target_uuid() -> None:
    entity = {
        **_key("fastapi_legacy", "note", "1"),
        "entity_content_digest": "1" * 64,
        "scope": "global",
        "target_uuid": "22222222-2222-4222-8222-222222222222",
    }
    with pytest.raises(IdentityDryRunError, match="deterministic E4 UUIDv5 rule"):
        build_identity_dry_run(_document(entity))
