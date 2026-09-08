from __future__ import annotations

import base64
import hashlib
import json

import pytest

from scripts import e4_import


def test_cli_returns_nonzero_when_importer_reports_blocked(monkeypatch, capsys, tmp_path):
    async def fake_run(_args):
        return {"dry_run": False, "migration_batch_id": "e4-cli-001", "blocked": True}

    monkeypatch.setattr(e4_import, "_run", fake_run)
    code = e4_import.main(
        [
            "--source",
            str(tmp_path / "bundle.json"),
            "--expected-manifest-sha256",
            "a" * 64,
        ]
    )

    assert code == 2
    assert json.loads(capsys.readouterr().out)["blocked"] is True


def test_cli_returns_zero_for_a_completed_import(monkeypatch, capsys, tmp_path):
    async def fake_run(_args):
        return {"dry_run": False, "migration_batch_id": "e4-cli-002", "blocked": False}

    monkeypatch.setattr(e4_import, "_run", fake_run)
    code = e4_import.main(
        [
            "--source",
            str(tmp_path / "bundle.json"),
            "--expected-manifest-sha256",
            "a" * 64,
        ]
    )

    assert code == 0
    assert json.loads(capsys.readouterr().out)["blocked"] is False


@pytest.fixture
def offline_bundle(tmp_path, monkeypatch):
    def no_database(*args, **kwargs):
        pytest.fail("offline payload validation must not inspect or connect to a database")

    monkeypatch.setattr(e4_import, "load_guard_from_environment", no_database)
    monkeypatch.setattr(e4_import, "create_async_engine", no_database)
    return {
        "schema_version": 1,
        "migration_batch_id": "e4-payload-test",
        "snapshot_manifest_digest": "a" * 64,
        "schema_revision": "20260905_0008_e4_business_shadow",
        "correlation_id": "aaaaaaaa-1111-4111-8111-111111111111",
        "entities": [{
            "source_system": "fastapi_legacy",
            "entity_type": "note",
            "source_id": "private-source-id",
            "entity_content_digest": "b" * 64,
            "scope": "global",
            "data": {"user_id": "legacy-user", "title": "private-title", "content": "private-body"},
        }],
    }


@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("failure", ["unsupported", "missing_payload", "missing_column", "unknown_column", "key_version"])
def test_cli_blocks_invalid_payload_before_database_access(failure, live, offline_bundle, tmp_path, capsys):
    entity = offline_bundle["entities"][0]
    if failure == "unsupported":
        entity.update(source_system="skill_legacy", entity_type="unsupported_fixture_entity")
    elif failure == "missing_payload":
        entity.pop("data")
    elif failure == "missing_column":
        entity["data"].pop("title")
    elif failure == "unknown_column":
        entity["data"]["private-column-name"] = "private-value"
    else:
        entity["entity_type"] = "model_config"
        entity["data"] = {"user_id": "legacy-user", "model_type": "ollama", "api_key_encrypted": "private-ciphertext"}
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(offline_bundle), encoding="utf-8")
    arguments = ["--source", str(path), "--expected-manifest-sha256", "a" * 64, "--preflight" if live else "--dry-run"]
    assert e4_import.main(arguments) == 2
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["blocked"] is True
    assert result["business_validation"]["blocked"] is True
    assert "private-" not in output.out + output.err


def test_cli_valid_payload_dry_run_is_offline(offline_bundle, tmp_path, capsys):
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(offline_bundle), encoding="utf-8")
    assert e4_import.main(["--source", str(path), "--expected-manifest-sha256", "a" * 64, "--dry-run"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["blocked"] is False
    assert result["business_validation"]["issues"] == []


@pytest.mark.parametrize("failure", [None, "base64", "sha256", "md5", "filename", "status", "owner"])
def test_cli_validates_media_without_database_access(failure, offline_bundle, tmp_path, capsys):
    blob = b"private-media-bytes"
    media = {
        "source_system": "filesystem", "source_id": "private-media-id", "scope": "global",
        "content_digest": "c" * 64, "artifact_digest": hashlib.sha256(blob).hexdigest(),
        "legacy_md5": hashlib.md5(blob).hexdigest(), "filename": "private-image.png", "mime_type": "image/png",
        "content_blob_base64": base64.b64encode(blob).decode("ascii"),
    }
    if failure == "base64":
        media["content_blob_base64"] = "!invalid!"
    elif failure == "sha256":
        media["artifact_digest"] = "d" * 64
    elif failure == "md5":
        media["legacy_md5"] = "d" * 32
    elif failure == "filename":
        media.pop("filename")
    elif failure == "status":
        media["status"] = "private-invalid-status"
    elif failure == "owner":
        media["scope"] = "user"
    offline_bundle.update(entities=[], media=[media])
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(offline_bundle), encoding="utf-8")
    code = e4_import.main(["--source", str(path), "--expected-manifest-sha256", "a" * 64, "--dry-run"])
    assert code == (0 if failure is None else 2)
    output = capsys.readouterr()
    assert "private-" not in output.out + output.err
    assert json.loads(output.out)["business_validation"]["checked_media"] == 1


@pytest.mark.parametrize("failure", [None, "missing_blob", "size", "md5"])
def test_cli_validates_document_bytes(failure, offline_bundle, tmp_path, capsys):
    blob = b"private-document-bytes"
    entity = offline_bundle["entities"][0]
    entity.update(entity_type="knowledge_document", artifact_digest=hashlib.sha256(blob).hexdigest())
    entity["data"] = {
        "user_id": "legacy-user", "filename": "private-file.pdf", "original_filename": "private-file.pdf", "file_ext": "pdf",
        "file_size": len(blob), "md5": hashlib.md5(blob).hexdigest(),
        "content_blob_base64": base64.b64encode(blob).decode("ascii"),
    }
    if failure == "missing_blob":
        entity["data"].pop("content_blob_base64")
    elif failure == "size":
        entity["data"]["file_size"] += 1
    elif failure == "md5":
        entity["data"]["md5"] = "e" * 32
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(offline_bundle), encoding="utf-8")
    code = e4_import.main(["--source", str(path), "--expected-manifest-sha256", "a" * 64, "--dry-run"])
    assert code == (0 if failure is None else 2)
    output = capsys.readouterr()
    assert "private-" not in output.out + output.err


def test_live_payload_check_leaves_missing_target_owner_facts_to_guarded_importer(offline_bundle, monkeypatch, tmp_path, capsys):
    events = []

    def guard_reached(*args, **kwargs):
        events.append("guard")
        raise e4_import.E4GuardError("fixture guard reached without connecting")

    monkeypatch.setattr(e4_import, "load_guard_from_environment", guard_reached)
    entity = offline_bundle["entities"][0]
    entity.update(scope="user", owner={"source_system": "django", "entity_type": "user", "source_id": "legacy-user"})
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(offline_bundle), encoding="utf-8")
    assert e4_import.main(["--source", str(path), "--expected-manifest-sha256", "a" * 64, "--preflight"]) == 2
    assert events == ["guard"]
    assert json.loads(capsys.readouterr().out)["error"] == "E4GuardError"
