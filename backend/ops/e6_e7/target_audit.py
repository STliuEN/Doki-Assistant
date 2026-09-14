"""Final read-only reconciliation of the fixed Doki target and retained inputs."""

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))


async def audit(directory):
    from sqlalchemy import select, text

    from app.auth.authorization import has_role
    from app.auth.passwords import verify_password
    from app.db.db_config import AsyncSessionLocal, async_engine, verify_database_schema
    from app.models.identity_domain import MigrationMap, User
    from app.models.projection_domain import SkillPackageUpload
    from app.models.skill_domain import Skill, SkillInstallation, SkillInstallationStatus, SkillVersion
    from app.rag.projection.settings import status
    from app.skills.authorization import authorized_grant
    from app.skills.grant_service import get_installation
    from app.skills.service import skill_service
    from ops.e5.verify_closure import TARGET_UUID, protected_state
    from ops.e6_e7.acceptance_env import save

    baseline = json.loads((ROOT / "project_changes/2026-09-14-e6-e7-ar5-joint/artifacts/preparation.json").read_text(encoding="utf-8"))
    migration = json.loads((ROOT / ".runtime/e6e7-target-20260914/target-migration.json").read_text(encoding="utf-8"))
    private = json.loads((ROOT / ".runtime/e6e7-target-closure-20260914/security-admin.private.json").read_text(encoding="utf-8"))
    report = {"stage": "E6E7", "recorded_at": datetime.now(UTC).isoformat(), "target": "127.0.0.1:33427/doki_e4"}
    try:
        await verify_database_schema()
        async with AsyncSessionLocal() as db:
            assert await db.scalar(text("SELECT @@server_uuid")) == TARGET_UUID
            flags = (await db.execute(text("SELECT @@global.read_only, @@global.super_read_only"))).one()
            assert tuple(flags) == (0, 0)
            report["mysql_global_flags"] = list(flags)
            counts = {
                table: await db.scalar(text("SELECT COUNT(*) FROM " + table))
                for table in (
                    "users",
                    "skills",
                    "skill_versions",
                    "skill_installations",
                    "skill_aliases",
                    "skill_packages",
                    "skill_package_uploads",
                    "skill_imports",
                    "source_media",
                    "media_assets",
                    "authorization_grants",
                    "audit_events",
                    "knowledge_source_documents",
                    "notes",
                )
            }
            report["counts"] = counts
            assert all(
                counts[table] == 10
                for table in ("skills", "skill_versions", "skill_installations", "skill_aliases", "skill_packages", "skill_package_uploads")
            )
            assert counts["source_media"] == counts["media_assets"] == 0
            for table in ("knowledge_source_documents", "notes"):
                assert counts[table] == baseline["table_counts"][table]
            for receipt, migrated in zip(baseline["legacy_package_receipts"], migration["packages"], strict=True):
                version = await db.get(SkillVersion, receipt["version_id"])
                assert version.skill_id == receipt["skill_id"] and version.package_digest == receipt["package_digest"]
                assert version.id == migrated["version_id"] and version.package_id == migrated["package_id"]
                await skill_service._verify_version_storage(db, version)
                upload = await db.get(SkillPackageUpload, migrated["upload_id"])
                assert hashlib.sha256(upload.raw_archive).hexdigest() == receipt["archive_sha256"]
                assert upload.source_kind == "legacy_canonical"
                mapping = await db.scalar(
                    select(MigrationMap).where(MigrationMap.source_system == "e6e7-legacy-packages", MigrationMap.source_id == version.storage_key)
                )
                assert mapping.target_uuid == version.package_id and mapping.source_digest == receipt["archive_sha256"]
            admin = await db.scalar(select(User).where(User.username == private["username"]))
            assert verify_password(admin.password_hash, private["password"]).verified
            assert await has_role(db, admin.id, "security_admin") and not await has_role(db, admin.id, "skill_admin")
            owner = await db.scalar(select(User).where(User.username == "STliuEN"))
            assert await has_role(db, owner.id, "skill_admin") and not await has_role(db, owner.id, "security_admin")
            report["administrators"] = {
                "skill_admin": owner.username,
                "security_admin": admin.username,
                "distinct_ids": True,
                "security_password_verified": True,
                "human_reviewers_claimed": 1,
            }
            skills = []
            for skill_id in list(await db.scalars(select(SkillInstallation.skill_id))):
                installation = await get_installation(db, skill_id)
                name = await db.scalar(select(Skill.canonical_name).where(Skill.id == skill_id))
                item = {"skill_id": skill_id, "name": name, "status": installation.status.value}
                if installation.status == SkillInstallationStatus.ENABLED:
                    grant = await authorized_grant(db, installation, installation.active_version)
                    assert grant.requested_by == owner.id and grant.approved_by == admin.id
                    item.update(grant_id=grant.id, expires_at=str(grant.expires_at), grant_valid=True)
                else:
                    assert name in {"mcp-smoke-test", "public-info-lookup"}
                    item["reason"] = "external MCP unsupported in E6/E7 local A/limited-B scope"
                skills.append(item)
            assert sum(item["status"] == "enabled" for item in skills) == 8
            report["skills"] = skills
            report["rag"] = [
                await status(db, identifier) | {"owner": identifier} for identifier in (owner.id, "f4aff4a5-2f5a-535a-825f-b6a906d9cd12")
            ]
            assert all(row["status"] == "ready" for row in report["rag"])
        report.update(status="passed", stable_legacy_packages_verified=10, new_api=protected_state())
        assert report["new_api"] == baseline["new_api"]
        save(directory / "target-final-audit.json", report)
        print(json.dumps({"status": "passed", "counts": counts, "enabled": 8, "unsupported": 2, "new_api_unchanged": True}))
    finally:
        await async_engine.dispose()


def main():
    from ops.e6_e7.target_env import target_environment

    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    os.environ.update(target_environment(args.directory.resolve(), purposes=("runtime", "validate")))
    asyncio.run(audit(args.directory.resolve()))


if __name__ == "__main__":
    main()
