"""Replica-only E6/E7 four-eyes authorization acceptance."""

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))


def _json(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(v) for v in value]
    return value


async def run(directory: Path) -> None:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.auth.authorization import ensure_roles, has_role
    from app.auth.errors import AuthError
    from app.db.db_config import AsyncSessionLocal, async_engine, verify_database_schema
    from app.models.identity_domain import RoleBinding, User
    from app.models.skill_domain import SkillInstallation, SkillInstallationStatus
    from app.skills.authorization import authorized_grant
    from app.skills.grant_service import decide, get_installation, request

    requester_id = "2e2c05f2-d031-527e-b463-93c9f0cccbfa"
    approver_id = "f4aff4a5-2f5a-535a-825f-b6a906d9cd12"
    report = {"stage": "E6E7", "fixture": "replica-only", "four_eyes": {}}
    try:
        await verify_database_schema()
        async with AsyncSessionLocal() as db:
            requester = await db.get(User, requester_id)
            approver = await db.get(User, approver_id)
            if requester is None or approver is None or requester.status != "active" or approver.status != "active":
                raise RuntimeError("Replica fixture users are missing or inactive")
            if not await has_role(db, requester_id, "skill_admin"):
                raise RuntimeError("Requester fixture is not a skill administrator")
            roles = await ensure_roles(db)
            security_binding = await db.scalar(
                select(RoleBinding).where(
                    RoleBinding.user_id == approver_id,
                    RoleBinding.role_id == roles["security_admin"].id,
                    RoleBinding.scope_type == "global",
                    RoleBinding.scope_id == "global",
                )
            )
            if security_binding is None:
                security_binding = RoleBinding(
                    user_id=approver_id,
                    role_id=roles["security_admin"].id,
                    scope_type="global",
                    scope_id="global",
                    status="active",
                    revision=1,
                )
                db.add(security_binding)
                await db.flush()
            if not await has_role(db, approver_id, "security_admin"):
                raise RuntimeError("Approver fixture is not a security administrator")

            installations = (
                await db.execute(
                    select(SkillInstallation)
                    .where(SkillInstallation.active_version_id.is_not(None))
                    .options(selectinload(SkillInstallation.active_version))
                    .order_by(SkillInstallation.id)
                )
            ).scalars().all()
            installation = next((item for item in installations if item.authorization_grant_id is None), None)
            if installation is None or installation.active_version is None:
                raise RuntimeError("No unbound Skill installation is available for acceptance")
            identifier = installation.skill_id

            async def new_request(expiry_minutes: int = 5):
                nonlocal installation
                installation = await get_installation(db, identifier)
                return await request(
                    db,
                    identifier,
                    requester_id,
                    expected_revision=int(installation.revision),
                    reason="E6/E7 replica four-eyes acceptance",
                    expires_at=datetime.now(UTC) + timedelta(minutes=expiry_minutes),
                )

            def decision_args(snapshot):
                return {
                    "expected_policy_revision": snapshot["policy_revision"],
                    "expected_subject_revision": snapshot["subject_revision"],
                    "expected_content_digest": snapshot["content_digest"],
                    "reason": "E6/E7 replica four-eyes acceptance",
                }

            first = await new_request()
            report["four_eyes"]["request"] = {"status": first["status"], "requested_by": first["requested_by"]}
            try:
                await decide(db, identifier, requester_id, first["id"], "approve", **decision_args(first))
            except AuthError as exc:
                report["four_eyes"]["self_approval_rejected"] = {"error": exc.code, "status": exc.status_code}
            else:
                raise AssertionError("Requester self-approval was accepted")

            approved = await decide(db, identifier, approver_id, first["id"], "approve", **decision_args(first))
            installation = await get_installation(db, identifier, lock=True)
            installation.status = SkillInstallationStatus.ENABLED
            await db.commit()
            installation = await get_installation(db, identifier)
            await authorized_grant(db, installation, installation.active_version)
            report["four_eyes"]["independent_approval"] = {"status": approved["status"], "approved_by": approved["approved_by"]}

            revoked = await decide(db, identifier, approver_id, first["id"], "revoke", **decision_args(approved))
            try:
                await authorized_grant(db, installation, installation.active_version)
            except AuthError as exc:
                report["four_eyes"]["revoke_fail_closed"] = {"error": exc.code, "status": exc.status_code}
            else:
                raise AssertionError("Revoked grant remained usable")
            report["four_eyes"]["revoke"] = {"status": revoked["status"]}

            second = await new_request()
            second_approved = await decide(db, identifier, approver_id, second["id"], "approve", **decision_args(second))
            installation = await get_installation(db, identifier, lock=True)
            installation.status = SkillInstallationStatus.ENABLED
            await db.commit()
            installation = await get_installation(db, identifier)
            from app.models.identity_domain import AuthorizationGrant
            grant_row = await db.get(AuthorizationGrant, second_approved["id"], with_for_update=True)
            grant_row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await db.flush()
            try:
                await authorized_grant(db, installation, installation.active_version)
            except AuthError as exc:
                report["four_eyes"]["expiry_fail_closed"] = {"error": exc.code, "status": exc.status_code}
            else:
                raise AssertionError("Expired grant remained usable")

            third = await new_request()
            third_approved = await decide(db, identifier, approver_id, third["id"], "approve", **decision_args(third))
            installation = await get_installation(db, identifier)
            grant_row = await db.get(AuthorizationGrant, third_approved["id"], with_for_update=True)
            grant_row.grant_json = {**grant_row.grant_json, "drift_fixture": True}
            await db.flush()
            try:
                await authorized_grant(db, installation, installation.active_version)
            except AuthError as exc:
                report["four_eyes"]["grant_drift_fail_closed"] = {"error": exc.code, "status": exc.status_code}
            else:
                raise AssertionError("Drifted grant remained usable")
            report["fixture_installation_id"] = installation.id
            report["fixture_skill_id"] = identifier
            report["temporary_security_admin_id"] = approver_id
            report["grant_statuses"] = [first["status"], revoked["status"], second_approved["status"], third_approved["status"]]
        output = directory / "authorization-acceptance.json"
        output.write_text(json.dumps(_json(report), ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(_json(report), ensure_ascii=False))
    finally:
        await async_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    from ops.e6_e7.acceptance_env import preflight

    os.environ.update(preflight(args.directory.resolve(), purposes=("runtime", "validate")))
    os.environ.update({"E6E7_ENABLED": "true", "E5_RAG_ENABLED": "true", "ENV": "dev"})
    asyncio.run(run(args.directory.resolve()))


if __name__ == "__main__":
    main()
