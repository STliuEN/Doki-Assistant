from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.backup_restore import (
    BackupRestoreError,
    create_backup,
    rebuild_projection,
    restore_backup,
    verify_backup,
    verify_restored,
)


@pytest.mark.parametrize("artifact_kind", ["storage-tree", "chroma-projection"])
def test_directory_backup_restore_and_verify_round_trip(tmp_path: Path, artifact_kind: str) -> None:
    source = tmp_path / "source"
    (source / "nested" / "empty").mkdir(parents=True)
    (source / "metadata.json").write_text('{"revision": 7}\n', encoding="utf-8")
    (source / "nested" / "segment.bin").write_bytes(b"\x00projection-or-storage\xff")
    bundle = tmp_path / "bundle"
    restored = tmp_path / "restored"

    manifest = create_backup(artifact_kind=artifact_kind, source=source, output=bundle)
    restore_backup(bundle=bundle, target=restored)

    assert manifest["artifact_kind"] == artifact_kind
    assert len(manifest["content_sha256"]) == 64
    assert (restored / "nested" / "empty").is_dir()
    assert (restored / "nested" / "segment.bin").read_bytes() == b"\x00projection-or-storage\xff"
    assert verify_backup(bundle) == manifest
    assert verify_restored(bundle, restored) == manifest


def test_repeated_backups_have_the_same_content_digest(tmp_path: Path) -> None:
    source = tmp_path / "storage"
    source.mkdir()
    (source / "object.bin").write_bytes(b"immutable")

    first = create_backup(artifact_kind="storage-tree", source=source, output=tmp_path / "first")
    second = create_backup(artifact_kind="storage-tree", source=source, output=tmp_path / "second")

    assert first["content_sha256"] == second["content_sha256"]


def test_mysql_backup_accepts_only_an_offline_file_and_restores_one_file(tmp_path: Path) -> None:
    fixture = tmp_path / "isolated-fixture.sql"
    fixture.write_text("CREATE TABLE fixture (id INT);\nINSERT INTO fixture VALUES (1);\n", encoding="utf-8")
    bundle = tmp_path / "mysql-bundle"
    restored = tmp_path / "restored.sql"

    manifest = create_backup(artifact_kind="mysql-dump", source=fixture, output=bundle)
    restore_backup(bundle=bundle, target=restored)

    assert manifest["source_format"] == "offline-sql-file"
    assert restored.read_bytes() == fixture.read_bytes()
    verify_restored(bundle, restored)

    with pytest.raises(BackupRestoreError, match="offline dump file"):
        create_backup(artifact_kind="mysql-dump", source=tmp_path, output=tmp_path / "invalid")


def test_verify_rejects_payload_tampering_and_restore_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "storage"
    source.mkdir()
    (source / "object.bin").write_bytes(b"healthy")
    bundle = tmp_path / "bundle"
    create_backup(artifact_kind="storage-tree", source=source, output=bundle)
    (bundle / "payload" / "object.bin").write_bytes(b"tampered")

    with pytest.raises(BackupRestoreError, match="does not match manifest"):
        verify_backup(bundle)
    with pytest.raises(BackupRestoreError, match="does not match manifest"):
        restore_backup(bundle=bundle, target=tmp_path / "must-not-exist")
    assert not (tmp_path / "must-not-exist").exists()


def test_projection_rebuild_validates_manifest_and_quarantines_previous_generation(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "chroma.sqlite3").write_bytes(b"new generation")
    bundle = tmp_path / "bundle"
    create_backup(artifact_kind="chroma-projection", source=source, output=bundle)

    target = tmp_path / "active-projection"
    target.mkdir()
    (target / "chroma.sqlite3").write_bytes(b"old generation")
    quarantine = tmp_path / "quarantine"

    result = rebuild_projection(bundle=bundle, target=target, quarantine_root=quarantine)

    assert (target / "chroma.sqlite3").read_bytes() == b"new generation"
    previous = Path(result["quarantined_previous"])
    assert previous.is_dir()
    assert (previous / "chroma.sqlite3").read_bytes() == b"old generation"
    assert result["content_sha256"] == verify_backup(bundle)["content_sha256"]


def test_projection_rebuild_rejects_non_projection_bundle_without_mutating_target(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "dump.sql").write_bytes(b"SELECT 1;\n")
    bundle = tmp_path / "bundle"
    create_backup(artifact_kind="storage-tree", source=source, output=bundle)
    target = tmp_path / "active"
    target.mkdir()
    (target / "marker").write_bytes(b"keep")

    with pytest.raises(BackupRestoreError, match="chroma-projection"):
        rebuild_projection(bundle=bundle, target=target)
    assert (target / "marker").read_bytes() == b"keep"


