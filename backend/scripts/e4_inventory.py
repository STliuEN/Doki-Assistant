"""Offline, read-only E4 source inventory.

This module deliberately uses only the Python standard library.  It does not
load application settings, read ``.env`` files, create a Chroma client, open a
network socket, or mutate any source resource.  The only write performed by
the CLI is the explicitly requested JSON evidence file.

The inventory is an evidence surface, not a migration input.  File paths and
metadata values are represented by stable SHA-256 tokens so that a manifest
can be retained without publishing user identifiers, filenames, temporary
paths, or document contents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import stat
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = BACKEND_ROOT / "data"
SCHEMA_VERSION = 1
BUFFER_SIZE = 1024 * 1024
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_MD5 = re.compile(r"^[0-9a-fA-F]{32}$")
_SENSITIVE_NAME = re.compile(r"(?:^|[.])env(?:$|[.])", re.IGNORECASE)


class InventoryError(RuntimeError):
    """Raised when a local inventory cannot be collected safely."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(BUFFER_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_root(path: str | os.PathLike[str] | Path) -> Path:
    """Normalize a caller path lexically, without following symlinks."""

    value = Path(path)
    if "~" in value.parts:
        raise InventoryError("home-directory expansion is not allowed; pass an explicit path")
    # ``resolve`` follows a symlink and would make a linked root look like a
    # regular directory before ``_is_reparse_or_symlink`` can reject it.
    return value.absolute()


def _is_reparse_or_symlink(path: Path) -> bool:
    """Reject symlinks and Windows junction/reparse points before traversal."""

    if path.is_symlink() or os.path.islink(path):
        return True
    try:
        attributes = path.stat(follow_symlinks=False).st_file_attributes
    except (AttributeError, OSError):
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _path_token(relative: str) -> str:
    return _sha256_text(relative)


