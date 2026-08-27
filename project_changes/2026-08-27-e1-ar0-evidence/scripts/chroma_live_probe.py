from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

BATCH_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BATCH_ROOT.parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
CHROMA_ROOT = (BATCH_ROOT / "artifacts" / "chroma").resolve()
BACKUP_ROOT = (BATCH_ROOT / "artifacts" / "backups").resolve()

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
sys.path.insert(0, str(BACKEND_ROOT))

from langchain_chroma import Chroma  # noqa: E402
from langchain_core.embeddings import Embeddings  # noqa: E402


class DeterministicEmbeddings(Embeddings):
    """Stable local vectors for persistence tests, not a quality substitute."""

    @staticmethod
    def _embed(text: str) -> list[float]:
        raw = hashlib.sha256(text.encode("utf-8")).digest()
        return [((value / 255.0) * 2.0) - 1.0 for value in raw]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def _safe_path(value: str) -> Path:
    path = Path(value).expanduser().resolve(strict=False)
    try:
        path.relative_to(CHROMA_ROOT)
    except ValueError as exc:
        raise ValueError(f"path must remain under E1 Chroma root {CHROMA_ROOT}: {path}") from exc
    if path == CHROMA_ROOT:
        raise ValueError("the E1 Chroma root itself is not a valid scenario target")
    return path


