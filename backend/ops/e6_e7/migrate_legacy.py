"""Explicit legacy package import and embedded media backfill; no runtime fallback."""

import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))


async def migrate(factory, *, package_root, batch="e6e7-20260914"):
    from sqlalchemy import select

    from app.auth.audit import record_audit
    from app.models.identity_domain import MigrationMap
    from app.models.knowledge_document import KnowledgeSourceDocument
    from app.models.skill_domain import SkillInstallation, SkillInstallationStatus, SkillVersion
    from app.services.sql_media import extract_images, store_source_images
    from app.skills.service import skill_service
    from app.skills.sql_storage import SqlSkillPackageStorage
    from app.skills.storage import SkillPackageStorage

    report = {"packages": [], "media": [], "installations_disabled": [], "batch": batch}
    storage = SkillPackageStorage(package_root)
    async with factory() as db, db.begin():
        versions = list(await db.scalars(select(SkillVersion).order_by(SkillVersion.id).with_for_update()))
        for version in versions:
            if version.package_id is not None:
                await skill_service._verify_version_storage(db, version)
                continue
            content = storage.read_archive(version.storage_key, expected_digest=version.package_digest)
            package = await SqlSkillPackageStorage(db, actor_id="local-migration", source_kind="legacy_canonical").store_archive(content)
            if package.digest != version.package_digest:
                raise ValueError("Legacy package digest mismatch")
            version.package_id = package.package_id
            await skill_service._verify_version_storage(db, version)
            source_id = version.storage_key
            identity = str(uuid5(NAMESPACE_URL, "doki:e6e7:legacy-package:" + source_id))
            existing = await db.get(MigrationMap, identity)
            archive_digest = hashlib.sha256(content).hexdigest()
            if existing is None:
                db.add(MigrationMap(id=identity, migration_batch_id=batch, source_system="e6e7-legacy-packages",
                                    entity_type="skill_package", source_id=source_id, target_uuid=package.package_id,
                                    source_digest=archive_digest, status="mapped"))
            elif existing.source_digest != archive_digest or existing.target_uuid != package.package_id:
                raise ValueError("Legacy package mapping conflict")
            report["packages"].append({"version_id": version.id, "skill_id": version.skill_id,
                                       "package_id": package.package_id, "upload_id": package.upload_id,
                                       "package_digest": package.digest, "input_sha256": archive_digest})
            await record_audit(db, action="skill.sql_package_migrated", target_type="skill_version", target_id=version.id,
                               actor_type="operator", actor_id="local-user-authorized-migration", result="succeeded",
                               reason="Import frozen legacy canonical archive; original historical upload is unknown",
                               scope_type="global", scope_id="global", content_digest=package.digest,
                               migration_id=batch, after={"package_id": package.package_id, "version_id": version.id})
        installations = list(await db.scalars(select(SkillInstallation).order_by(SkillInstallation.id).with_for_update()))
        for installation in installations:
            if installation.authorization_grant_id is None and installation.status == SkillInstallationStatus.ENABLED:
                before = {"status": "enabled", "revision": int(installation.revision), "settings": installation.settings}
                installation.status = SkillInstallationStatus.DISABLED
                installation.settings = {**(installation.settings or {}), "default": False, "legacy_enabled_at_e6": True,
                                         "legacy_default_at_e6": (installation.settings or {}).get("default", False)}
                installation.revision += 1
                report["installations_disabled"].append(installation.id)
                await record_audit(db, action="skill.migration_awaiting_authorization", target_type="skill_installation",
                                   target_id=installation.id, actor_type="operator", actor_id="local-user-authorized-migration",
                                   result="succeeded", reason="Legacy enabled state does not constitute an independent security approval",
                                   scope_type="global", scope_id="global", before=before,
                                   after={"status": "disabled", "revision": int(installation.revision)}, migration_id=batch)
        sources = list(await db.scalars(select(KnowledgeSourceDocument).where(KnowledgeSourceDocument.status != "excluded")
                                        .order_by(KnowledgeSourceDocument.canonical_id).with_for_update()))
        for document in sources:
            images = await asyncio.to_thread(extract_images, document.content_blob, document.file_ext)
            await store_source_images(db, document, images)
            report["media"].append({"source_id": document.canonical_id, "owner": document.canonical_user_id, "images": len(images)})
        if report["packages"] or report["installations_disabled"]:
            await skill_service._bump_registry(db, skill_id=None, event_type="e6e7_sql_authority_migrated", payload={"batch": batch})
    return report


def main():
    from ops.e6_e7.acceptance_env import preflight, save
    parser = argparse.ArgumentParser()
    parser.add_argument("--replica", type=Path, required=True)
    args = parser.parse_args()
    directory = args.replica.resolve()
    os.environ.update(preflight(directory, ("migrate", "runtime", "validate")))
    from app.db.db_config import AsyncSessionLocal, async_engine, verify_database_schema

    async def run():
        try:
            await verify_database_schema()
            result = await migrate(AsyncSessionLocal, package_root=ROOT / "backend/data/skill_packages")
            save(directory / "legacy-migration.json", result)
            print(json.dumps({"packages": len(result["packages"]), "disabled": len(result["installations_disabled"]),
                              "sources": len(result["media"]), "images": sum(row["images"] for row in result["media"])}))
        finally:
            await async_engine.dispose()
    asyncio.run(run())


if __name__ == "__main__":
    main()
