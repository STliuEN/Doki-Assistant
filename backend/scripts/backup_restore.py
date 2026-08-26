from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

SCHEMA_VERSION = 1
MANIFEST_NAME = "manifest.json"
PAYLOAD_DIR = "payload"
ARTIFACT_KINDS = ("mysql-dump", "storage-tree", "chroma-projection")
DIRECTORY_KINDS = frozenset({"storage-tree", "chroma-projection"})
BUFFER_SIZE = 1024 * 1024


class BackupRestoreError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(BUFFER_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _content_digest(artifact_kind: str, source_format: str, entries: list[dict[str, Any]]) -> str:
    content = {
        "artifact_kind": artifact_kind,
        "entries": entries,
        "source_format": source_format,
    }
    return hashlib.sha256(_canonical_json(content)).hexdigest()


def _assert_not_symlink(path: Path, label: str) -> None:
    if path.is_symlink():
        raise BackupRestoreError(f"{label} must not be a symbolic link: {path}")


def _is_relative_to(path: Path, other: Path) -> bool:
    try:
        path.relative_to(other)
    except ValueError:
        return False
    return True


def _validate_source_and_output(source: Path, output: Path, artifact_kind: str) -> tuple[Path, Path]:
    _assert_not_symlink(source, "source")
    if not source.exists():
        raise BackupRestoreError(f"source does not exist: {source}")
    if artifact_kind == "mysql-dump" and not source.is_file():
        raise BackupRestoreError("mysql-dump source must be one offline dump file")
    if artifact_kind in DIRECTORY_KINDS and not source.is_dir():
        raise BackupRestoreError(f"{artifact_kind} source must be a directory")

    if output.exists() or output.is_symlink():
        raise BackupRestoreError(f"backup output already exists: {output}")
    source = source.resolve(strict=True)
    output = output.resolve(strict=False)
    if _is_relative_to(output, source) or _is_relative_to(source, output):
        raise BackupRestoreError("source and backup output must not contain one another")
    return source, output


def _directory_entries(source: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for current_root, directory_names, file_names in os.walk(source, followlinks=False):
        root = Path(current_root)
        for name in sorted(directory_names):
            directory = root / name
            _assert_not_symlink(directory, "source entry")
            relative = directory.relative_to(source).as_posix()
            entries.append({"path": relative, "type": "directory"})
        for name in sorted(file_names):
            file_path = root / name
            _assert_not_symlink(file_path, "source entry")
            if not file_path.is_file():
                raise BackupRestoreError(f"source entry is not a regular file: {file_path}")
            relative = file_path.relative_to(source).as_posix()
            entries.append(
                {
                    "path": relative,
                    "sha256": _sha256_file(file_path),
                    "size": file_path.stat().st_size,
                    "type": "file",
                }
            )
    return sorted(entries, key=lambda entry: (entry["path"], entry["type"]))


def _copy_directory_entries(source: Path, payload: Path, entries: list[dict[str, Any]]) -> None:
    payload.mkdir()
    for entry in entries:
        destination = payload / PurePosixPath(entry["path"])
        if entry["type"] == "directory":
            destination.mkdir(parents=True, exist_ok=False)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / PurePosixPath(entry["path"]), destination)


def create_backup(*, artifact_kind: str, source: Path, output: Path) -> dict[str, Any]:
    if artifact_kind not in ARTIFACT_KINDS:
        raise BackupRestoreError(f"unsupported artifact kind: {artifact_kind}")
    source, output = _validate_source_and_output(source, output, artifact_kind)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        payload = staging / PAYLOAD_DIR
        if artifact_kind == "mysql-dump":
            entries = [
                {
                    "path": "dump.sql",
                    "sha256": _sha256_file(source),
                    "size": source.stat().st_size,
                    "type": "file",
                }
            ]
            payload.mkdir()
            shutil.copyfile(source, payload / "dump.sql")
            source_format = "offline-sql-file"
        else:
            entries = _directory_entries(source)
            _copy_directory_entries(source, payload, entries)
            source_format = "directory-tree"

        manifest = {
            "artifact_kind": artifact_kind,
            "content_sha256": _content_digest(artifact_kind, source_format, entries),
            "created_at": datetime.now(UTC).isoformat(),
            "entries": entries,
            "schema_version": SCHEMA_VERSION,
            "source_format": source_format,
        }
        (staging / MANIFEST_NAME).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        verify_backup(staging)
        staging.replace(output)
        return manifest
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _safe_relative_path(value: Any) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise BackupRestoreError("manifest entry path must be a non-empty string")
    # Manifest paths are emitted as POSIX separators, but the bundle can be
    # verified on Windows.  Reject drive-qualified, rooted, or backslash
    # paths before converting them to ``Path`` objects; otherwise a value such
    # as ``C:\\outside`` could become absolute during Windows path joining.
    windows_path = PureWindowsPath(value)
    if "\\" in value or windows_path.drive or windows_path.root:
        raise BackupRestoreError(f"unsafe manifest entry path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts or path.as_posix() != value:
        raise BackupRestoreError(f"unsafe manifest entry path: {value!r}")
    return path


def _load_manifest(bundle: Path) -> dict[str, Any]:
    _assert_not_symlink(bundle, "bundle")
    if not bundle.is_dir():
        raise BackupRestoreError(f"backup bundle is not a directory: {bundle}")
    manifest_path = bundle / MANIFEST_NAME
    _assert_not_symlink(manifest_path, "manifest")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupRestoreError(f"cannot read backup manifest: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise BackupRestoreError("unsupported backup manifest schema")
    artifact_kind = manifest.get("artifact_kind")
    source_format = manifest.get("source_format")
    entries = manifest.get("entries")
    if artifact_kind not in ARTIFACT_KINDS or not isinstance(entries, list):
        raise BackupRestoreError("invalid backup manifest metadata")
    expected_format = "offline-sql-file" if artifact_kind == "mysql-dump" else "directory-tree"
    if source_format != expected_format:
        raise BackupRestoreError("artifact kind and source format disagree")

    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise BackupRestoreError("manifest entries must be objects")
        path = _safe_relative_path(entry.get("path"))
        relative = path.as_posix()
        if relative in seen:
            raise BackupRestoreError(f"duplicate manifest entry: {relative}")
        seen.add(relative)
        if entry.get("type") == "file":
            sha256 = entry.get("sha256")
            size = entry.get("size")
            if not isinstance(sha256, str) or len(sha256) != 64 or not isinstance(size, int) or size < 0:
                raise BackupRestoreError(f"invalid file metadata: {relative}")
        elif entry.get("type") != "directory":
            raise BackupRestoreError(f"invalid entry type: {relative}")
    if artifact_kind == "mysql-dump" and entries != [
        {
            "path": "dump.sql",
            "sha256": entries[0].get("sha256") if len(entries) == 1 else None,
            "size": entries[0].get("size") if len(entries) == 1 else None,
            "type": "file",
        }
    ]:
        raise BackupRestoreError("mysql-dump manifest must contain only payload/dump.sql")
    expected_digest = _content_digest(artifact_kind, source_format, entries)
    if manifest.get("content_sha256") != expected_digest:
        raise BackupRestoreError("backup manifest content digest mismatch")
    return manifest


def _actual_entries(root: Path) -> list[dict[str, Any]]:
    _assert_not_symlink(root, "payload")
    if not root.is_dir():
        raise BackupRestoreError(f"payload is not a directory: {root}")
    return _directory_entries(root)


def verify_backup(bundle: Path) -> dict[str, Any]:
    _assert_not_symlink(bundle, "bundle")
    bundle = bundle.resolve(strict=True)
    manifest = _load_manifest(bundle)
    expected = manifest["entries"]
    actual = _actual_entries(bundle / PAYLOAD_DIR)
    if actual != expected:
        raise BackupRestoreError("backup payload does not match manifest")
    return manifest


def _verify_restored_target(manifest: dict[str, Any], target: Path) -> None:
    if manifest["artifact_kind"] == "mysql-dump":
        _assert_not_symlink(target, "restored target")
        if not target.is_file():
            raise BackupRestoreError(f"restored MySQL dump is not a file: {target}")
        expected = manifest["entries"][0]
        if target.stat().st_size != expected["size"] or _sha256_file(target) != expected["sha256"]:
            raise BackupRestoreError("restored MySQL dump does not match manifest")
        return
    if _actual_entries(target) != manifest["entries"]:
        raise BackupRestoreError("restored directory does not match manifest")


def verify_restored(bundle: Path, target: Path) -> dict[str, Any]:
    manifest = verify_backup(bundle)
    _verify_restored_target(manifest, target.resolve(strict=True))
    return manifest


def restore_backup(*, bundle: Path, target: Path) -> dict[str, Any]:
    _assert_not_symlink(bundle, "bundle")
    bundle = bundle.resolve(strict=True)
    manifest = verify_backup(bundle)
    if target.exists() or target.is_symlink():
        raise BackupRestoreError(f"restore target already exists: {target}")
    target = target.resolve(strict=False)
    if _is_relative_to(target, bundle) or _is_relative_to(bundle, target):
        raise BackupRestoreError("backup bundle and restore target must not contain one another")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
    try:
        payload = bundle / PAYLOAD_DIR
        if manifest["artifact_kind"] == "mysql-dump":
            staging.rmdir()
            shutil.copyfile(payload / "dump.sql", staging)
        else:
            shutil.copytree(payload, staging, dirs_exist_ok=True)
        _verify_restored_target(manifest, staging)
        staging.replace(target)
        return manifest
    except BaseException:
        if staging.is_dir() and not staging.is_symlink():
            shutil.rmtree(staging, ignore_errors=True)
        elif staging.exists():
            staging.unlink(missing_ok=True)
        raise


def rebuild_projection(
    *,
    bundle: Path,
    target: Path,
    quarantine_root: Path | None = None,
) -> dict[str, Any]:
    """Rebuild an isolated Chroma projection with a validated atomic swap.

    The bundle is verified before touching ``target``.  A new projection is
    materialized in a sibling staging directory, verified against the same
    manifest, and then renamed into place.  An existing target is retained in
    a quarantine directory so an operator can inspect or roll back it.  The
    swap is guarded by rollback: if installing the new generation fails, the
    old target is restored and no bytes are deleted.

    This helper deliberately works on an offline backup bundle only.  It does
    not open Chroma, connect to MySQL, or infer a source of truth.
    """

    bundle = Path(bundle)
    target = Path(target)
    manifest = verify_backup(bundle)
    if manifest["artifact_kind"] != "chroma-projection":
        raise BackupRestoreError("projection rebuild requires a chroma-projection bundle")

    _assert_not_symlink(target, "projection target")
    if target.exists() and not target.is_dir():
        raise BackupRestoreError(f"projection target must be a directory: {target}")
    bundle = bundle.resolve(strict=True)
    target = target.resolve(strict=False)
    if _is_relative_to(target, bundle) or _is_relative_to(bundle, target):
        raise BackupRestoreError("projection bundle and target must not contain one another")

    if quarantine_root is None:
        quarantine_root = target.parent / ".projection-quarantine"
    quarantine_root = Path(quarantine_root)
    _assert_not_symlink(quarantine_root, "projection quarantine root")
    quarantine_root = quarantine_root.resolve(strict=False)
    if _is_relative_to(quarantine_root, bundle) or _is_relative_to(bundle, quarantine_root):
        raise BackupRestoreError("projection bundle and quarantine root must not contain one another")
    if _is_relative_to(quarantine_root, target) or _is_relative_to(target, quarantine_root):
        raise BackupRestoreError("projection target and quarantine root must not contain one another")

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}-rebuild-", dir=target.parent))
    old_target: Path | None = None
    try:
        shutil.copytree(bundle / PAYLOAD_DIR, staging, dirs_exist_ok=True)
        _verify_restored_target(manifest, staging)

        if target.exists():
            quarantine_root.mkdir(parents=True, exist_ok=True)
            old_target = quarantine_root / f"{target.name}-{uuid.uuid4().hex}"
            os.replace(target, old_target)
        try:
            os.replace(staging, target)
        except BaseException:
            # Restore the previous generation if finalization failed.  Keep
            # the quarantine copy if rollback itself fails for forensics.
            if old_target is not None and old_target.exists() and not target.exists():
                try:
                    os.replace(old_target, target)
                    old_target = None
                except OSError:
                    pass
            raise

        result = dict(manifest)
        result["target"] = str(target)
        result["quarantined_previous"] = str(old_target) if old_target is not None else None
        return result
    finally:
        if staging.exists() and not staging.is_symlink():
            shutil.rmtree(staging, ignore_errors=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Offline backup/restore tool for an isolated MySQL dump, Storage tree, or Chroma projection."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup", help="Create and verify a new backup bundle.")
    backup.add_argument("--kind", required=True, choices=ARTIFACT_KINDS)
    backup.add_argument("--source", required=True, type=Path)
    backup.add_argument("--output", required=True, type=Path)

    restore = subparsers.add_parser("restore", help="Restore into a new target and verify it.")
    restore.add_argument("--bundle", required=True, type=Path)
    restore.add_argument("--target", required=True, type=Path)

    verify = subparsers.add_parser("verify", help="Verify a bundle and optionally a restored target.")
    verify.add_argument("--bundle", required=True, type=Path)
    verify.add_argument("--target", type=Path)

    rebuild = subparsers.add_parser(
        "rebuild-projection",
        help="Rebuild an isolated Chroma projection from a verified backup bundle.",
    )
    rebuild.add_argument("--bundle", required=True, type=Path)
    rebuild.add_argument("--target", required=True, type=Path)
    rebuild.add_argument("--quarantine-root", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "backup":
            manifest = create_backup(artifact_kind=args.kind, source=args.source, output=args.output)
            location = args.output
        elif args.command == "restore":
            manifest = restore_backup(bundle=args.bundle, target=args.target)
            location = args.target
        elif args.command == "rebuild-projection":
            manifest = rebuild_projection(
                bundle=args.bundle,
                target=args.target,
                quarantine_root=args.quarantine_root,
            )
            location = args.target
        else:
            manifest = verify_restored(args.bundle, args.target) if args.target else verify_backup(args.bundle)
            location = args.target or args.bundle
    except (BackupRestoreError, OSError) as exc:
        print(f"backup/restore failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"{args.command} verified: kind={manifest['artifact_kind']} "
        f"content_sha256={manifest['content_sha256']} path={location}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
