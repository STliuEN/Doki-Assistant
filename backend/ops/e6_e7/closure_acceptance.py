"""Real SQL lifecycle and revocation acceptance, restricted to a fresh replica."""

import argparse
import asyncio
import base64
import hashlib
import io
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
OWNER = "2e2c05f2-d031-527e-b463-93c9f0cccbfa"
SECURITY = "eb4a32d9-5eef-4e01-b461-b605656f3af1"
OTHER = "f4aff4a5-2f5a-535a-825f-b6a906d9cd12"
RESOURCE = b"SQL-only E6/E7 resource acceptance.\n"


async def run(directory):
    from fastapi import HTTPException
    from PIL import Image
    from sqlalchemy import func, select, text

    from app.agent.skill_registry import tool_registry
    from app.agent.tool_context import set_current_run_binding, set_current_session_id, set_current_user_id
    from app.agent.tool_guard import tool_definition_digest, tool_provider_config_digest, wrap_tool
    from app.auth.authorization import ensure_roles, has_role
    from app.auth.errors import AuthError
    from app.core.background_init import init_manager
    from app.db.db_config import AsyncSessionLocal as factory
    from app.db.db_config import async_engine, verify_database_schema
    from app.models.e4_migration import MediaAsset
    from app.models.e6_e7_domain import SourceMedia
    from app.models.identity_domain import AuthorizationGrant, RoleBinding
    from app.models.job_domain import Job
    from app.models.knowledge_document import KnowledgeSourceDocument
    from app.models.note import Note
    from app.models.projection_domain import SkillPackageUpload
    from app.models.skill_domain import Skill, SkillImport, SkillInstallationStatus, SkillVersion
    from app.services.agent_run_service import prepare_agent_run
    from app.services.confirmation_service import resolve_confirmed_tool
    from app.services.knowledge_document_service import KnowledgeDocumentService, KnowledgeFileInput
    from app.services.note_service import NoteService
    from app.services.sql_media import batch_images, image_response, source_images
    from app.skills.authorization import authorized_grant, job_authority, validate_run
    from app.skills.grant_service import decide, get_installation, request
    from app.skills.package import SkillPackageError, parse_skill_zip
    from app.skills.resource_tools import build_resource_tools
    from app.skills.service import SkillConflictError, skill_service
    from app.skills.sql_storage import SqlSkillPackageStorage
    from app.skills.storage import build_skill_archive, package_digest
    from ops.e6_e7.acceptance_env import save

    result = {"stage": "E6E7", "fixture": "synthetic-inputs-real-SQL-and-application-services", "checks": []}
    output = directory / ("closure-acceptance-" + uuid4().hex[:8] + ".json")

    def passed(case, **details):
        result["checks"].append({"case": case, "passed": True, **details})
        save(output, result)
        print(case + ": passed", flush=True)

    async def rejected(call, exception, *, code=None, status=None, message=None):
        try:
            await call()
        except exception as exc:
            if code is not None:
                assert exc.code == code, (type(exc).__name__, getattr(exc, "code", None))
            if status is not None:
                assert exc.status_code == status
            if message is not None:
                assert message in str(exc)
            return
        raise AssertionError("Expected rejection did not occur")

    async def imported(raw, key):
        async with factory() as db:
            return await skill_service.import_archive(db, raw, actor_id=OWNER, idempotency_key=key)

    def decision_args(grant):
        return {
            "expected_policy_revision": grant["policy_revision"],
            "expected_subject_revision": grant["subject_revision"],
            "expected_content_digest": grant["content_digest"],
            "reason": "Isolated E6/E7 acceptance",
        }

    try:
        await verify_database_schema()
        name = "closure-fixture-" + uuid4().hex[:8]
        raw = build_skill_archive(
            {
                "SKILL.md": (
                    "---\nname: " + name + "\ndescription: SQL closure acceptance\n---\nUse references/check.md and the selected local tools.\n"
                ).encode(),
                "references/check.md": RESOURCE,
            }
        )
        key = "closure-import-" + uuid4().hex
        first, duplicate = await asyncio.gather(imported(raw, key), imported(raw, key))
        assert first["id"] == duplicate["id"] and first["digest"] == package_digest(parse_skill_zip(raw))
        await rejected(lambda: imported(raw + b"changed", key), SkillConflictError, message="different actor or archive")
        passed("concurrent import idempotency and key conflict", import_id=first["id"])
        async with factory() as db:
            await skill_service.approve_import(
                db,
                first["id"],
                actor_id=OWNER,
                expected_digest=first["digest"],
                expected_revision=0,
                enabled=True,
                default=False,
                visibility="public",
                order=100,
                tools=["create_note", "delete_memory"],
                always_on=False,
                routable=True,
                routing_examples={},
            )
            skill_id = await db.scalar(select(Skill.id).where(Skill.canonical_name == name))
            installation = await get_installation(db, skill_id)
            assert installation.status == SkillInstallationStatus.DISABLED and not installation.authorization_grant_id
            version_id, storage_key, digest = (
                installation.active_version_id,
                installation.active_version.storage_key,
                installation.active_version.package_digest,
            )
            export, _ = await skill_service.export_version(db, skill_id, version_id)
            assert package_digest(parse_skill_zip(export)) == digest
            upload_id = await db.scalar(select(SkillImport.upload_id).where(SkillImport.id == first["id"]))
            upload = await db.get(SkillPackageUpload, upload_id)
            assert bytes(upload.raw_archive) == raw and upload.request_archive_digest == hashlib.sha256(raw).hexdigest()
            assert (
                await SqlSkillPackageStorage(db).read_resource(storage_key, "references/check.md", max_bytes=65536, expected_digest=digest)
                == RESOURCE
            )
        reimport = await imported(export, "closure-roundtrip-" + uuid4().hex)
        assert reimport["digest"] == digest
        passed("publish disabled and verified raw/canonical/resource export roundtrip", skill_id=skill_id, version_id=version_id)

        bad = io.BytesIO()
        import zipfile

        with zipfile.ZipFile(bad, "w") as archive:
            archive.writestr("../outside.txt", b"forbidden")
            archive.writestr("SKILL.md", b"---\nname: invalid\ndescription: invalid\n---\ninvalid")
        quarantine = await imported(bad.getvalue(), "closure-bad-" + uuid4().hex)
        assert quarantine["status"] == "quarantined" and not quarantine.get("skill_id")
        passed("traversal upload quarantined with no installation", error_code=quarantine.get("error_code"))

        async with factory() as db:
            installation = await get_installation(db, skill_id)
            grant = await request(
                db,
                skill_id,
                OWNER,
                expected_revision=int(installation.revision),
                reason="Isolated E6/E7 acceptance",
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        # Give requester both roles only inside a rolled-back replica transaction.
        # This proves the requester/approver identity rule independently of role denial.
        async with factory() as db:
            roles = await ensure_roles(db)
            db.add(
                RoleBinding(
                    id=str(uuid4()),
                    user_id=OWNER,
                    role_id=roles["security_admin"].id,
                    scope_type="global",
                    scope_id="global",
                    status="active",
                    revision=1,
                    effective_at=datetime.now(UTC) - timedelta(minutes=1),
                )
            )
            await db.flush()
            assert await has_role(db, OWNER, "security_admin")
            await rejected(
                lambda: decide(db, skill_id, OWNER, grant["id"], "approve", **decision_args(grant)),
                AuthError,
                status=403,
                message="requester and approver must be different",
            )
            await db.rollback()
        async with factory() as db:
            await rejected(
                lambda: decide(db, skill_id, OTHER, grant["id"], "approve", **decision_args(grant)),
                AuthError,
                status=403,
                message="Security administrator permission required",
            )
        async with factory() as db:
            approved = await decide(db, skill_id, SECURITY, grant["id"], "approve", **decision_args(grant))
            installation = await get_installation(db, skill_id)
            await skill_service.update_settings(db, skill_id, actor_id=OWNER, expected_revision=int(installation.revision), patch={"enabled": True})
        passed("four-eyes including dual-role self-approval and ordinary-user rejection", grant_id=grant["id"])

        async def prepare():
            async with factory() as db:
                plan = await prepare_agent_run(
                    db,
                    OWNER,
                    query="Create acceptance note",
                    model_config_id=None,
                    prompt_type=None,
                    skill_ids=[skill_id],
                    tool_ids=["create_note", "delete_memory"],
                    session_id=None,
                )
                await db.commit()
                return plan

        plan = await prepare()
        set_current_user_id(OWNER)
        set_current_session_id(None)
        set_current_run_binding(plan.run_id, plan.registry_revision)
        async with factory() as db:
            snapshot = await skill_service.reconcile_registry(db)
        resources = build_resource_tools([snapshot.get(skill_id)])
        read_resource = resources[1]
        action = {
            "run_id": plan.run_id,
            "user_id": OWNER,
            "session_id": None,
            "registry_revision": plan.registry_revision,
            "tool_id": "delete_memory",
            "tool_digest": tool_definition_digest(tool_registry.get("delete_memory")),
            "source": "local",
            "provider_config_digest": tool_provider_config_digest(tool_registry.get("delete_memory")),
        }
        payload = {"owner_id": OWNER, "skill_origin": {"run_id": plan.run_id, "session_id": None}}

        async def check_run():
            async with factory() as db:
                await validate_run(db, OWNER, plan.run_id, session_id=None, tool_id="create_note")

        async def check_confirmation():
            async with factory() as db:
                return await resolve_confirmed_tool(db, action, OWNER)

        async def check_job():
            async with job_authority(factory, payload):
                return True

        async def check_resource():
            return await read_resource.ainvoke({"skill_id": skill_id, "path": "references/check.md"})

        await check_run()
        assert (await check_resource()).encode() == RESOURCE
        assert await check_job()
        assert (await check_confirmation()).id == "delete_memory"
        init_manager.note_service = NoteService()
        note_title = "E6E7 closure " + uuid4().hex
        note_tool = wrap_tool(tool_registry.get("create_note"))
        await note_tool.ainvoke({"title": note_title, "content": "SQL note written by an authorized Skill."})
        async with factory() as db:
            note = await db.scalar(select(Note).where(Note.title == note_title, Note.canonical_user_id == OWNER))
            assert note is not None
            note_id = note.id
            jobs = list(await db.scalars(select(Job).where(Job.owner_scope_id == OWNER)))
            origins = [row.id for row in jobs if (row.payload_json or {}).get("skill_origin", {}).get("run_id") == plan.run_id]
            assert origins, "Skill business jobs lost their originating run"
            await rejected(lambda: validate_run(db, OTHER, plan.run_id, session_id=None), AuthError, status=403, message="owner or session")
        passed(
            "real RunBinding resource tool note side effect job provenance and confirmation positive",
            run_id=plan.run_id,
            note_id=note_id,
            jobs=origins,
        )

        for label, mutation in (("expiry", {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}), ("digest", {"content_digest": "0" * 64})):
            async with factory() as db:
                installation = await get_installation(db, skill_id)
                assert installation.status == SkillInstallationStatus.ENABLED
                await authorized_grant(db, installation, installation.active_version)
                row = await db.get(AuthorizationGrant, grant["id"])
                for attr, value in mutation.items():
                    setattr(row, attr, value)
                await db.flush()
                await rejected(
                    lambda: authorized_grant(db, installation, installation.active_version),
                    AuthError,
                    code="SKILL_AUTHORIZATION_REQUIRED",
                    status=403,
                )
                await rejected(lambda: validate_run(db, OWNER, plan.run_id, session_id=None), AuthError, status=403)
                await db.rollback()
            await check_run()
            passed(label + " mutation rejected while enabled; rollback restores positive control")

        # SQL-only corruption injection is confined to this fresh replica and rolled back.
        async with async_engine.connect() as connection:
            transaction = await connection.begin()
            await connection.execute(
                text("UPDATE skill_packages SET canonical_archive=:bytes WHERE package_digest=:digest"),
                {"bytes": b"corrupted replica fixture", "digest": digest},
            )
            from sqlalchemy.ext.asyncio import AsyncSession

            async with AsyncSession(bind=connection) as db:
                await rejected(
                    lambda: SqlSkillPackageStorage(db).load_archive(storage_key, expected_digest=digest),
                    SkillPackageError,
                    code="storage_digest_mismatch",
                )
            await transaction.rollback()
        await check_run()
        passed("SQL package corruption fails closed with no filesystem fallback")

        async with factory() as db:
            await decide(db, skill_id, SECURITY, grant["id"], "revoke", **decision_args(approved))
        from app.jobs.runner import JobHandlerError

        await rejected(check_run, AuthError, status=403)
        await rejected(check_resource, AuthError, status=403)
        await rejected(check_job, JobHandlerError, code="skill_authorization_revoked")
        await rejected(check_confirmation, AuthError, status=403)
        await rejected(lambda: note_tool.ainvoke({"title": note_title + " revoked", "content": "Must not be written"}), AuthError, status=403)
        await rejected(prepare, HTTPException, status=400)
        async with factory() as db:
            assert await db.scalar(select(func.count()).select_from(Note).where(Note.title == note_title + " revoked")) == 0
        passed("revoke propagates to new run existing tool resource queued-job and deferred confirmation; no second note")

        set_current_run_binding(None, None)
        # Terminal revoked jobs must be reconciled before another source write.
        from ops.e6_e7.closure_runtime import rebuild

        await rebuild(directory)
        buffer = io.BytesIO()
        Image.new("RGB", (37, 29), (34, 151, 78)).save(buffer, format="PNG")
        image = buffer.getvalue()
        content = b"# E6E7 SQL media restore fixture\n![embedded](data:image/png;base64," + base64.b64encode(image) + b")\n"
        service = KnowledgeDocumentService()
        source_ids = []
        assets = []
        for owner in (OWNER, OTHER):
            async with factory() as db:
                source, created = await service.upsert_source(db, owner, KnowledgeFileInput("e6e7-closure-media.md", content, "text/markdown", 0), {})
                assert created
                source_ids.append(source.canonical_id)
                md5 = source.md5
                item = await image_response(db, owner, md5, "embedded-1.png")
                assert item["content"] == image and item["mime_type"] == "image/png"
                assets.append(item["media_id"])
                batch = await batch_images(db, owner, md5)
                assert batch["total"] == 1 and base64.b64decode(batch["images"]["embedded-1.png"].split(",", 1)[1]) == image
        assert source_ids[0] != source_ids[1] and assets[0] != assets[1]
        async with factory() as db:
            await rejected(lambda: source_images(db, OTHER, source_id=source_ids[0]), HTTPException, status=404)
            await rejected(lambda: image_response(db, SECURITY, md5, "embedded-1.png"), HTTPException, status=404)
            await rejected(lambda: image_response(db, OWNER, md5, "../image.png"), HTTPException, status=400)
        for table, field, identity, value in (
            ("media_assets", "content_blob", assets[0], b"corruption"),
            ("knowledge_source_documents", "content_blob", source_ids[0], b"changed source"),
        ):
            async with async_engine.connect() as connection:
                transaction = await connection.begin()
                await connection.execute(text(f"UPDATE {table} SET {field}=:value WHERE id=:identity"), {"value": value, "identity": identity})
                from sqlalchemy.ext.asyncio import AsyncSession

                async with AsyncSession(bind=connection) as db:
                    await rejected(lambda: image_response(db, OWNER, md5, "embedded-1.png"), HTTPException, status=409)
                await transaction.rollback()
        async with async_engine.connect() as connection:
            transaction = await connection.begin()
            await connection.execute(text("DELETE FROM knowledge_source_documents WHERE id=:id"), {"id": source_ids[0]})
            from sqlalchemy.ext.asyncio import AsyncSession

            async with AsyncSession(bind=connection) as db:
                assert await db.scalar(select(func.count()).select_from(SourceMedia).where(SourceMedia.source_id == source_ids[0])) == 0
                await rejected(lambda: image_response(db, OWNER, md5, "embedded-1.png"), HTTPException, status=404)
            await transaction.rollback()
        async with factory() as db:
            assert (await image_response(db, OWNER, md5, "embedded-1.png"))["content"] == image
            for asset_id in assets:
                assert await db.get(MediaAsset, asset_id)
            assert await db.get(KnowledgeSourceDocument, source_ids[0])
            assert await db.get(SkillVersion, version_id)
        passed("embedded-media application ingest download batch owner same-MD5 deletion corruption and rollback")
        result["restore_fixture"] = {
            "skill_id": skill_id,
            "version_id": version_id,
            "storage_key": storage_key,
            "package_digest": digest,
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "resource_sha256": hashlib.sha256(RESOURCE).hexdigest(),
            "run_id": plan.run_id,
            "grant_id": grant["id"],
            "grant_status": "revoked",
            "note_id": note_id,
            "media_md5": md5,
            "source_ids": source_ids,
            "asset_ids": assets,
            "image_sha256": hashlib.sha256(image).hexdigest(),
        }
        result["status"] = "passed"
        save(output, result)
        save(directory / "closure-acceptance.json", result)
    except Exception as exc:
        result.update(status="failed", error_type=type(exc).__name__)
        save(output, result)
        raise
    finally:
        await async_engine.dispose()


def main():
    from ops.e6_e7.acceptance_env import preflight

    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    assert not (directory / "closure-acceptance.json").exists(), "Use a new replica for another acceptance run"
    os.environ.update(preflight(directory, purposes=("runtime", "validate")))
    os.environ.update(E4_RUNNER_ENABLED="false", SKILL_STORAGE_DIR=str(directory / "absent-legacy-packages"))
    asyncio.run(run(directory))


if __name__ == "__main__":
    main()
