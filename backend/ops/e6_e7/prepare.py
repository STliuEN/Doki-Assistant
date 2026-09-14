"""Read-only E6/E7 preparation against the exact, already authorized E5 target.

Writes only task evidence. No application startup, model calls, grants, migration,
server read-only changes, container changes, or source-file mutation.
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
from ops.e5.verify_closure import inventory, prepare, protected_state, sha_file  # noqa: E402 - standalone CLI bootstrap

E5 = ROOT / "project_changes/2026-09-10-e5-ar4-rag-projection/artifacts"
TABLES = (
    "skills",
    "skill_versions",
    "skill_installations",
    "skill_aliases",
    "skill_packages",
    "skill_package_uploads",
    "skill_imports",
    "skill_capability_grants",
    "skill_run_bindings",
    "authorization_grants",
    "media_assets",
    "knowledge_source_documents",
    "notes",
    "chat_sessions",
    "chat_messages",
    "migration_maps",
    "audit_events",
)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def seal_input(directory, baseline_archive=None):
    index = json.loads((E5 / "evidence-index.json").read_text("utf-8"))
    snapshot = directory / "e5-sealed-inputs.zip"
    if snapshot.exists():
        raise ValueError("Use a new preparation directory; preserve earlier evidence")
    items = index["current_files"] + index["artifacts"]
    if baseline_archive is not None:
        # Explicit historical verification for subsequent stages; never rewrite the E5 index.
        with zipfile.ZipFile(baseline_archive) as archive:
            if hashlib.sha256(archive.read("e5-evidence-index.json")).hexdigest() != sha_file(E5 / "evidence-index.json"):
                raise ValueError("Archive is not bound to the sealed E5 index")
            for row in items:
                if hashlib.sha256(archive.read(row["path"])).hexdigest() != row["sha256"]:
                    raise ValueError("Archived E5 baseline drift: " + row["path"])
        with snapshot.open("xb") as destination, baseline_archive.open("rb") as source:
            import shutil

            shutil.copyfileobj(source, destination)
        return {
            "path": snapshot.relative_to(ROOT).as_posix(),
            "sha256": sha_file(snapshot),
            "files": len(items),
            "e5_index_sha256": sha_file(E5 / "evidence-index.json"),
            "verified_before_preparation": True,
            "verification_source": "explicit immutable baseline archive; current working tree may have later changes",
        }
    with zipfile.ZipFile(snapshot, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for row in items:
            path = ROOT / row["path"]
            if sha_file(path) != row["sha256"]:
                raise ValueError("E5 sealed input drift: " + row["path"])
            archive.write(path, row["path"])
        archive.write(E5 / "evidence-index.json", "e5-evidence-index.json")
    return {
        "path": snapshot.relative_to(ROOT).as_posix(),
        "sha256": sha_file(snapshot),
        "files": len(items),
        "e5_index_sha256": sha_file(E5 / "evidence-index.json"),
        "verified_before_preparation": True,
    }


def scan(root):
    rows = []
    if not root.exists():
        return rows
    if root.is_symlink() or root.is_junction():
        raise ValueError("Input root is a link: " + root.name)
    for base, directories, files in os.walk(root, followlinks=False):
        for name in list(directories):
            path = Path(base) / name
            if path.is_symlink() or path.is_junction():
                raise ValueError("Input directory is a link")
        for name in sorted(files):
            path = Path(base) / name
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("Input file escapes declared root")
            rows.append({"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": sha_file(path)})
    return sorted(rows, key=lambda row: row["path"])


async def run(directory, output, baseline_archive=None):
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError("Do not overwrite preparation evidence")
    sealed = seal_input(directory, baseline_archive)
    url = prepare()
    from sqlalchemy import event, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.skills.package import parse_skill_zip
    from app.skills.storage import package_digest

    engine = create_async_engine(url, pool_size=1, max_overflow=0, hide_parameters=True)

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def read_only(_conn, _cursor, statement, *_args):
        if not statement.lstrip().upper().startswith(("SELECT ", "SHOW ")):
            raise RuntimeError("Preparation connections are SELECT/SHOW only")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    report = {"stage": "E6+E7", "phase": "preparation", "recorded_at": datetime.now(UTC).isoformat(), "e5_baseline": sealed}
    protected_before = protected_state()
    try:
        before = await inventory(factory)
        async with factory() as db:
            report["table_counts"] = {table: await db.scalar(text("SELECT COUNT(*) FROM `" + table + "`")) for table in TABLES}
            versions = [
                dict(row)
                for row in (
                    await db.execute(text("SELECT id,skill_id,version_number,package_digest,storage_key,status FROM skill_versions ORDER BY id"))
                ).mappings()
            ]
            report["installation_status"] = [
                dict(row) for row in (await db.execute(text("SELECT status,COUNT(*) AS n FROM skill_installations GROUP BY status"))).mappings()
            ]
            report["role_counts"] = [
                dict(row)
                for row in (
                    await db.execute(
                        text("SELECT r.name,b.status,COUNT(*) AS n FROM role_bindings b JOIN roles r ON r.id=b.role_id GROUP BY r.name,b.status")
                    )
                ).mappings()
            ]
        input_roots = {
            "skill_objects": ROOT / "backend/data/skill_packages/objects",
            "knowledge_images": ROOT / "backend/data/extracted_images",
            "md5_sidecars": ROOT / "backend/data/md5_hex_store",
            "seed_inputs": ROOT / "backend/app/skills/seed_packages",
        }
        manifests = {key: scan(root) for key, root in input_roots.items()}
        report["input_inventory"] = {
            key: {
                "root": input_roots[key].relative_to(ROOT).as_posix(),
                "files": len(rows),
                "bytes": sum(row["bytes"] for row in rows),
                "manifest_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
                "disposition": "retain; migrate only after reconciliation",
            }
            for key, rows in manifests.items()
        }
        receipt_rows = []
        for version in versions:
            key = version["storage_key"]
            row = {"version_id": version["id"], "skill_id": version["skill_id"], "package_digest": version["package_digest"]}
            if not re.fullmatch(r"objects/[0-9a-f]{2}/[0-9a-f]{64}\.zip", key):
                row["status"] = "invalid_storage_key"
            else:
                path = ROOT / "backend/data/skill_packages" / key
                if not path.is_file():
                    row["status"] = "missing_package"
                elif path.stat().st_size > 64 * 1024 * 1024:
                    row["status"] = "oversize_package"
                else:
                    try:
                        package = parse_skill_zip(path.read_bytes())
                        row["status"] = "verified" if package_digest(package) == version["package_digest"] else "digest_mismatch"
                        row["archive_sha256"] = sha_file(path)
                        row["resource_count"] = len(package.resource_manifest)
                    except Exception as error:
                        row["status"] = getattr(error, "code", type(error).__name__)
            receipt_rows.append(row)
        report["legacy_package_receipts"] = receipt_rows
        after = await inventory(factory)
        report["sql_inventory_unchanged"] = before == after
        report["new_api"] = protected_state()
        report["new_api_unchanged"] = protected_before == report["new_api"]
        report["global_read_only_flags_observed"] = after["global_flags_observed"]
        report["rag_states"] = [{key: row[key] for key in ("user_id", "status", "revision", "query_revision")} for row in after["states"]]
        report["schema"] = after["schema"]
        report["source_inventory_unchanged"] = all(scan(input_roots[key]) == rows for key, rows in manifests.items())
        report["preparation_passed"] = report["sql_inventory_unchanged"] and report["new_api_unchanged"] and report["source_inventory_unchanged"]
        report["migration_executed"] = False
        report["authorization_changed"] = False
        report["stage_closed"] = False
        save(directory / "private-input-manifest.json", {"files": manifests, "sql_before": before, "sql_after": after})
        save(output, report)
        if not report["preparation_passed"]:
            raise RuntimeError("Preparation boundary observation changed")
        print(
            json.dumps(
                {
                    "preparation_passed": True,
                    "counts": report["table_counts"],
                    "inputs": report["input_inventory"],
                    "packages_verified": sum(row["status"] == "verified" for row in receipt_rows),
                }
            )
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline-archive", type=Path)
    args = parser.parse_args()
    asyncio.run(run(args.directory, args.output, args.baseline_archive))