def _safe_backup_path(value: str) -> Path:
    path = Path(value).expanduser().resolve(strict=False)
    try:
        path.relative_to(BACKUP_ROOT)
    except ValueError as exc:
        raise ValueError(f"path must remain under E1 backup root {BACKUP_ROOT}: {path}") from exc
    if path == BACKUP_ROOT:
        raise ValueError("the E1 backup root itself is not a valid bundle")
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def tree_snapshot(path: Path) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    if path.exists():
        for item in sorted(path.rglob("*"), key=lambda candidate: candidate.as_posix()):
            relative = item.relative_to(path).as_posix()
            if item.is_symlink():
                raise ValueError(f"symlink is not allowed in E1 projection: {item}")
            if item.is_file():
                entries.append(
                    {
                        "path": relative,
                        "sha256": _sha256_file(item),
                        "size": item.stat().st_size,
                        "type": "file",
                    }
                )
            elif item.is_dir():
                entries.append({"path": relative, "type": "directory"})
    encoded = json.dumps(entries, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return {
        "entries": entries,
        "entry_count": len(entries),
        "path": str(path),
        "tree_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _store(path: Path, collection_name: str, *, create: bool) -> Chroma:
    return Chroma(
        collection_name=collection_name,
        embedding_function=DeterministicEmbeddings(),
        persist_directory=str(path),
        create_collection_if_not_exists=create,
    )


def seed(path: Path) -> dict[str, object]:
    if path.exists() and any(path.iterdir()):
        raise ValueError(f"seed target must be absent or empty: {path}")
    path.mkdir(parents=True, exist_ok=True)
    rag = _store(path, "rag_collection", create=True)
    notes = _store(path, "notes_collection", create=True)
    rag.add_texts(
        ["alpha document", "beta document", "中文知识"],
        metadatas=[{"source_id": "source-a"}, {"source_id": "source-b"}, {"source_id": "source-c"}],
        ids=["rag-a", "rag-b", "rag-c"],
    )
    notes.add_texts(
        ["isolated note"],
        metadatas=[{"note_id": "note-a"}],
        ids=["note-a"],
    )
    result = verify(path)
    result["operation"] = "seed"
    return result


def verify(path: Path) -> dict[str, object]:
    rag = _store(path, "rag_collection", create=False)
    notes = _store(path, "notes_collection", create=False)
    rag_payload = rag.get(include=["metadatas", "documents"])
    note_payload = notes.get(include=["metadatas", "documents"])
    query = rag.similarity_search_with_relevance_scores("alpha document", k=1)
    collections = {
        "notes_collection": [
            {"document": document, "id": item_id, "metadata": metadata}
            for item_id, document, metadata in zip(
                note_payload["ids"], note_payload["documents"], note_payload["metadatas"], strict=True
            )
        ],
        "rag_collection": [
            {"document": document, "id": item_id, "metadata": metadata}
            for item_id, document, metadata in zip(
                rag_payload["ids"], rag_payload["documents"], rag_payload["metadatas"], strict=True
            )
        ],
    }
    for records in collections.values():
        records.sort(key=lambda record: str(record["id"]))
    ids = sorted(record["id"] for records in collections.values() for record in records)
    canonical_content = json.dumps(
        collections,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {
        "collections": sorted(collections),
        "content_sha256": hashlib.sha256(canonical_content).hexdigest(),
        "counts": {"notes_collection": len(note_payload["ids"]), "rag_collection": len(rag_payload["ids"])},
        "id_sha256": hashlib.sha256("|".join(ids).encode("utf-8")).hexdigest(),
        "ids": ids,
        "operation": "verify",
        "query_document": query[0][0].page_content if query else None,
        "snapshot": tree_snapshot(path),
    }


def copy_projection(source: Path, target: Path) -> dict[str, object]:
    if not source.is_dir():
        raise ValueError(f"copy source is not a directory: {source}")
    if target.exists():
        raise ValueError(f"copy target already exists: {target}")
    shutil.copytree(source, target)
    return {"operation": "copy", "source": tree_snapshot(source), "target": tree_snapshot(target)}


def rebuild_projection(bundle: Path, target: Path, quarantine_root: Path) -> dict[str, object]:
    if target.parent != CHROMA_ROOT or not target.name.startswith("fault-"):
        raise ValueError(f"rebuild target must be a direct fault-* child of {CHROMA_ROOT}: {target}")
    if not target.is_dir():
        raise ValueError(f"rebuild target must be an existing fault directory: {target}")
    if quarantine_root.parent != CHROMA_ROOT or not quarantine_root.name.startswith("quarantine-"):
        raise ValueError(
            f"quarantine root must be a direct quarantine-* child of {CHROMA_ROOT}: {quarantine_root}"
        )
    if quarantine_root.exists():
        raise ValueError(f"quarantine root must not already exist: {quarantine_root}")

    from scripts.backup_restore import rebuild_projection as rebuild_from_bundle

    result = rebuild_from_bundle(bundle=bundle, target=target, quarantine_root=quarantine_root)
    previous = _safe_path(str(result["quarantined_previous"]))
    result["installed_snapshot"] = tree_snapshot(target)
    result["operation"] = "rebuild_projection"
    result["quarantined_snapshot"] = tree_snapshot(previous)
    return result


def delete_collection(path: Path, name: str) -> dict[str, object]:
    import chromadb

    client = chromadb.PersistentClient(path=str(path))
    client.delete_collection(name=name)
    names = sorted(collection.name for collection in client.list_collections())
    return {"collections": names, "operation": "delete_collection", "snapshot": tree_snapshot(path)}


def corrupt_sqlite(path: Path) -> dict[str, object]:
    database = path / "chroma.sqlite3"
    if not database.is_file():
        raise ValueError(f"Chroma database does not exist: {database}")
    with database.open("r+b") as target:
        target.seek(0)
        target.write(b"E1_CORRUPTED_DB!")
        target.flush()
        os.fsync(target.fileno())
    return {"operation": "corrupt_sqlite", "snapshot": tree_snapshot(path)}


def migration_mismatch(path: Path) -> dict[str, object]:
    database = path / "chroma.sqlite3"
    if not database.is_file():
        raise ValueError(f"Chroma database does not exist: {database}")
    connection = sqlite3.connect(database)
    try:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(migrations)")]
        if "hash" not in columns:
            raise ValueError(f"Chroma migrations table has no hash column: {columns}")
        row = connection.execute("SELECT rowid, hash FROM migrations ORDER BY rowid DESC LIMIT 1").fetchone()
        if row is None:
            raise ValueError("Chroma migrations table is empty")
        connection.execute("UPDATE migrations SET hash = ? WHERE rowid = ?", ("0" * 64, row[0]))
        connection.commit()
    finally:
        connection.close()
    return {
        "operation": "migration_mismatch",
        "previous_hash": row[1],
        "replacement_hash": "0" * 64,
        "snapshot": tree_snapshot(path),
    }


def inspect_sqlite(path: Path) -> dict[str, object]:
    database = path / "chroma.sqlite3"
    uri = f"{database.resolve(strict=True).as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        collections = connection.execute("SELECT id, name FROM collections ORDER BY name").fetchall()
        migrations = connection.execute("SELECT dir, version, filename, hash FROM migrations ORDER BY dir, version").fetchall()
    finally:
        connection.close()
    return {
        "collections": collections,
        "migrations": migrations,
        "operation": "inspect_sqlite",
        "tables": tables,
    }


def service_init(path: Path, expected: str, *, include_snapshot: bool = True) -> dict[str, object]:
    from app.core.background_init import init_manager
    from app.rag import vector_store

    init_manager.embed_model = DeterministicEmbeddings()
    vector_store.chroma_config["persist_directory"] = str(path)
    vector_store.chroma_config["md5_hex_store"] = str(BATCH_ROOT / "artifacts" / "md5" / "md5_hex_store.txt")
    vector_store.VectorStoreService._instance = None
    vector_store.VectorStoreService._initialized = False
    vector_store.VectorStoreService._restart_required = False
    vector_store.VectorStoreService._projection_health = vector_store.ChromaProjectionHealth(
        status="not_initialized",
        persist_directory=None,
        checked_at=None,
    )
    error: dict[str, str] | None = None
    try:
        vector_store.VectorStoreService()
    except Exception as exc:  # The structured result is the evidence surface.
        error = {"message": str(exc), "type": type(exc).__name__}
    health = vector_store.VectorStoreService.projection_health()
    outcome = "ready" if health["status"] == "ready" and error is None else "quarantined"
    result = {
        "error": error,
        "expected": expected,
        "health": health,
        "operation": "service_init",
        "outcome": outcome,
        "snapshot": tree_snapshot(path) if include_snapshot else None,
    }
    if outcome != expected:
        raise RuntimeError(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def api_degraded(path: Path) -> dict[str, object]:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.background_init import _BackgroundInitManager
    from app.rag import vector_store
    from app.router import health as health_module
    from app.router import note_router as note_module

    async def dependency_ready() -> bool:
        return True

    health_module.check_mysql_connection = dependency_ready
    health_module.check_redis_connection = dependency_ready
    health_module.skill_package_storage.check_health = lambda: True

    vector_store.VectorStoreService._projection_health = vector_store.ChromaProjectionHealth(
        status="quarantined",
        persist_directory=str(path),
        checked_at="e1-live-probe",
        error_type="E1InjectedFailure",
        error_message="isolated projection failure",
    )
    manager = _BackgroundInitManager()
    manager._started = True
    manager.note_service_error = "isolated projection failure"
    manager.note_service_init_done.set()
    note_module.init_manager = manager

    app = FastAPI()
    app.include_router(health_module.health_router)
    app.include_router(note_module.note_router)
    with TestClient(app) as client:
        health_response = client.get("/health/ready")
        note_response = client.get("/note/list")
    return {
        "health_body": health_response.json(),
        "health_status": health_response.status_code,
        "note_body": note_response.json(),
        "note_status": note_response.status_code,
        "operation": "api_degraded",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="E1-only live Chroma persistence and containment probe.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in (
        "seed",
        "verify",
        "snapshot",
        "api-degraded",
        "corrupt-sqlite",
        "migration-mismatch",
        "inspect-sqlite",
    ):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--path", required=True)
    copy_parser = subparsers.add_parser("copy")
    copy_parser.add_argument("--source", required=True)
    copy_parser.add_argument("--target", required=True)
    rebuild_parser = subparsers.add_parser("rebuild")
    rebuild_parser.add_argument("--bundle", required=True)
    rebuild_parser.add_argument("--path", required=True)
    rebuild_parser.add_argument("--quarantine-root", required=True)
    delete_parser = subparsers.add_parser("delete-collection")
    delete_parser.add_argument("--path", required=True)
    delete_parser.add_argument("--name", required=True)
    init_parser = subparsers.add_parser("service-init")
    init_parser.add_argument("--path", required=True)
    init_parser.add_argument("--expect", required=True, choices=("ready", "quarantined"))
    init_parser.add_argument("--skip-snapshot", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "seed":
            result = seed(_safe_path(args.path))
        elif args.command == "verify":
            result = verify(_safe_path(args.path))
        elif args.command == "snapshot":
            result = tree_snapshot(_safe_path(args.path))
        elif args.command == "copy":
            result = copy_projection(_safe_path(args.source), _safe_path(args.target))
        elif args.command == "rebuild":
            result = rebuild_projection(
                _safe_backup_path(args.bundle),
                _safe_path(args.path),
                _safe_path(args.quarantine_root),
            )
        elif args.command == "delete-collection":
            result = delete_collection(_safe_path(args.path), args.name)
        elif args.command == "corrupt-sqlite":
            result = corrupt_sqlite(_safe_path(args.path))
        elif args.command == "migration-mismatch":
            result = migration_mismatch(_safe_path(args.path))
        elif args.command == "inspect-sqlite":
            result = inspect_sqlite(_safe_path(args.path))
        elif args.command == "service-init":
            result = service_init(
                _safe_path(args.path),
                args.expect,
                include_snapshot=not args.skip_snapshot,
            )
        else:
            result = api_degraded(_safe_path(args.path))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