def _safe_relative(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise InventoryError("source entry escaped its inventory root") from exc
    if not relative or relative == "." or relative.startswith("../") or "/../" in relative:
        raise InventoryError("source entry has an unsafe relative path")
    return relative


def _entry_error(code: str, path: str | None = None, *, detail_type: str | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code}
    if path is not None:
        error["path_token"] = _path_token(path)
    if detail_type is not None:
        error["type"] = detail_type
    return error


def _should_skip(relative: str) -> bool:
    """Never inspect environment files, even if a caller points at a broad root."""

    return any(_SENSITIVE_NAME.search(part) for part in PurePosixPath(relative).parts)


def _walk_entries(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entries: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    if not root.exists():
        return entries, [_entry_error("root_missing")]
    if _is_reparse_or_symlink(root):
        return entries, [_entry_error("root_link")]
    if _should_skip(root.name):
        return entries, [_entry_error("sensitive_path_skipped", root.name)]
    if not root.is_dir():
        return entries, [_entry_error("root_not_directory")]

    # os.walk with followlinks=False still needs an explicit reparse check:
    # Windows junctions are directory-like and can otherwise escape the root.
    for current_root, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_root)
        try:
            relative_current = _safe_relative(current, root) if current != root else ""
        except InventoryError:
            issues.append(_entry_error("directory_escape"))
            directory_names[:] = []
            continue
        for name in sorted(directory_names):
            candidate = current / name
            relative = f"{relative_current}/{name}" if relative_current else name
            if _should_skip(relative):
                directory_names.remove(name)
                issues.append(_entry_error("sensitive_path_skipped", relative))
                continue
            if _is_reparse_or_symlink(candidate):
                directory_names.remove(name)
                issues.append(_entry_error("link_rejected", relative))
                continue
            entries.append({"path_token": _path_token(relative), "type": "directory"})
        for name in sorted(file_names):
            candidate = current / name
            relative = f"{relative_current}/{name}" if relative_current else name
            if _should_skip(relative):
                issues.append(_entry_error("sensitive_path_skipped", relative))
                continue
            if _is_reparse_or_symlink(candidate):
                issues.append(_entry_error("link_rejected", relative))
                continue
            if not candidate.is_file():
                issues.append(_entry_error("non_regular_file", relative))
                continue
            try:
                size = candidate.stat().st_size
                digest = _sha256_file(candidate)
            except (OSError, ValueError) as exc:
                issues.append(_entry_error("file_read_error", relative, detail_type=type(exc).__name__))
                continue
            entries.append(
                {
                    "path_token": _path_token(relative),
                    "type": "file",
                    "size": size,
                    "sha256": digest,
                    "suffix": candidate.suffix.lower() or None,
                }
            )
    entries.sort(key=lambda item: (str(item["path_token"]), str(item["type"])))
    return entries, issues


def inventory_tree(root: str | os.PathLike[str] | Path, *, label: str) -> dict[str, Any]:
    """Return a redacted deterministic tree manifest for one local root."""

    resolved = _normalise_root(root)
    entries, issues = _walk_entries(resolved)
    files = [entry for entry in entries if entry["type"] == "file"]
    directories = [entry for entry in entries if entry["type"] == "directory"]
    content = {
        "entries": entries,
        "label": label,
        "schema_version": SCHEMA_VERSION,
    }
    return {
        "label": label,
        "root_present": resolved.is_dir() and not _is_reparse_or_symlink(resolved),
        "entry_count": len(entries),
        "file_count": len(files),
        "directory_count": len(directories),
        "total_bytes": sum(int(entry.get("size", 0)) for entry in files),
        "tree_sha256": _sha256_bytes(_canonical_json(content)),
        "entries": entries,
        "issues": issues,
    }


def _sqlite_uri(path: Path) -> str:
    return f"{path.resolve(strict=True).as_uri()}?mode=ro&immutable=1"


def _collection_class(name: str) -> str:
    if name == "rag_collection":
        return "rag_global"
    if name == "notes_collection":
        return "notes_global"
    if name.startswith("rag_"):
        return "rag_scoped"
    if name.startswith("notes_"):
        return "notes_scoped"
    return "other"


def _chroma_metadata_values(connection: sqlite3.Connection) -> dict[str, dict[str, list[dict[str, str]]]]:
    """Collect only scope-like metadata, replacing values with tokens."""

    result: dict[str, dict[str, list[dict[str, str]]]] = {}
    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        if isinstance(row[0], str)
    }
    queries: list[str] = []
    if "segment_metadata" in tables:
        queries.append("SELECT segment_id, key, str_value FROM segment_metadata")
    if "embedding_metadata" in tables and "embeddings" in tables:
        # Embedding metadata is keyed by the integer embedding id.  Join it
        # back to the segment before redacting the identifier, otherwise
        # metadata would be attributed to the wrong collection.
        queries.append(
            "SELECT embeddings.segment_id, embedding_metadata.key, embedding_metadata.string_value "
            "FROM embedding_metadata JOIN embeddings ON embeddings.id = embedding_metadata.id"
        )
    if "embedding_metadata_array" in tables and "embeddings" in tables:
        queries.append(
            "SELECT embeddings.segment_id, embedding_metadata_array.key, embedding_metadata_array.string_value "
            "FROM embedding_metadata_array JOIN embeddings ON embeddings.id = embedding_metadata_array.id"
        )
    wanted = {"user_id", "userid", "user", "owner_id", "source", "source_id", "path", "file_path", "filename"}
    for query in queries:
        for row in connection.execute(query):
            key = str(row[1]).strip().lower()
            if key not in wanted:
                continue
            value = row[2]
            if value is None:
                continue
            raw_value = str(value)
            token = _sha256_text(raw_value)
            segment_token = _sha256_text(str(row[0]))
            result.setdefault(segment_token, {}).setdefault(key, []).append({"raw": raw_value, "token": token})
    for values in result.values():
        for key in values:
            unique = {(item["raw"], item["token"]) for item in values[key]}
            values[key] = [
                {"raw": raw, "token": token}
                for raw, token in sorted(unique, key=lambda item: (item[1], item[0]))
            ]
    return result


