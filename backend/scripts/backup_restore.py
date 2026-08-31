from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

# Direct script execution sets ``sys.path[0]`` to ``backend/scripts``.  Keep
# the documented ``python scripts/backup_restore.py ...`` form able to import
# the sibling ``app`` package without relying on the caller's ``PYTHONPATH``.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

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


def _content_digest(
    artifact_kind: str,
    source_format: str,
    entries: list[dict[str, Any]],
    metadata: Mapping[str, Any] | None = None,
) -> str:
    content = {
        "artifact_kind": artifact_kind,
        "entries": entries,
        "source_format": source_format,
    }
    if metadata is not None:
        content["metadata"] = dict(metadata)
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


def create_backup(
    *,
    artifact_kind: str,
    source: Path,
    output: Path,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
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

        if metadata is not None and not isinstance(metadata, Mapping):
            raise BackupRestoreError("backup metadata must be a JSON object")
        manifest = {
            "artifact_kind": artifact_kind,
            "content_sha256": _content_digest(artifact_kind, source_format, entries, metadata),
            "created_at": datetime.now(UTC).isoformat(),
            "entries": entries,
            "schema_version": SCHEMA_VERSION,
            "source_format": source_format,
        }
        if metadata is not None:
            try:
                _canonical_json(metadata)
            except (TypeError, ValueError) as exc:
                raise BackupRestoreError("backup metadata must be JSON-serializable") from exc
            manifest["metadata"] = dict(metadata)
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
    if artifact_kind == "mysql-dump":
        if len(entries) != 1 or entries[0].get("path") != "dump.sql" or entries[0].get("type") != "file":
            raise BackupRestoreError("mysql-dump manifest must contain only payload/dump.sql")
    metadata = manifest.get("metadata")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise BackupRestoreError("backup metadata must be a JSON object")
    expected_digest = _content_digest(artifact_kind, source_format, entries, metadata)
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


def _canonical_value(value: Any) -> Any:
    """Convert SQL values into a stable, JSON-compatible representation."""

    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise BackupRestoreError("unsupported non-finite SQL float value")
        return {"__float__": value.hex()}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"__bytes__": bytes(value).hex()}
    if isinstance(value, Decimal):
        return {"__decimal__": format(value, "f")}
    if isinstance(value, datetime):
        normalized = value.astimezone(UTC) if value.tzinfo is not None else value
        return {"__datetime__": normalized.isoformat()}
    if isinstance(value, date):
        return {"__date__": value.isoformat()}
    if isinstance(value, time):
        return {"__time__": value.isoformat()}
    if isinstance(value, uuid.UUID):
        return {"__uuid__": str(value)}
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, set):
        return sorted((_canonical_value(item) for item in value), key=lambda item: _canonical_json(item))
    type_name = f"{type(value).__module__}.{type(value).__qualname__}"
    raise BackupRestoreError(f"unsupported SQL value type: {type_name}")


def canonical_row_digest(rows: Iterable[Mapping[str, Any]], columns: Sequence[str]) -> str:
    """Return a deterministic digest independent of database row iteration order."""

    column_names = tuple(columns)
    encoded_rows = []
    for row in rows:
        try:
            normalized = {column: _canonical_value(row[column]) for column in column_names}
        except (KeyError, TypeError) as exc:
            raise BackupRestoreError("schema row is missing a requested column") from exc
        encoded_rows.append(_canonical_json(normalized))
    encoded_rows.sort()
    digest = hashlib.sha256()
    digest.update(_canonical_json({"columns": column_names}))
    digest.update(b"\n")
    for encoded in encoded_rows:
        digest.update(encoded)
        digest.update(b"\n")
    return digest.hexdigest()


def _quote_identifier(identifier: str) -> str:
    if not isinstance(identifier, str) or not identifier or not identifier.replace("_", "a").replace("$", "a").isalnum():
        raise BackupRestoreError(f"unsafe SQL identifier: {identifier!r}")
    return f"`{identifier.replace('`', '``')}`"


