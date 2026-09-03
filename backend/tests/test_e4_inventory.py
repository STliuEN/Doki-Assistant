from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.e4_inventory import InventoryError, build_manifest, inventory_chroma, inventory_tree, write_manifest


def _build_chroma_fixture(root: Path) -> None:
    root.mkdir(parents=True)
    connection = sqlite3.connect(root / "chroma.sqlite3")
    try:
        connection.executescript(
            """
            CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT NOT NULL, dimension INTEGER);
            CREATE TABLE segments (id TEXT PRIMARY KEY, type TEXT NOT NULL, scope TEXT NOT NULL, collection TEXT NOT NULL);
            CREATE TABLE embeddings (id INTEGER PRIMARY KEY, segment_id TEXT NOT NULL, embedding_id TEXT NOT NULL);
            CREATE TABLE embedding_metadata (id INTEGER NOT NULL, key TEXT NOT NULL, string_value TEXT);
            INSERT INTO collections VALUES ('global-id', 'rag_collection', 1024);
            INSERT INTO collections VALUES ('scoped-id', 'rag_legacy-scope', 1024);
            INSERT INTO segments VALUES ('global-segment', 'vector', 'VECTOR', 'global-id');
            INSERT INTO segments VALUES ('scoped-segment', 'vector', 'VECTOR', 'scoped-id');
            INSERT INTO embeddings VALUES (1, 'global-segment', 'embedding-global');
            INSERT INTO embeddings VALUES (2, 'scoped-segment', 'embedding-scoped');
            INSERT INTO embedding_metadata VALUES (1, 'source', 'private-document.pdf');
            INSERT INTO embedding_metadata VALUES (1, 'user_id', 'legacy-user-123');
            INSERT INTO embedding_metadata VALUES (2, 'user_id', 'different-legacy-user');
            """
        )
        connection.commit()
    finally:
        connection.close()


def _build_source_fixture(tmp_path: Path) -> dict[str, Path]:
    data = tmp_path / "data"
    chroma = data / "chromadb"
    md5 = data / "md5_hex_store" / "user-legacy"
    images = data / "extracted_images" / "user-legacy" / "0123456789abcdef0123456789abcdef"
    skills = data / "skill_packages" / "objects" / "ab"
    _build_chroma_fixture(chroma)
    md5.mkdir(parents=True)
    (md5 / "md5_hex_store.txt").write_text(
        json.dumps(
            {
                "md5": "0123456789abcdef0123456789abcdef",
                "filename": "private-document.pdf",
                "original_filename": "private-document.pdf",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (md5 / ".env").write_text("SECRET=must-not-be-read\n", encoding="utf-8")
    images.mkdir(parents=True)
    (images / "page-1.png").write_bytes(b"image-bytes")
    skills.mkdir(parents=True)
    digest = "ab" + "1" * 62
    (skills / f"{digest}.zip").write_bytes(b"normalized-skill-archive")
    return {"chroma": chroma, "md5": data / "md5_hex_store", "images": data / "extracted_images", "skills": data / "skill_packages"}


def test_manifest_is_redacted_stable_and_counts_all_local_sources(tmp_path: Path) -> None:
    roots = _build_source_fixture(tmp_path)
    captured_at = datetime(2026, 9, 2, tzinfo=UTC)
    first = build_manifest(
        chroma_root=roots["chroma"],
        md5_root=roots["md5"],
        images_root=roots["images"],
        skill_root=roots["skills"],
        captured_at=captured_at,
    )
    second = build_manifest(
        chroma_root=roots["chroma"],
        md5_root=roots["md5"],
        images_root=roots["images"],
        skill_root=roots["skills"],
        captured_at=captured_at,
    )

    assert first == second
    assert first["manifest_sha256"] and len(first["manifest_sha256"]) == 64
    assert first["counts"] == {
        "file_count": 4,
        "chroma_collections": 2,
        "chroma_embeddings": 2,
        "md5_records": 1,
        "md5_values": 1,
        "skill_objects": 1,
    }
    assert first["read_only_contract"] == {
        "business_resource_writes": False,
        "chroma_client_created": False,
        "database_connections": False,
        "environment_files_read": False,
        "network_connections": False,
        "redis_access": False,
    }
    rendered = json.dumps(first, ensure_ascii=False, sort_keys=True)
    for private_value in ("legacy-user-123", "different-legacy-user", "private-document.pdf", "must-not-be-read"):
        assert private_value not in rendered
    issue_codes = {issue["code"] for issue in first["issues"]}
    assert "sensitive_path_skipped" in issue_codes
    assert "scope_conflict" in issue_codes


def test_chroma_inventory_uses_read_only_sqlite_and_reports_scope_conflict(tmp_path: Path) -> None:
    root = tmp_path / "chroma"
    _build_chroma_fixture(root)
    before = (root / "chroma.sqlite3").read_bytes()
    result = inventory_chroma(root)
    after = (root / "chroma.sqlite3").read_bytes()

    assert result["collection_count"] == 2
    assert result["embedding_count"] == 2
    assert any(issue["code"] == "scope_conflict" for issue in result["issues"])
    assert before == after


def test_tree_rejects_links_and_skips_environment_files(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    (root / ".env").write_text("TOKEN=private\n", encoding="utf-8")
    (root / "safe.txt").write_text("safe\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    linked = root / "linked.txt"
    try:
        linked.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")

    result = inventory_tree(root, label="fixture")
    assert result["file_count"] == 1
    issue_codes = {issue["code"] for issue in result["issues"]}
    assert {"sensitive_path_skipped", "link_rejected"} <= issue_codes


def test_manifest_output_cannot_overwrite_or_land_under_source(tmp_path: Path) -> None:
    roots = _build_source_fixture(tmp_path)
    manifest = build_manifest(
        chroma_root=roots["chroma"],
        md5_root=roots["md5"],
        images_root=roots["images"],
        skill_root=roots["skills"],
        captured_at=datetime(2026, 9, 2, tzinfo=UTC),
    )
    with pytest.raises(InventoryError, match="outside"):
        write_manifest(manifest, roots["chroma"] / "manifest.json", source_roots=roots.values())
    output = tmp_path / "manifest.json"
    write_manifest(manifest, output, source_roots=roots.values())
    with pytest.raises(InventoryError, match="already exists"):
        write_manifest(manifest, output, source_roots=roots.values())