def inventory_chroma(root: str | os.PathLike[str] | Path, *, label: str = "chroma") -> dict[str, Any]:
    """Inspect a local Chroma SQLite projection without opening Chroma itself."""

    resolved = _normalise_root(root)
    tree = inventory_tree(resolved, label=label)
    result: dict[str, Any] = {
        "label": label,
        "tree": tree,
        "collection_count": 0,
        "embedding_count": 0,
        "collections": [],
        "metadata_sha256": _sha256_text(""),
        "issues": list(tree["issues"]),
    }
    database = resolved / "chroma.sqlite3"
    if not database.is_file() or _is_reparse_or_symlink(database):
        result["issues"].append(_entry_error("chroma_database_missing"))
        return result
    try:
        connection = sqlite3.connect(_sqlite_uri(database), uri=True)
        connection.row_factory = sqlite3.Row
    except (OSError, sqlite3.Error) as exc:
        result["issues"].append(_entry_error("chroma_read_error", detail_type=type(exc).__name__))
        return result
    try:
        table_names = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if row[0] is not None
        }
        required = {"collections", "embeddings"}
        missing = sorted(required - table_names)
        if missing:
            result["issues"].append({"code": "chroma_tables_missing", "tables": missing})
            return result
        collections = list(connection.execute("SELECT id, name, dimension FROM collections ORDER BY name"))
        metadata_by_segment = _chroma_metadata_values(connection)
        collection_records: list[dict[str, Any]] = []
        metadata_digest_rows: list[dict[str, Any]] = []
        for collection in collections:
            collection_id = str(collection["id"])
            collection_name = str(collection["name"])
            segment_ids: list[str] = []
            if "segments" in table_names:
                segment_ids = [str(row[0]) for row in connection.execute("SELECT id FROM segments WHERE collection = ?", (collection_id,))]
            embedding_count = 0
            if segment_ids:
                placeholders = ",".join("?" for _ in segment_ids)
                embedding_count = int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM embeddings WHERE segment_id IN ({placeholders})", segment_ids
                    ).fetchone()[0]
                )
            else:
                embedding_count = int(
                    connection.execute("SELECT COUNT(*) FROM embeddings WHERE segment_id = ?", (collection_id,)).fetchone()[0]
                )
            scope_values: Counter[str] = Counter()
            raw_scope_values: set[str] = set()
            related_metadata: list[dict[str, Any]] = []
            for segment_id in segment_ids:
                segment_token = _sha256_text(segment_id)
                values = metadata_by_segment.get(segment_token, {})
                for key, tokens in values.items():
                    value_tokens = sorted({item["token"] for item in tokens})
                    related_metadata.append({"key": key, "value_tokens": value_tokens, "count": len(value_tokens)})
                    if key in {"user_id", "userid", "user", "owner_id"}:
                        scope_values.update(value_tokens)
                        raw_scope_values.update(item["raw"] for item in tokens)
            related_metadata.sort(key=lambda item: (item["key"], item["value_tokens"]))
            collection_record = {
                "name_class": _collection_class(collection_name),
                "name_token": _sha256_text(collection_name),
                "dimension": collection["dimension"],
                "segment_count": len(segment_ids),
                "embedding_count": embedding_count,
                "scope_value_tokens": sorted(scope_values),
                "metadata": related_metadata,
            }
            collection_records.append(collection_record)
            metadata_digest_rows.append(collection_record)
            # A scoped collection suffix is only a candidate scope.  If its
            # raw suffix and metadata user IDs disagree, retain a redacted
            # conflict marker and leave identity resolution to E4 mapping.
            if _collection_class(collection_name) in {"rag_scoped", "notes_scoped"} and scope_values:
                suffix = collection_name.split("_", 1)[1]
                if suffix != "collection" and any(raw != suffix for raw in raw_scope_values):
                    result["issues"].append(
                        {
                            "code": "scope_conflict",
                            "collection_name_token": _sha256_text(collection_name),
                            "metadata_value_count": sum(scope_values.values()),
                        }
                    )
        result["collections"] = collection_records
        result["collection_count"] = len(collection_records)
        result["embedding_count"] = sum(int(record["embedding_count"]) for record in collection_records)
        result["metadata_sha256"] = _sha256_bytes(_canonical_json(metadata_digest_rows))
    except (OSError, sqlite3.Error, ValueError) as exc:
        result["issues"].append(_entry_error("chroma_query_error", detail_type=type(exc).__name__))
    finally:
        connection.close()
    return result