def _inspection_columns(inspector: Any, table_name: str) -> list[dict[str, Any]]:
    columns = []
    for column in inspector.get_columns(table_name):
        columns.append(
            {
                "name": column.get("name"),
                "type": str(column.get("type")),
                "nullable": bool(column.get("nullable")),
                "default": None if column.get("default") is None else str(column.get("default")),
                "autoincrement": column.get("autoincrement"),
            }
        )
    return sorted(columns, key=lambda item: str(item["name"]))


def _inspection_constraints(inspector: Any, table_name: str) -> dict[str, Any]:
    primary_key = inspector.get_pk_constraint(table_name) or {}
    indexes = [
        {
            "name": item.get("name"),
            "unique": bool(item.get("unique")),
            "columns": list(item.get("column_names") or []),
        }
        for item in inspector.get_indexes(table_name)
    ]
    unique_constraints = [
        {"name": item.get("name"), "columns": list(item.get("column_names") or [])}
        for item in inspector.get_unique_constraints(table_name)
    ]
    foreign_keys = [
        {
            "name": item.get("name"),
            "columns": list(item.get("constrained_columns") or []),
            "referred_table": item.get("referred_table"),
            "referred_columns": list(item.get("referred_columns") or []),
            "ondelete": (item.get("options") or {}).get("ondelete"),
        }
        for item in inspector.get_foreign_keys(table_name)
    ]
    checks = [
        {"name": item.get("name"), "sqltext": str(item.get("sqltext") or "")}
        for item in inspector.get_check_constraints(table_name)
    ]
    return {
        "primary_key": {
            "name": primary_key.get("name"),
            "columns": list(primary_key.get("constrained_columns") or []),
        },
        "indexes": sorted(indexes, key=lambda item: (str(item["name"]), item["columns"])),
        "unique_constraints": sorted(unique_constraints, key=lambda item: (str(item["name"]), item["columns"])),
        "foreign_keys": sorted(
            foreign_keys,
            key=lambda item: (str(item["name"]), item["columns"], str(item["referred_table"])),
        ),
        "check_constraints": sorted(checks, key=lambda item: (str(item["name"]), item["sqltext"])),
    }


def build_schema_inventory(connection: Any, *, include_rows: bool = True) -> dict[str, Any]:
    """Build a read-only schema/row inventory from an open SQL connection.

    The caller owns the connection and is responsible for selecting an
    explicitly approved E2 target.  This function performs SELECTs only.
    """

    from sqlalchemy import inspect, text

    inspector = inspect(connection)
    table_names = sorted(str(name) for name in inspector.get_table_names())
    tables: dict[str, Any] = {}
    for table_name in table_names:
        columns = _inspection_columns(inspector, table_name)
        constraints = _inspection_constraints(inspector, table_name)
        quoted_table = _quote_identifier(table_name)
        row_count = int(connection.execute(text(f"SELECT COUNT(*) FROM {quoted_table}")).scalar_one())
        column_names = [str(column["name"]) for column in columns]
        primary_columns = constraints["primary_key"]["columns"]
        order_columns = list(primary_columns) or column_names
        row_digest = None
        if include_rows and column_names:
            quoted_columns = ", ".join(_quote_identifier(column) for column in column_names)
            order_clause = ""
            if order_columns:
                order_clause = " ORDER BY " + ", ".join(_quote_identifier(column) for column in order_columns)
            rows = connection.execute(text(f"SELECT {quoted_columns} FROM {quoted_table}{order_clause}")).mappings()
            row_digest = canonical_row_digest(rows, column_names)
        tables[table_name] = {
            "schema": {"columns": columns, **constraints},
            "row_count": row_count,
            "content_sha256": row_digest,
        }

    if getattr(getattr(connection, "dialect", None), "name", None) == "mysql":
        database_name = connection.execute(text("SELECT DATABASE()")).scalar_one_or_none()
    else:
        database_name = getattr(getattr(connection, "engine", None), "url", None)
        database_name = getattr(database_name, "database", None)
    revision = None
    if "alembic_version" in tables:
        revision_rows = connection.execute(text("SELECT version_num FROM `alembic_version` ORDER BY version_num")).scalars()
        revisions = [str(value) for value in revision_rows]
        revision = revisions[0] if len(revisions) == 1 else revisions
    inventory = {
        "schema_version": 1,
        "database": None if database_name is None else str(database_name),
        "alembic_revision": revision,
        "tables": tables,
    }
    inventory["inventory_sha256"] = hashlib.sha256(_canonical_json(inventory)).hexdigest()
    return inventory


