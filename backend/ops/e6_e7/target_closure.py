"""Complete the explicitly authorized E6/E7 target closure gates."""

import argparse
import asyncio
import base64
import hashlib
import json
import os
import secrets
import sys
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))


async def run(directory: Path, security_password: str) -> None:
    from fastapi import HTTPException
    from sqlalchemy import select, text

    from app.auth.audit import record_audit
    from app.auth.authorization import ensure_roles, has_role
    from app.auth.errors import AuthError
    from app.auth.passwords import hash_password, verify_password
    from app.db.db_config import AsyncSessionLocal, async_engine, verify_database_schema
    from app.models.e4_migration import MediaAsset
    from app.models.e6_e7_domain import SourceMedia
    from app.models.identity_domain import RoleBinding, User
    from app.models.knowledge_document import KnowledgeSourceDocument
    from app.models.skill_domain import Skill, SkillInstallation, SkillInstallationStatus
    from app.services.sql_media import extract_images, image_response, source_images, store_source_images, verify_asset
    from app.skills.authorization import authorized_grant, subject
    from app.skills.grant_service import decide, get_installation, request
    from app.skills.service import skill_service
    from ops.e6_e7.acceptance_env import save

    requester_id = "2e2c05f2-d031-527e-b463-93c9f0cccbfa"
    security_username = "STliuEN-security-admin"
    security_email = "stliuEn-security-admin@local.invalid"
    security_id = str(uuid4())
    report = {"stage": "E6E7", "target": True, "security_admin": {}, "skills": [], "media": {}}
    journal = directory / ("target-closure-" + uuid4().hex[:8] + ".json")
    try:
        await verify_database_schema()
        async with AsyncSessionLocal() as db:
            requester = await db.get(User, requester_id)
            if requester is None or requester.status != "active" or not await has_role(db, requester_id, "skill_admin"):
                raise RuntimeError("STliuEN is not an active skill administrator")
            existing = await db.scalar(select(User).where(User.username == security_username))
            if existing is not None:
                security_id = existing.id
                security_user = existing
                assert security_user.status == "active" and security_id != requester_id
                assert verify_password(security_user.password_hash, security_password).verified
                assert await has_role(db, security_id, "security_admin")
                assert not await has_role(db, security_id, "skill_admin")
                assert not await has_role(db, requester_id, "security_admin")
            else:
                security_user = User(
                    id=security_id,
                    username=security_username,
                    email_display=security_email,
                    email_normalized=security_email.casefold(),
                    password_hash=hash_password(security_password),
                    status="active",
                    token_version=1,
                )
                db.add(security_user)
                await db.flush()
            roles = await ensure_roles(db)
            binding = await db.scalar(
                select(RoleBinding).where(
                    RoleBinding.user_id == security_id,
                    RoleBinding.role_id == roles["security_admin"].id,
                    RoleBinding.scope_type == "global",
                    RoleBinding.scope_id == "global",
                )
            )
            if binding is None:
                db.add(
                    RoleBinding(
                        id=str(uuid4()),
                        user_id=security_id,
                        role_id=roles["security_admin"].id,
                        scope_type="global",
                        scope_id="global",
                        status="active",
                        revision=1,
                        effective_at=datetime.now(UTC),
                    )
                )
            else:
                binding.status = "active"
                binding.expires_at = None
                binding.revoked_at = None
            await db.flush()
            if existing is None:
                await record_audit(
                    db,
                    action="auth.e6e7_security_admin_created",
                    target_type="user",
                    target_id=security_id,
                    actor_type="operator",
                    actor_id="local-user-authorized-maintenance",
                    result="succeeded",
                    reason="Explicit user authorization for E6/E7 independent security administrator",
                )
            if os.environ.get("E6E7_ROTATE_CREDENTIAL") == "true":
                security_password = secrets.token_urlsafe(24)
                security_user.password_hash = hash_password(security_password)
                security_user.token_version += 1
                await record_audit(
                    db,
                    action="auth.password_reset",
                    target_type="user",
                    target_id=security_id,
                    actor_type="operator",
                    actor_id="local-user-authorized-maintenance",
                    result="succeeded",
                    reason="Complete user-authorized security administrator provisioning",
                )
            await db.commit()
            save(directory / "security-admin.private.json", {"username": security_username, "password": security_password})
            assert await has_role(db, security_id, "security_admin")
            report["security_admin"] = {
                "username": security_username,
                "user_id": security_id,
                "roles": ["security_admin"],
                "independent_from": requester_id,
                "password_verified": True,
                "approval_boundary": "Distinct application accounts, one authorizing human",
            }
            report["clock"] = {"host_utc": datetime.now(UTC).isoformat(), "sql_utc": str(await db.scalar(text("SELECT UTC_TIMESTAMP(6)")))}

            installations = (
                (
                    await db.execute(
                        select(SkillInstallation.skill_id).where(SkillInstallation.active_version_id.is_not(None)).order_by(SkillInstallation.id)
                    )
                )
                .scalars()
                .all()
            )
            for skill_id in installations:
                installation = await get_installation(db, skill_id, lock=True)
                if installation.authorization_grant_id is not None:
                    try:
                        await authorized_grant(db, installation, installation.active_version, require_enabled=False)
                    except AuthError as exc:
                        raise RuntimeError(f"Existing target grant is invalid for {skill_id}: {exc.code}") from exc
                    await skill_service.update_settings(
                        db, skill_id, actor_id=requester_id, expected_revision=int(installation.revision), patch={"enabled": True}
                    )
                    installation = await get_installation(db, skill_id)
                    grant = await authorized_grant(db, installation, installation.active_version)
                    assert grant.approved_by == security_id and grant.requested_by == requester_id
                    report["skills"].append(
                        {
                            "skill_id": installation.skill_id,
                            "installation_id": installation.id,
                            "grant_id": installation.authorization_grant_id,
                            "status": "approved",
                            "approved_by": security_id,
                            "enabled": True,
                            "reused": True,
                        }
                    )
                    save(journal, report)
                    continue
                try:
                    await subject(db, installation, installation.active_version)
                except AuthError as exc:
                    name = await db.scalar(select(Skill.canonical_name).where(Skill.id == skill_id))
                    if name not in {"mcp-smoke-test", "public-info-lookup"}:
                        raise
                    if exc.message not in {"Skill contains an unavailable tool", "External or unavailable tools are unsupported in this stage"}:
                        raise
                    assert installation.status == SkillInstallationStatus.DISABLED
                    skill_id = installation.skill_id
                    installation_id = installation.id
                    await db.rollback()
                    report["skills"].append(
                        {
                            "skill_id": skill_id,
                            "installation_id": installation_id,
                            "status": "unsupported",
                            "enabled": False,
                            "skipped": exc.code,
                            "reason": exc.message,
                        }
                    )
                    save(journal, report)
                    continue
                else:
                    snapshot = await request(
                        db,
                        installation.skill_id,
                        requester_id,
                        expected_revision=int(installation.revision),
                        reason="E6/E7 target closure authorization",
                        expires_at=datetime.now(UTC) + timedelta(days=30),
                    )
                    await db.commit()
                    installation = await get_installation(db, installation.skill_id)
                    approved = await decide(
                        db,
                        installation.skill_id,
                        security_id,
                        snapshot["id"],
                        "approve",
                        expected_policy_revision=snapshot["policy_revision"],
                        expected_subject_revision=snapshot["subject_revision"],
                        expected_content_digest=snapshot["content_digest"],
                        reason="Independent security approval for E6/E7 target closure",
                    )
                    installation = await get_installation(db, installation.skill_id, lock=True)
                    await skill_service.update_settings(
                        db, skill_id, actor_id=requester_id, expected_revision=int(installation.revision), patch={"enabled": True}
                    )
                    installation = await get_installation(db, skill_id)
                    await authorized_grant(db, installation, installation.active_version)
                    await db.commit()
                    report["skills"].append(
                        {
                            "skill_id": installation.skill_id,
                            "installation_id": installation.id,
                            "grant_id": approved["id"],
                            "status": approved["status"],
                            "approved_by": approved["approved_by"],
                            "enabled": True,
                        }
                    )
                    save(journal, report)

            owner = requester_id
            other = security_id
            image_buffer = BytesIO()
            Image.new("RGB", (32, 24), (40, 120, 220)).save(image_buffer, format="PNG")
            image = image_buffer.getvalue()
            content = b"# Transactional E6/E7 fixture\n![image](data:image/png;base64," + base64.b64encode(image) + b")\n"
            source_id = str(uuid4())
            md5 = hashlib.md5(content).hexdigest()
            artifact = hashlib.sha256(content).hexdigest()
            source = KnowledgeSourceDocument(
                id=source_id,
                user_id=owner,
                canonical_id=source_id,
                canonical_user_id=owner,
                md5=md5,
                content_digest=artifact,
                artifact_digest=artifact,
                filename="e6e7-target-media-fixture.md",
                original_filename="e6e7-target-media-fixture.md",
                file_ext="md",
                mime_type="text/markdown",
                file_size=len(content),
                content_blob=content,
                status="indexed",
            )
            db.add(source)
            await db.flush()
            await store_source_images(db, source, extract_images(content, "md"))
            rows = await source_images(db, owner, source_id=source_id)
            if len(rows) != 1 or rows[0]["content"] != image:
                raise AssertionError("Target media owner read failed")
            try:
                await image_response(db, other, md5, "embedded-1.png")
            except HTTPException as exc:
                assert exc.status_code == 404
                cross_user_rejected = True
            else:
                cross_user_rejected = False
            asset_id = rows[0]["media_id"]
            asset = await db.get(MediaAsset, asset_id)
            asset.content_blob = b"corrupted"
            try:
                verify_asset(asset, owner)
            except HTTPException as exc:
                assert exc.status_code == 409
                corruption_rejected = True
            else:
                corruption_rejected = False
            if not cross_user_rejected or not corruption_rejected:
                raise AssertionError("Target media negative case was accepted")
            report["media"] = {
                "owner_read": True,
                "cross_user_rejected": True,
                "corruption_rejected": True,
                "fixture": "transactional-target-only",
                "rolled_back": True,
            }
            await db.rollback()
            # Verify the transactional fixture left no durable rows.
            async with AsyncSessionLocal() as check:
                assert await check.get(KnowledgeSourceDocument, source_id) is None
                assert await check.get(MediaAsset, asset_id) is None
                remaining = await check.scalar(select(SourceMedia).where(SourceMedia.source_id == source_id))
                if remaining is not None:
                    raise AssertionError("Target media acceptance fixture was not rolled back")
        assert sum(bool(item["enabled"]) for item in report["skills"]) == 8
        report["status"] = "passed"
        save(journal, report)
        output = directory / "target-closure.json"
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(json.dumps({"security_admin": security_username, "skills": len(report["skills"]), "media": report["media"]}, ensure_ascii=False))
    finally:
        await async_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--rotate-credential", action="store_true")
    args = parser.parse_args()
    from ops.e6_e7.target_env import target_environment

    os.environ.update(target_environment(args.directory.resolve(), purposes=("runtime", "validate", "migrate")))
    os.environ.update({"E6E7_ENABLED": "true", "E5_RAG_ENABLED": "true", "ENV": "dev"})
    private = args.directory.resolve() / "security-admin.private.json"
    password = json.loads(private.read_text(encoding="utf-8"))["password"] if private.exists() else secrets.token_urlsafe(24)
    os.environ["E6E7_ROTATE_CREDENTIAL"] = str(args.rotate_credential).lower()
    asyncio.run(run(args.directory.resolve(), password))


if __name__ == "__main__":
    main()
