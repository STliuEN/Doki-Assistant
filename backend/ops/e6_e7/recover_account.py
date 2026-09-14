"""Explicit local account recovery; password arrives via a non-echoing prompt.

Run against a restored replica first, then the pinned target. Never prints or
stores plaintext passwords, hashes, cookies, JWTs or database credentials.
"""

import argparse
import asyncio
import getpass
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))


async def recover(username, password):
    from sqlalchemy import select

    from app.auth.audit import record_audit
    from app.auth.authorization import ensure_roles, role_names
    from app.auth.passwords import hash_password, verify_password
    from app.auth.repository import AuthRepository
    from app.auth.tokens import decode_access_token
    from app.db.db_config import AsyncSessionLocal, async_engine, verify_database_schema
    from app.models.identity_domain import AuthSession, RoleBinding, User

    await verify_database_schema()
    try:
        async with AsyncSessionLocal() as db, db.begin():
            user = await db.scalar(select(User).where(User.username == username).with_for_update())
            if user is None:
                raise ValueError("Named account does not exist; do not fabricate its identity or email")
            if verify_password(user.password_hash, password).verified:
                raise ValueError("Password already verifies; this conditional recovery is unnecessary")
            before = {"status": user.status, "roles": sorted(await role_names(db, user.id))}
            user.password_hash = hash_password(password)
            user.token_version = int(user.token_version) + 1
            user.status = "active"
            user.disabled_at = None
            repo = AuthRepository(db)
            old_sessions = list(await db.scalars(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.status == "active")))
            for session in old_sessions:
                await repo.logout(session_id=session.id, reason="explicit local account recovery")
            roles = await ensure_roles(db)
            role = roles["skill_admin"]
            binding = await db.scalar(select(RoleBinding).where(
                RoleBinding.user_id == user.id, RoleBinding.role_id == role.id,
                RoleBinding.scope_type == "global", RoleBinding.scope_id == "global",
            ))
            if binding is None:
                db.add(RoleBinding(id=str(uuid4()), user_id=user.id, role_id=role.id,
                                   scope_type="global", scope_id="global", status="active", revision=1))
            else:
                binding.status = "active"
                binding.expires_at = None
                binding.revoked_at = None
                binding.revision += 1
            await db.flush()
            after = {"status": user.status, "roles": sorted(await role_names(db, user.id))}
            audit = await record_audit(
                db, action="auth.local_account_recovered", target_type="user", target_id=user.id,
                result="succeeded", reason="User explicitly requested password recovery and a development administrator after failed verification",
                actor_type="operator", actor_id="local-user-authorized-maintenance",
                scope_type="user", scope_id=user.id, before=before, after=after,
            )
            authenticated, _, tokens = await repo.authenticate(username, password, device_label="local-recovery-verification")
            claims = decode_access_token(tokens.access_token)
            validated = await repo.validate_access_claims(claims)
            assert validated.id == authenticated.id == user.id
            await repo.logout(session_id=tokens.session_id, reason="local recovery verification completed")
            result = {"username": username, "user_id": user.id, "before": before, "after": after,
                      "password_reset": True, "authentication_verified": True, "old_sessions_revoked": len(old_sessions),
                      "verification_session_revoked": True, "audit_id": audit.id}
        return result
    finally:
        await async_engine.dispose()


def main():
    from ops.e5.verify_closure import TARGET, protected_state, sha_file
    from ops.e6_e7.acceptance_env import dump, preflight, save
    from ops.e6_e7.target_env import target_environment

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["replica", "target"], required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--replica-evidence", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not directory.is_relative_to(ROOT / ".runtime"):
        raise ValueError("Evidence must stay inside workspace .runtime")
    directory.mkdir(parents=True, exist_ok=True)
    report_path = directory / "account-recovery.json"
    if report_path.exists():
        raise ValueError("Preserve earlier recovery evidence; use a new directory")
    before = protected_state()
    if args.mode == "replica":
        os.environ.update(preflight(directory))
        backup = directory / "target-current.sql"
    else:
        if not args.replica_evidence:
            raise ValueError("Successful replica rehearsal is required")
        evidence = json.loads(args.replica_evidence.read_text(encoding="utf-8"))
        if evidence.get("mode") != "replica" or not evidence.get("authentication_verified") or evidence.get("username") != args.username:
            raise ValueError("Replica recovery evidence mismatch")
        os.environ.update(target_environment(directory))
        credentials = json.loads((ROOT / ".runtime/e4/live-credentials.json").read_text(encoding="utf-8"))
        content = dump(TARGET, credentials["target_password"], "doki_e4_app")
        if hashlib.sha256(content).hexdigest() != evidence["backup_sha256"]:
            raise ValueError("Target changed after backup restore rehearsal")
        backup = directory / "before-account-recovery.sql"
        backup.write_bytes(content)
    os.environ["AUTH_JWT_SECRET"] = json.loads((ROOT / ".runtime/e4/runtime-auth-secret.json").read_text(encoding="utf-8"))["AUTH_JWT_SECRET"]
    password = getpass.getpass("New account password (not echoed): ")
    report = asyncio.run(recover(args.username, password))
    report.update(mode=args.mode, recorded_at=datetime.now(UTC).isoformat(), backup_sha256=sha_file(backup),
                  new_api_unchanged=protected_state() == before)
    save(report_path, report)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