def test_projection_rebuild_rejects_tampered_bundle_before_swapping_target(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "chroma.sqlite3").write_bytes(b"candidate")
    bundle = tmp_path / "bundle"
    create_backup(artifact_kind="chroma-projection", source=source, output=bundle)
    (bundle / "payload" / "chroma.sqlite3").write_bytes(b"tampered")

    target = tmp_path / "target"
    target.mkdir()
    (target / "marker").write_bytes(b"keep")
    with pytest.raises(BackupRestoreError, match="does not match manifest"):
        rebuild_projection(bundle=bundle, target=target)
    assert (target / "marker").read_bytes() == b"keep"


def test_manifest_path_traversal_and_unexpected_payload_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "projection"
    source.mkdir()
    (source / "index.bin").write_bytes(b"index")
    bundle = tmp_path / "bundle"
    create_backup(artifact_kind="chroma-projection", source=source, output=bundle)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["entries"][0]["path"] = "../outside"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(BackupRestoreError, match="unsafe manifest entry path"):
        verify_backup(bundle)

    second_bundle = tmp_path / "second-bundle"
    create_backup(artifact_kind="chroma-projection", source=source, output=second_bundle)
    (second_bundle / "payload" / "unexpected.bin").write_bytes(b"unexpected")
    with pytest.raises(BackupRestoreError, match="does not match manifest"):
        verify_backup(second_bundle)


@pytest.mark.parametrize("unsafe_path", ["C:/outside", "C:\\outside", "\\outside", "\\\\server\\share"])
def test_manifest_windows_absolute_paths_are_rejected(tmp_path: Path, unsafe_path: str) -> None:
    source = tmp_path / "projection"
    source.mkdir()
    (source / "index.bin").write_bytes(b"index")
    bundle = tmp_path / "bundle"
    create_backup(artifact_kind="chroma-projection", source=source, output=bundle)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["entries"][0]["path"] = unsafe_path
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(BackupRestoreError, match="unsafe manifest entry path"):
        verify_backup(bundle)


def test_symlinks_and_existing_outputs_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "storage"
    source.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    link = source / "linked.bin"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")

    with pytest.raises(BackupRestoreError, match="symbolic link"):
        create_backup(artifact_kind="storage-tree", source=source, output=tmp_path / "bundle")

    link.unlink()
    (source / "safe.bin").write_bytes(b"safe")
    bundle = tmp_path / "bundle"
    create_backup(artifact_kind="storage-tree", source=source, output=bundle)
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(BackupRestoreError, match="already exists"):
        restore_backup(bundle=bundle, target=existing)

    bundle_link = tmp_path / "bundle-link"
    bundle_link.symlink_to(bundle, target_is_directory=True)
    with pytest.raises(BackupRestoreError, match="symbolic link"):
        verify_backup(bundle_link)

    broken_target = tmp_path / "broken-target"
    broken_target.symlink_to(tmp_path / "missing-target", target_is_directory=True)
    with pytest.raises(BackupRestoreError, match="already exists"):
        restore_backup(bundle=bundle, target=broken_target)


@pytest.mark.parametrize("artifact_kind", ["mysql-dump", "storage-tree", "chroma-projection"])
def test_cli_runs_a_reproducible_isolated_drill(tmp_path: Path, artifact_kind: str) -> None:
    script = Path(__file__).parents[1] / "scripts" / "backup_restore.py"
    if artifact_kind == "mysql-dump":
        fixture = tmp_path / "fixture.sql"
        fixture.write_text("SELECT 1;\n", encoding="utf-8")
        restored = tmp_path / "restored.sql"
    else:
        fixture = tmp_path / "fixture"
        fixture.mkdir()
        (fixture / "payload.bin").write_bytes(artifact_kind.encode("ascii"))
        restored = tmp_path / "restored"
    bundle = tmp_path / "bundle"

    commands = [
        ["backup", "--kind", artifact_kind, "--source", str(fixture), "--output", str(bundle)],
        ["restore", "--bundle", str(bundle), "--target", str(restored)],
        ["verify", "--bundle", str(bundle), "--target", str(restored)],
    ]
    for arguments in commands:
        result = subprocess.run([sys.executable, str(script), *arguments], capture_output=True, check=False, text=True)
        assert result.returncode == 0, result.stderr
        assert "verified:" in result.stdout

    if artifact_kind == "mysql-dump":
        assert restored.read_bytes() == fixture.read_bytes()
    else:
        assert (restored / "payload.bin").read_bytes() == (fixture / "payload.bin").read_bytes()


def test_cli_rebuild_projection_performs_verified_atomic_swap(tmp_path: Path) -> None:
    script = Path(__file__).parents[1] / "scripts" / "backup_restore.py"
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "chroma.sqlite3").write_bytes(b"candidate")
    bundle = tmp_path / "bundle"
    target = tmp_path / "target"
    target.mkdir()
    (target / "chroma.sqlite3").write_bytes(b"previous")

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "backup",
            "--kind",
            "chroma-projection",
            "--source",
            str(fixture),
            "--output",
            str(bundle),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "rebuild-projection",
            "--bundle",
            str(bundle),
            "--target",
            str(target),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "chroma-projection" in result.stdout
    assert (target / "chroma.sqlite3").read_bytes() == b"candidate"
