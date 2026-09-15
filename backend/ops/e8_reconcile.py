"""Read-only SQL integrity and migration reconciliation for E8 fixtures."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pymysql


def inspect(label, host, port, user, password):
    db = pymysql.connect(host=host, port=port, user=user, password=password, database="doki_e4", charset="utf8mb4", autocommit=True)
    try:
        cur = db.cursor()
        cur.execute("SELECT version_num FROM alembic_version")
        revision = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()")
        tables = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM information_schema.referential_constraints WHERE constraint_schema=DATABASE()")
        fks = cur.fetchone()[0]
        cur.execute("SELECT @@global.read_only, @@global.super_read_only")
        flags = list(cur.fetchone())
        names = [
            "users",
            "auth_sessions",
            "chat_sessions",
            "chat_messages",
            "skills",
            "skill_versions",
            "skill_installations",
            "skill_packages",
            "skill_package_uploads",
            "knowledge_source_documents",
            "notes",
            "rag_user_states",
            "rag_generations",
            "rag_artifacts",
            "rag_generation_heads",
            "audit_events",
            "pending_actions",
        ]
        counts = {}
        for name in names:
            cur.execute("SELECT COUNT(*) FROM `" + name + "`")
            counts[name] = cur.fetchone()[0]
        cur.execute(
            "SELECT package_digest, canonical_archive, canonical_archive_digest, canonical_size_bytes FROM skill_packages ORDER BY package_digest"
        )
        package_checks = []
        for digest, archive, archive_digest, size in cur.fetchall():
            package_checks.append(
                {
                    "package_digest": digest,
                    "digest_match": hashlib.sha256(bytes(archive)).hexdigest() == archive_digest,
                    "size_match": len(archive) == size,
                }
            )
        cur.execute("SELECT canonical_id, content_blob, artifact_digest FROM knowledge_source_documents ORDER BY canonical_id")
        source_checks = [hashlib.sha256(bytes(blob)).hexdigest() == artifact for _, blob, artifact in cur.fetchall()]
        cur.execute("SELECT COUNT(*) FROM skill_versions v LEFT JOIN skill_packages p ON p.id=v.package_id WHERE p.id IS NULL")
        orphan_versions = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM chat_messages m LEFT JOIN chat_sessions s ON s.id=m.session_id WHERE s.id IS NULL")
        orphan_messages = cur.fetchone()[0]
        cur.close()
        return {
            "label": label,
            "revision": revision,
            "tables": tables,
            "foreign_keys": fks,
            "global_flags": flags,
            "counts": counts,
            "package_checks": package_checks,
            "source_digest_checks": source_checks,
            "orphan_skill_versions": orphan_versions,
            "orphan_chat_messages": orphan_messages,
        }
    finally:
        db.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("output", type=Path)
    p.add_argument("--replica", type=Path, required=True)
    a = p.parse_args()
    target = json.loads(Path(".runtime/e4/live-credentials.json").read_text())
    replica = json.loads((a.replica / "credentials.private.json").read_text())
    report = {
        "stage": "E8",
        "recorded_at": datetime.now(UTC).isoformat(),
        "target": inspect("current_target", "127.0.0.1", 33427, "doki_e4_app", target["target_password"]),
        "restored": inspect("restored_fixture", "127.0.0.1", replica["port"], replica["username"], replica["password"]),
    }
    report["passed"] = all(
        item["revision"] == "20260915_0011_e8_pending_actions"
        and item["global_flags"] == [0, 0]
        and item["foreign_keys"] == 58
        and item["orphan_skill_versions"] == 0
        and item["orphan_chat_messages"] == 0
        and all(x["digest_match"] and x["size_match"] for x in item["package_checks"])
        and all(item["source_digest_checks"])
        for item in report.values()
        if isinstance(item, dict) and "label" in item
    )
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "target_tables": report["target"]["tables"], "restored_tables": report["restored"]["tables"]}))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