def compare_sql_inventories(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> dict[str, Any]:
    """Compare schema, constraints, row counts and canonical content digests."""

    expected_tables = expected.get("tables") if isinstance(expected.get("tables"), Mapping) else {}
    actual_tables = actual.get("tables") if isinstance(actual.get("tables"), Mapping) else {}
    expected_names = set(expected_tables)
    actual_names = set(actual_tables)
    missing = sorted(expected_names - actual_names)
    extra = sorted(actual_names - expected_names)
    changed: dict[str, Any] = {}
    for table_name in sorted(expected_names & actual_names):
        expected_table = expected_tables[table_name]
        actual_table = actual_tables[table_name]
        changes: dict[str, Any] = {}
        if expected_table.get("schema") != actual_table.get("schema"):
            changes["schema"] = {"expected": expected_table.get("schema"), "actual": actual_table.get("schema")}
        if expected_table.get("row_count") != actual_table.get("row_count"):
            changes["row_count"] = {"expected": expected_table.get("row_count"), "actual": actual_table.get("row_count")}
        if expected_table.get("content_sha256") != actual_table.get("content_sha256"):
            changes["content_sha256"] = {
                "expected": expected_table.get("content_sha256"),
                "actual": actual_table.get("content_sha256"),
            }
        if changes:
            changed[table_name] = changes
    if expected.get("alembic_revision") != actual.get("alembic_revision"):
        changed["__alembic_revision__"] = {
            "expected": expected.get("alembic_revision"),
            "actual": actual.get("alembic_revision"),
        }
    return {
        "equal": not missing and not extra and not changed,
        "missing_tables": missing,
        "extra_tables": extra,
        "changed_tables": changed,
    }


def assert_sql_inventory_equal(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> None:
    diff = compare_sql_inventories(expected, actual)
    if not diff["equal"]:
        raise BackupRestoreError(f"SQL inventory mismatch: {_canonical_json(diff).decode('utf-8')}")


def write_json_artifact(value: Mapping[str, Any], output: Path) -> None:
    """Atomically write an inventory/evidence JSON file without overwriting."""

    output = Path(output)
    if output.exists() or output.is_symlink():
        raise BackupRestoreError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, staging_name = tempfile.mkstemp(prefix=f".{output.name}-", suffix=".tmp", dir=output.parent)
    os.close(descriptor)
    staging = Path(staging_name)
    try:
        staging.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        staging.replace(output)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise


def _load_explicit_guard(
    *,
    purpose: str,
    database_url: str,
    approval_token: str,
    preflight_file: Path,
    inspector: Any = None,
) -> Any:
    """Load an E2 guard from explicit arguments; never consult dotenv."""

    from app.db.e2_guard import E2GuardError, load_guard_from_environment

    values = {
        "E2_MIGRATION_ENABLED": "I_UNDERSTAND_E2_MIGRATION",
        "E2_DATABASE_URL": database_url,
        "E2_APPROVAL_TOKEN": approval_token,
        "E2_PREFLIGHT_FILE": str(Path(preflight_file)),
    }
    kwargs: dict[str, Any] = {"environ": values}
    if inspector is not None:
        kwargs["inspector"] = inspector
    try:
        return load_guard_from_environment(purpose, **kwargs)
    except E2GuardError as exc:
        raise BackupRestoreError(f"E2 {purpose} guard refused the operation: {exc}") from exc


def issue_e2_preflight(
    *,
    database_url: str,
    approval_token: str,
    purposes: list[str],
    issuance_switch: str,
    lifetime_seconds: int,
) -> dict[str, Any]:
    """Issue a short-lived E2 preflight record from explicit CLI arguments."""

    from app.db.e2_guard import E2GuardError, issue_e2_preflight_record

    try:
        return asyncio.run(
            issue_e2_preflight_record(
                database_url=database_url,
                approval_token=approval_token,
                purposes=purposes,
                issuance_switch=issuance_switch,
                lifetime_seconds=lifetime_seconds,
            )
        )
    except E2GuardError as exc:
        raise BackupRestoreError(f"E2 preflight issuance refused: {exc}") from exc


def _mysql_cli_args(database_url: str, executable: str) -> tuple[list[str], str]:
    from sqlalchemy.engine import make_url

    url = make_url(database_url)
    if url.drivername != "mysql+aiomysql" or not url.host or not url.port or not url.database or not url.username:
        raise BackupRestoreError("E2 database URL is not a complete approved MySQL URL")
    args = [
        executable,
        "--protocol=TCP",
        "--host",
        str(url.host),
        "--port",
        str(url.port),
        "--user",
        str(url.username),
    ]
    # ``mysql`` accepts ``--database`` while ``mysqldump`` treats the
    # database name as a positional argument (and rejects ``--database``).
    executable_name = Path(str(executable)).name.casefold()
    if "mysqldump" in executable_name:
        args.append(str(url.database))
    else:
        args.extend(["--database", str(url.database)])
    password = "" if url.password is None else str(url.password)
    return args, password


def _mysql_container_cli_args(database_url: str, executable: str, container_name: str) -> tuple[list[str], str]:
    """Build a client command executed inside one explicitly approved E2 container."""

    args, password = _mysql_cli_args(database_url, executable)
    # The DSN intentionally names the loopback host port.  Once execution is
    # moved inside the target container, connect to that container's MySQL
    # listener instead; the target/container guard is checked by the caller.
    args[args.index("--host") + 1] = "127.0.0.1"
    args[args.index("--port") + 1] = "3306"
    return ["docker", "exec", "-i", "--env", "MYSQL_PWD", container_name, *args], password


def _mysql_environment(password: str) -> dict[str, str]:
    environment = dict(os.environ)
    environment["MYSQL_PWD"] = password
    return environment


def dump_mysql_database(
    *,
    database_url: str,
    approval_token: str,
    preflight_file: Path,
    output: Path,
    mysqldump_bin: str = "mysqldump",
    mysqldump_container: str | None = None,
    timeout_seconds: int = 900,
    inspector: Any = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a verified E2 SQL bundle with ``mysqldump --single-transaction``."""

    guard = _load_explicit_guard(
        purpose="dump",
        database_url=database_url,
        approval_token=approval_token,
        preflight_file=preflight_file,
        inspector=inspector,
    )
    if guard.target.role != "source":
        raise BackupRestoreError("database dump requires the approved E2 source target")
    if mysqldump_container is not None and mysqldump_container != guard.target.container_name:
        raise BackupRestoreError("mysqldump container must be the approved E2 source container")
    if mysqldump_container is not None and mysqldump_bin != "mysqldump":
        raise BackupRestoreError("--mysqldump-bin cannot be combined with --mysqldump-container")
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise BackupRestoreError(f"backup output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix=f".{output.name}-dump-", dir=output.parent))
    dump_file = staging_dir / "dump.sql"
    try:
        if mysqldump_container is None:
            args, password = _mysql_cli_args(database_url, mysqldump_bin)
            args.extend(
                [
                    "--single-transaction",
                    "--skip-lock-tables",
                    "--hex-blob",
                    "--routines",
                    "--events",
                    "--triggers",
                    "--set-gtid-purged=OFF",
                    "--result-file",
                    str(dump_file),
                ]
            )
        else:
            args, password = _mysql_container_cli_args(database_url, "mysqldump", mysqldump_container)
            args.extend(
                [
                    "--single-transaction",
                    "--skip-lock-tables",
                    "--hex-blob",
                    "--routines",
                    "--events",
                    "--triggers",
                    "--set-gtid-purged=OFF",
                ]
            )
        result = subprocess.run(
            args,
            capture_output=True,
            check=False,
            env=_mysql_environment(password),
            timeout=timeout_seconds,
            text=mysqldump_container is None,
        )
        if result.returncode != 0:
            detail_value = result.stderr or result.stdout or "mysqldump failed"
            detail = (
                detail_value.decode("utf-8", errors="replace")
                if isinstance(detail_value, bytes)
                else str(detail_value)
            ).strip()[:1000]
            raise BackupRestoreError(f"mysqldump failed with exit code {result.returncode}: {detail}")
        if mysqldump_container is not None:
            output_bytes = result.stdout if isinstance(result.stdout, bytes) else str(result.stdout).encode("utf-8")
            dump_file.write_bytes(output_bytes)
        if not dump_file.is_file():
            raise BackupRestoreError("mysqldump completed without producing a dump file")
        target_metadata: dict[str, Any] = {
            "operation": "mysqldump",
            "database_url_sha256": _dsn_fingerprint(database_url),
            "target": {
                "role": guard.target.role,
                "host": guard.target.host,
                "port": guard.target.port,
                "database": guard.target.database,
                "container_name": guard.target.container_name,
            },
            "options": {
                "single_transaction": True,
                "skip_lock_tables": True,
                "client_mode": "container-exec" if mysqldump_container is not None else "host",
            },
            "source_preflight": {
                "schema_version": guard.preflight["schema_version"],
                "target": dict(guard.preflight["target"]),
                "container": dict(guard.preflight["container"]),
                "database": dict(guard.preflight["database"]),
            },
        }
        if metadata is not None:
            target_metadata["caller"] = dict(metadata)
        return create_backup(artifact_kind="mysql-dump", source=dump_file, output=output, metadata=target_metadata)
    except subprocess.TimeoutExpired as exc:
        raise BackupRestoreError("mysqldump timed out") from exc
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


def _dsn_fingerprint(database_url: str) -> str:
    from app.db.e2_guard import database_url_fingerprint

    return database_url_fingerprint(database_url)


def _require_mysql_dump_source_metadata(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    """Reject legacy or manually assembled SQL bundles before import."""

    metadata = manifest.get("metadata")
    if not isinstance(metadata, Mapping):
        raise BackupRestoreError("MySQL restore requires E2 mysqldump source metadata")
    if metadata.get("operation") != "mysqldump":
        raise BackupRestoreError("MySQL restore requires an E2 mysqldump source metadata record")
    source_digest = metadata.get("database_url_sha256")
    if (
        not isinstance(source_digest, str)
        or len(source_digest) != 64
        or any(character not in "0123456789abcdef" for character in source_digest)
    ):
        raise BackupRestoreError("MySQL dump source DSN fingerprint is invalid")

    from app.db.e2_guard import approved_e2_target, e2_target_record

    expected_source = e2_target_record(approved_e2_target("source"))
    if metadata.get("target") != expected_source:
        raise BackupRestoreError("MySQL dump source target is outside the approved E2 topology")
    options = metadata.get("options")
    if not isinstance(options, Mapping) or options.get("single_transaction") is not True or options.get("skip_lock_tables") is not True:
        raise BackupRestoreError("MySQL dump source metadata does not prove a consistent single-transaction dump")

    source_preflight = metadata.get("source_preflight")
    if not isinstance(source_preflight, Mapping) or source_preflight.get("schema_version") != 1:
        raise BackupRestoreError("MySQL dump is missing E2 source preflight metadata")
    if source_preflight.get("target") != expected_source:
        raise BackupRestoreError("MySQL dump source preflight target is invalid")
    source_database = source_preflight.get("database")
    if (
        not isinstance(source_database, Mapping)
        or not isinstance(source_database.get("server_uuid"), str)
        or not source_database["server_uuid"].strip()
    ):
        raise BackupRestoreError("MySQL dump source preflight server UUID is missing")
    source_container = source_preflight.get("container")
    if not isinstance(source_container, Mapping):
        raise BackupRestoreError("MySQL dump source preflight container metadata is missing")
    for key in ("container_name", "container_id", "image_id", "image_reference"):
        if not isinstance(source_container.get(key), str) or not source_container[key]:
            raise BackupRestoreError(f"MySQL dump source preflight {key} is invalid")
    if source_container.get("container_name") != expected_source["container_name"]:
        raise BackupRestoreError("MySQL dump source preflight container is outside the approved topology")
    return metadata


def _mysql_query(
    *,
    database_url: str,
    query: str,
    mysql_bin: str,
    mysql_container: str | None = None,
    timeout_seconds: int,
) -> str:
    if mysql_container is None:
        args, password = _mysql_cli_args(database_url, mysql_bin)
    else:
        if mysql_bin != "mysql":
            raise BackupRestoreError("--mysql-bin cannot be combined with --mysql-container")
        args, password = _mysql_container_cli_args(database_url, "mysql", mysql_container)
    args.extend(["--batch", "--skip-column-names", "--execute", query])
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            check=False,
            env=_mysql_environment(password),
            timeout=timeout_seconds,
            text=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise BackupRestoreError("mysql query timed out") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "mysql query failed").strip()[:1000]
        raise BackupRestoreError(f"mysql query failed with exit code {result.returncode}: {detail}")
    return result.stdout.strip()


def restore_mysql_database(
    *,
    bundle: Path,
    database_url: str,
    approval_token: str,
    preflight_file: Path,
    mysql_bin: str = "mysql",
    mysql_container: str | None = None,
    timeout_seconds: int = 900,
    require_empty: bool = True,
    inspector: Any = None,
) -> dict[str, Any]:
    """Restore a verified dump into the approved, loopback-only restore target."""

    bundle = Path(bundle).resolve(strict=True)
    manifest = verify_backup(bundle)
    if manifest["artifact_kind"] != "mysql-dump":
        raise BackupRestoreError("MySQL restore requires a mysql-dump bundle")
    metadata = _require_mysql_dump_source_metadata(manifest)
    guard = _load_explicit_guard(
        purpose="restore",
        database_url=database_url,
        approval_token=approval_token,
        preflight_file=preflight_file,
        inspector=inspector,
    )
    if guard.target.role != "restore":
        raise BackupRestoreError("restore requires the separate approved E2 restore target")
    if mysql_container is not None and mysql_container != guard.target.container_name:
        raise BackupRestoreError("mysql container must be the approved E2 restore container")
    if metadata.get("database_url_sha256") == _dsn_fingerprint(database_url):
        raise BackupRestoreError("restore target must not be the dump source target")
    if require_empty:
        table_count = _mysql_query(
            database_url=database_url,
            query="SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'",
            mysql_bin=mysql_bin,
            mysql_container=mysql_container,
            timeout_seconds=timeout_seconds,
        )
        try:
            if int(table_count or "0") != 0:
                raise BackupRestoreError("restore target is not empty; refusing to import over existing tables")
        except ValueError as exc:
            raise BackupRestoreError("mysql returned an invalid target table count") from exc
    dump_path = bundle / PAYLOAD_DIR / "dump.sql"
    if mysql_container is None:
        args, password = _mysql_cli_args(database_url, mysql_bin)
    else:
        if mysql_bin != "mysql":
            raise BackupRestoreError("--mysql-bin cannot be combined with --mysql-container")
        args, password = _mysql_container_cli_args(database_url, "mysql", mysql_container)
    args.extend(["--binary-mode"])
    try:
        with dump_path.open("rb") as dump_source:
            result = subprocess.run(
                args,
                stdin=dump_source,
                capture_output=True,
                check=False,
                env=_mysql_environment(password),
                timeout=timeout_seconds,
                text=False,
            )
    except subprocess.TimeoutExpired as exc:
        raise BackupRestoreError("mysql restore timed out") from exc
    if result.returncode != 0:
        detail_value = result.stderr or result.stdout or b"mysql restore failed"
        detail = (
            detail_value.decode("utf-8", errors="replace")
            if isinstance(detail_value, bytes)
            else str(detail_value)
        ).strip()[:1000]
        raise BackupRestoreError(f"mysql restore failed with exit code {result.returncode}: {detail}")
    return {
        "operation": "mysql-restore",
        "artifact_kind": manifest["artifact_kind"],
        "content_sha256": manifest["content_sha256"],
        "target": {
            "role": guard.target.role,
            "host": guard.target.host,
            "port": guard.target.port,
            "database": guard.target.database,
            "container_name": guard.target.container_name,
        },
    }


async def ainventory_mysql_database(
    *,
    database_url: str,
    approval_token: str,
    preflight_file: Path,
    purpose: str = "inventory",
    include_rows: bool = True,
    inspector: Any = None,
) -> dict[str, Any]:
    """Collect a live E2 inventory through the guarded async SQL driver."""

    guard = _load_explicit_guard(
        purpose=purpose,
        database_url=database_url,
        approval_token=approval_token,
        preflight_file=preflight_file,
        inspector=inspector,
    )
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(guard.database_url, pool_size=1, max_overflow=0, echo=False)
    try:
        async with engine.connect() as connection:
            from app.db.e2_guard import verify_database_fingerprint

            await connection.run_sync(lambda sync: verify_database_fingerprint(sync, guard))
            return await connection.run_sync(lambda sync: build_schema_inventory(sync, include_rows=include_rows))
    finally:
        await engine.dispose()


def inventory_mysql_database(**kwargs: Any) -> dict[str, Any]:
    return asyncio.run(ainventory_mysql_database(**kwargs))


def restore_forward_mysql_database(
    *,
    bundle: Path,
    database_url: str,
    approval_token: str,
    preflight_file: Path,
    expected_inventory: Mapping[str, Any],
    mysql_bin: str = "mysql",
    mysql_container: str | None = None,
    timeout_seconds: int = 900,
    inspector: Any = None,
) -> dict[str, Any]:
    """Restore to a fresh E2 target, then require a zero-diff SQL inventory."""

    restored = restore_mysql_database(
        bundle=bundle,
        database_url=database_url,
        approval_token=approval_token,
        preflight_file=preflight_file,
        mysql_bin=mysql_bin,
        mysql_container=mysql_container,
        timeout_seconds=timeout_seconds,
        require_empty=True,
        inspector=inspector,
    )
    actual = inventory_mysql_database(
        database_url=database_url,
        approval_token=approval_token,
        preflight_file=preflight_file,
        purpose="restore-forward",
        include_rows=True,
        inspector=inspector,
    )
    diff = compare_sql_inventories(expected_inventory, actual)
    if not diff["equal"]:
        raise BackupRestoreError(f"restore-forward inventory mismatch: {_canonical_json(diff).decode('utf-8')}")
    return {**restored, "operation": "restore-forward", "inventory_sha256": actual["inventory_sha256"], "diff": diff}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Offline backup/restore tool for an isolated MySQL dump, Storage tree, or Chroma projection."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup", help="Create and verify a new backup bundle.")
    backup.add_argument("--kind", required=True, choices=ARTIFACT_KINDS)
    backup.add_argument("--source", required=True, type=Path)
    backup.add_argument("--output", required=True, type=Path)

    dump = subparsers.add_parser("dump-mysql", help="Create a guarded mysqldump bundle for an E2 source target.")
    dump.add_argument("--database-url", required=True)
    dump.add_argument("--approval-token", required=True)
    dump.add_argument("--preflight-file", required=True, type=Path)
    dump.add_argument("--output", required=True, type=Path)
    dump.add_argument("--mysqldump-bin", default="mysqldump")
    dump.add_argument(
        "--mysqldump-container",
        help="Run the bundled mysqldump client inside this exact approved E2 source container.",
    )
    dump.add_argument("--timeout-seconds", default=900, type=int)

    preflight = subparsers.add_parser(
        "issue-preflight",
        help="Issue a short-lived E2 preflight record after inspecting the approved target.",
    )
    preflight.add_argument("--database-url", required=True)
    preflight.add_argument("--approval-token", required=True)
    preflight.add_argument("--issuance-switch", required=True)
    preflight.add_argument("--purpose", dest="purposes", action="append", required=True)
    preflight.add_argument("--lifetime-seconds", default=900, type=int)
    preflight.add_argument("--output", required=True, type=Path)

    inventory = subparsers.add_parser("schema-inventory", help="Collect a guarded read-only E2 SQL inventory.")
    inventory.add_argument("--database-url", required=True)
    inventory.add_argument("--approval-token", required=True)
    inventory.add_argument("--preflight-file", required=True, type=Path)
    inventory.add_argument("--output", required=True, type=Path)
    inventory.add_argument("--no-rows", action="store_true", help="Record schema and row counts without content digests.")

    restore = subparsers.add_parser("restore", help="Restore into a new target and verify it.")
    restore.add_argument("--bundle", required=True, type=Path)
    restore.add_argument("--target", required=True, type=Path)

    restore_mysql = subparsers.add_parser(
        "restore-mysql",
        help="Restore a verified SQL bundle into a fresh, guarded E2 restore target.",
    )
    restore_mysql.add_argument("--bundle", required=True, type=Path)
    restore_mysql.add_argument("--database-url", required=True)
    restore_mysql.add_argument("--approval-token", required=True)
    restore_mysql.add_argument("--preflight-file", required=True, type=Path)
    restore_mysql.add_argument("--mysql-bin", default="mysql")
    restore_mysql.add_argument(
        "--mysql-container",
        help="Run the bundled mysql client inside this exact approved E2 restore container.",
    )
    restore_mysql.add_argument("--timeout-seconds", default=900, type=int)

    restore_forward = subparsers.add_parser(
        "restore-forward",
        help="Restore into the guarded restore target and require a zero-diff inventory.",
    )
    restore_forward.add_argument("--bundle", required=True, type=Path)
    restore_forward.add_argument("--database-url", required=True)
    restore_forward.add_argument("--approval-token", required=True)
    restore_forward.add_argument("--preflight-file", required=True, type=Path)
    restore_forward.add_argument("--expected-inventory", required=True, type=Path)
    restore_forward.add_argument("--mysql-bin", default="mysql")
    restore_forward.add_argument(
        "--mysql-container",
        help="Run the bundled mysql client inside this exact approved E2 restore container.",
    )
    restore_forward.add_argument("--timeout-seconds", default=900, type=int)

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
        elif args.command == "dump-mysql":
            manifest = dump_mysql_database(
                database_url=args.database_url,
                approval_token=args.approval_token,
                preflight_file=args.preflight_file,
                output=args.output,
                mysqldump_bin=args.mysqldump_bin,
                mysqldump_container=args.mysqldump_container,
                timeout_seconds=args.timeout_seconds,
            )
            location = args.output
        elif args.command == "issue-preflight":
            manifest = issue_e2_preflight(
                database_url=args.database_url,
                approval_token=args.approval_token,
                purposes=args.purposes,
                issuance_switch=args.issuance_switch,
                lifetime_seconds=args.lifetime_seconds,
            )
            write_json_artifact(manifest, args.output)
            location = args.output
        elif args.command == "schema-inventory":
            manifest = inventory_mysql_database(
                database_url=args.database_url,
                approval_token=args.approval_token,
                preflight_file=args.preflight_file,
                include_rows=not args.no_rows,
            )
            write_json_artifact(manifest, args.output)
            location = args.output
        elif args.command == "restore":
            manifest = restore_backup(bundle=args.bundle, target=args.target)
            location = args.target
        elif args.command == "restore-mysql":
            manifest = restore_mysql_database(
                bundle=args.bundle,
                database_url=args.database_url,
                approval_token=args.approval_token,
                preflight_file=args.preflight_file,
                mysql_bin=args.mysql_bin,
                mysql_container=args.mysql_container,
                timeout_seconds=args.timeout_seconds,
            )
            location = args.database_url.split("@", 1)[-1]
        elif args.command == "restore-forward":
            try:
                expected_inventory = json.loads(args.expected_inventory.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise BackupRestoreError(f"cannot read expected inventory: {exc}") from exc
            if not isinstance(expected_inventory, Mapping):
                raise BackupRestoreError("expected inventory must be a JSON object")
            manifest = restore_forward_mysql_database(
                bundle=args.bundle,
                database_url=args.database_url,
                approval_token=args.approval_token,
                preflight_file=args.preflight_file,
                expected_inventory=expected_inventory,
                mysql_bin=args.mysql_bin,
                mysql_container=args.mysql_container,
                timeout_seconds=args.timeout_seconds,
            )
            location = args.database_url.split("@", 1)[-1]
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
    except (BackupRestoreError, OSError, ValueError) as exc:
        print(f"backup/restore failed: {exc}", file=sys.stderr)
        return 1
    if args.command == "issue-preflight":
        print(f"{args.command} verified: schema_version={manifest['schema_version']} path={location}")
    elif args.command == "schema-inventory":
        print(f"{args.command} verified: inventory_sha256={manifest['inventory_sha256']} path={location}")
    elif args.command in {"dump-mysql", "restore-mysql", "restore-forward"}:
        print(
            f"{args.command} verified: kind={manifest.get('artifact_kind', 'mysql')} "
            f"content_sha256={manifest.get('content_sha256', 'n/a')} path={location}"
        )
    else:
        print(
            f"{args.command} verified: kind={manifest['artifact_kind']} "
            f"content_sha256={manifest['content_sha256']} path={location}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