def _parse_md5_file(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    records = 0
    valid_json = 0
    valid_md5 = 0
    md5_values: list[str] = []
    issues: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                value = line.strip()
                if not value:
                    continue
                records += 1
                candidate: Any = value
                if value.startswith("{"):
                    try:
                        candidate = json.loads(value)
                        valid_json += 1
                    except json.JSONDecodeError:
                        issues.append({"code": "invalid_json_record", "line": line_number})
                md5_value = candidate.get("md5") if isinstance(candidate, Mapping) else candidate
                if isinstance(md5_value, str) and _MD5.fullmatch(md5_value):
                    valid_md5 += 1
                    md5_values.append(md5_value.lower())
                else:
                    issues.append({"code": "invalid_md5_record", "line": line_number})
    except (OSError, UnicodeError) as exc:
        issues.append(_entry_error("md5_read_error", detail_type=type(exc).__name__))
    md5_values.sort()
    return (
        {
            "record_count": records,
            "valid_json_count": valid_json,
            "valid_md5_count": valid_md5,
            "md5_values_sha256": _sha256_bytes(_canonical_json(md5_values)),
        },
        issues,
    )


def inventory_md5(root: str | os.PathLike[str] | Path, *, label: str = "md5") -> dict[str, Any]:
    resolved = _normalise_root(root)
    tree = inventory_tree(resolved, label=label)
    files: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = list(tree["issues"])
    if resolved.is_dir() and not _is_reparse_or_symlink(resolved):
        for current_root, _directory_names, file_names in os.walk(resolved, followlinks=False):
            current = Path(current_root)
            for name in sorted(file_names):
                path = current / name
                if _is_reparse_or_symlink(path):
                    continue
                relative = _safe_relative(path, resolved)
                if _should_skip(relative):
                    continue
                if path.name.lower() != "md5_hex_store.txt":
                    continue
                summary, parse_issues = _parse_md5_file(path)
                issues.extend({**issue, "path_token": _path_token(relative)} for issue in parse_issues)
                files.append(
                    {
                        "path_token": _path_token(relative),
                        "size": path.stat().st_size,
                        "sha256": _sha256_file(path),
                        **summary,
                    }
                )
    files.sort(key=lambda item: item["path_token"])
    result = {
        "label": label,
        "tree": tree,
        "file_count": len(files),
        "record_count": sum(int(item["record_count"]) for item in files),
        "md5_count": sum(int(item["valid_md5_count"]) for item in files),
        "files": files,
        "content_sha256": _sha256_bytes(_canonical_json(files)),
        "issues": issues,
    }
    return result


def inventory_skill_storage(root: str | os.PathLike[str] | Path, *, label: str = "skill_storage") -> dict[str, Any]:
    resolved = _normalise_root(root)
    tree = inventory_tree(resolved, label=label)
    objects: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = list(tree["issues"])
    objects_root = resolved / "objects"
    if objects_root.is_dir() and not _is_reparse_or_symlink(objects_root):
        for current_root, _directory_names, file_names in os.walk(objects_root, followlinks=False):
            current = Path(current_root)
            for name in sorted(file_names):
                path = current / name
                if _is_reparse_or_symlink(path):
                    issues.append(_entry_error("link_rejected", _safe_relative(path, resolved)))
                    continue
                relative = _safe_relative(path, resolved)
                if _should_skip(relative):
                    continue
                digest = _sha256_file(path)
                key_digest = Path(name).stem.lower() if name.lower().endswith(".zip") else ""
                key_prefix = path.parent.name.lower()
                valid_key = bool(_HEX64.fullmatch(key_digest))
                record = {
                    "path_token": _path_token(relative),
                    "size": path.stat().st_size,
                    "sha256": digest,
                    "artifact_kind": "zip" if name.lower().endswith(".zip") else "file",
                    "key_digest": key_digest if valid_key else None,
                    # Skill storage keys identify the normalized package
                    # digest, while ``sha256`` identifies archive bytes.  Do
                    # not compare these different digest domains.
                    "key_digest_semantics": "normalized-package" if valid_key else None,
                    "key_prefix_matches": bool(valid_key and key_prefix == key_digest[:2]),
                }
                if name.lower().endswith(".zip") and not valid_key:
                    issues.append({"code": "object_key_invalid", "path_token": record["path_token"]})
                elif valid_key and not record["key_prefix_matches"]:
                    issues.append({"code": "object_key_prefix_mismatch", "path_token": record["path_token"]})
                objects.append(record)
    objects.sort(key=lambda item: item["path_token"])
    return {
        "label": label,
        "tree": tree,
        "object_count": len(objects),
        "object_bytes": sum(int(item["size"]) for item in objects),
        "objects": objects,
        "objects_sha256": _sha256_bytes(_canonical_json(objects)),
        "issues": issues,
    }


def _aggregate_counts(sources: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    return {
        "file_count": sum(int(source.get("file_count", source.get("tree", {}).get("file_count", 0))) for source in sources.values()),
        "chroma_collections": int(sources.get("chroma", {}).get("collection_count", 0)),
        "chroma_embeddings": int(sources.get("chroma", {}).get("embedding_count", 0)),
        "md5_records": int(sources.get("md5", {}).get("record_count", 0)),
        "md5_values": int(sources.get("md5", {}).get("md5_count", 0)),
        "skill_objects": int(sources.get("skill_storage", {}).get("object_count", 0)),
    }


def build_manifest(
    *,
    chroma_root: str | os.PathLike[str] | Path,
    md5_root: str | os.PathLike[str] | Path,
    images_root: str | os.PathLike[str] | Path,
    skill_root: str | os.PathLike[str] | Path,
    captured_at: datetime | None = None,
) -> dict[str, Any]:
    """Build one redacted local manifest; all source reads are synchronous and read-only."""

    sources: dict[str, dict[str, Any]] = {
        "chroma": inventory_chroma(chroma_root),
        "md5": inventory_md5(md5_root),
        "images": inventory_tree(images_root, label="images"),
        "skill_storage": inventory_skill_storage(skill_root),
    }
    issues: list[dict[str, Any]] = []
    for source_name, source in sources.items():
        for issue in source.get("issues", []):
            issues.append({"source": source_name, **issue})
    manifest: dict[str, Any] = {
        "artifact_kind": "e4-local-inventory",
        "schema_version": SCHEMA_VERSION,
        "tool": "e4_inventory",
        "captured_at": (captured_at or datetime.now(UTC)).astimezone(UTC).isoformat(),
        "capture_mode": "offline-read-only",
        "read_only_contract": {
            "database_connections": False,
            "network_connections": False,
            "environment_files_read": False,
            "business_resource_writes": False,
            "chroma_client_created": False,
            "redis_access": False,
        },
        "sources": sources,
        "counts": _aggregate_counts(sources),
        "issues": issues,
    }
    digest_input = {key: value for key, value in manifest.items() if key != "captured_at"}
    manifest["manifest_sha256"] = _sha256_bytes(_canonical_json(digest_input))
    return manifest


def _assert_output_outside_sources(output: Path, source_roots: Iterable[Path]) -> None:
    output_resolved = output.resolve(strict=False)
    for root in source_roots:
        root_resolved = root.resolve(strict=False)
        try:
            output_resolved.relative_to(root_resolved)
        except ValueError:
            continue
        raise InventoryError("manifest output must be outside every source root")


def write_manifest(manifest: Mapping[str, Any], output: str | os.PathLike[str] | Path, *, source_roots: Iterable[Path] = ()) -> Path:
    destination = _normalise_root(output)
    _assert_output_outside_sources(destination, source_roots)
    if destination.exists() or destination.is_symlink():
        raise InventoryError(f"manifest output already exists: {destination.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, staging_name = tempfile.mkstemp(prefix=f".{destination.name}-", suffix=".tmp", dir=destination.parent)
    os.close(descriptor)
    staging = Path(staging_name)
    try:
        staging.write_text(
            json.dumps(dict(manifest), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        staging.replace(destination)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise
    return destination


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a redacted, offline-only E4 local inventory manifest.")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--chroma-root", type=Path)
    parser.add_argument("--md5-root", type=Path)
    parser.add_argument("--images-root", type=Path)
    parser.add_argument("--skill-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    data_root = _normalise_root(args.data_root)
    roots = {
        "chroma": args.chroma_root or data_root / "chromadb",
        "md5": args.md5_root or data_root / "md5_hex_store",
        "images": args.images_root or data_root / "extracted_images",
        "skill": args.skill_root or data_root / "skill_packages",
    }
    try:
        manifest = build_manifest(
            chroma_root=roots["chroma"],
            md5_root=roots["md5"],
            images_root=roots["images"],
            skill_root=roots["skill"],
        )
        destination = write_manifest(manifest, args.output, source_roots=roots.values())
    except (InventoryError, OSError, sqlite3.Error, ValueError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {
                "output": str(destination),
                "manifest_sha256": manifest["manifest_sha256"],
                "issues": len(manifest["issues"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
