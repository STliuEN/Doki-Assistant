"""Verify SQL-restored package/media/grant facts and regenerated Chroma bytes."""

import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))


async def verify(directory, source_directory, *, chroma=False):
    from sqlalchemy import func, select, text

    from app.auth.errors import AuthError
    from app.db.db_config import AsyncSessionLocal, async_engine, verify_database_schema
    from app.models.identity_domain import AuthorizationGrant, User
    from app.models.job_domain import AuditEvent
    from app.models.note import Note
    from app.models.projection_domain import SkillPackageUpload
    from app.models.skill_domain import SkillImport, SkillVersion
    from app.rag.projection.chroma_adapter import ChromaProjectionAdapter
    from app.rag.projection.embedding import embedding_model
    from app.rag.projection.snapshot import read_snapshot
    from app.rag.projection.sources import split_sources
    from app.services.sql_media import batch_images, image_response
    from app.skills.authorization import validate_run
    from app.skills.sql_storage import SqlSkillPackageStorage
    from ops.e6_e7.acceptance_env import save
    from ops.e6_e7.closure_acceptance import OTHER, OWNER

    fixture = json.loads((source_directory / "closure-acceptance.json").read_text(encoding="utf-8"))["restore_fixture"]
    report = {"status": "running", "sql_only": True, "legacy_package_path": "absent", "chroma_validation": chroma}
    try:
        await verify_database_schema()
        async with AsyncSessionLocal() as db:
            version = await db.get(SkillVersion, fixture["version_id"])
            assert version and version.package_digest == fixture["package_digest"]
            stored = await SqlSkillPackageStorage(db).load_archive(version.storage_key, expected_digest=version.package_digest)
            assert stored.package_id == version.package_id
            resource = await SqlSkillPackageStorage(db).read_resource(
                version.storage_key, "references/check.md", expected_digest=version.package_digest, max_bytes=65536
            )
            assert hashlib.sha256(resource).hexdigest() == fixture["resource_sha256"]
            upload = await db.scalar(
                select(SkillPackageUpload)
                .join(SkillImport, SkillImport.upload_id == SkillPackageUpload.id)
                .where(SkillImport.skill_version_id == version.id)
            )
            assert hashlib.sha256(upload.raw_archive).hexdigest() == fixture["raw_sha256"]
            assert await db.get(Note, fixture["note_id"])
            grant = await db.get(AuthorizationGrant, fixture["grant_id"])
            assert grant.status == "revoked" and grant.requested_by != grant.approved_by
            actions = set(await db.scalars(select(AuditEvent.action).where(AuditEvent.target_id == grant.id)))
            assert {"skill.authorization_requested", "skill.authorization_approve", "skill.authorization_revoke"} <= actions
            try:
                await validate_run(db, OWNER, fixture["run_id"], session_id=None)
            except AuthError as exc:
                assert exc.status_code == 403 and exc.code == "SKILL_AUTHORIZATION_REQUIRED"
            else:
                raise AssertionError("SQL restore resurrected a revoked run")
            for owner in (OWNER, OTHER):
                item = await image_response(db, owner, fixture["media_md5"], "embedded-1.png")
                assert hashlib.sha256(item["content"]).hexdigest() == fixture["image_sha256"]
                assert (await batch_images(db, owner, fixture["media_md5"]))["total"] == 1
            fk_count = await db.scalar(
                text(
                    "SELECT COUNT(*) FROM information_schema.referential_constraints "
                    "WHERE constraint_schema=DATABASE() AND table_name IN ('source_media','skill_versions','skill_imports')"
                )
            )
            assert fk_count >= 7
            counts = {
                table: await db.scalar(text("SELECT COUNT(*) FROM " + table))
                for table in (
                    "skill_packages",
                    "skill_package_uploads",
                    "skill_imports",
                    "source_media",
                    "media_assets",
                    "authorization_grants",
                    "audit_events",
                )
            }
            users = list(await db.scalars(select(User.id)))
            assert await db.scalar(select(func.count()).select_from(SkillVersion).where(SkillVersion.package_id.is_(None))) == 0
        report.update(
            package_raw_canonical_resource_verified=True,
            source_image_download_batch_verified=True,
            revoked_run_denied=True,
            authorization_audit_verified=True,
            table_counts=counts,
            foreign_keys=fk_count,
        )
        if chroma:
            adapter = ChromaProjectionAdapter(embedding_model)
            corpora = []
            for owner in users:
                snapshot = await read_snapshot(AsyncSessionLocal, owner)
                expected = await asyncio.to_thread(split_sources, snapshot.sources, snapshot.index)
                for kind, artifact in snapshot.artifacts.items():
                    await adapter.validate(
                        collection=artifact["collection"],
                        owner=owner,
                        generation=artifact["generation"],
                        chunks=expected[kind],
                        receipt=artifact["receipt"],
                    )
                    corpora.append(
                        {
                            "owner": owner,
                            "kind": kind,
                            "chunks": len(expected[kind]),
                            "ids_digest": artifact["receipt"]["ids_digest"],
                            "generation": artifact["generation"],
                        }
                    )
            report["chroma"] = corpora
            from app.rag.projection.contracts import ProjectionUnavailable

            missing = ChromaProjectionAdapter(embedding_model, persist_directory=directory / "empty-chroma-fault")
            sample = corpora[0]
            try:
                await missing.chunks(
                    collection=missing.locator(sample["kind"], sample["generation"]), owner=sample["owner"], generation=sample["generation"]
                )
            except ProjectionUnavailable as exc:
                assert exc.code == "chroma_read_failed"
                report["missing_chroma_fail_closed"] = exc.code
            else:
                raise AssertionError("Missing Chroma collection silently recovered from another authority")
        report["status"] = "passed"
        save(directory / ("restore-verified-chroma.json" if chroma else "restore-verified-sql.json"), report)
        print(json.dumps({"status": "passed", "chroma": chroma, "counts": counts}))
    finally:
        await async_engine.dispose()


def main():
    from ops.e6_e7.acceptance_env import preflight

    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--source-directory", type=Path, required=True)
    parser.add_argument("--chroma", action="store_true")
    args = parser.parse_args()
    directory = args.directory.resolve()
    os.environ.update(preflight(directory, ("runtime", "validate")))
    legacy = directory / "absent-legacy-packages"
    assert not legacy.exists()
    os.environ["SKILL_STORAGE_DIR"] = str(legacy)
    asyncio.run(verify(directory, args.source_directory.resolve(), chroma=args.chroma))


if __name__ == "__main__":
    main()
