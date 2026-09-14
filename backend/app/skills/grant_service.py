"""Content administrator requests and independent security decisions."""

from datetime import UTC, datetime

from app.auth.audit import record_audit
from app.auth.authorization import approve_grant, has_role, request_grant, revoke_grant
from app.db.transaction_context import persist_service_write
from app.models.identity_domain import AuthorizationGrant
from app.models.skill_domain import SkillInstallationStatus
from app.skills.authorization import authorized_grant, denied, subject
from app.skills.service import SkillConflictError, SkillNotFoundError, skill_service


def summary(grant):
    if grant is None:
        return None
    return {"id": grant.id, "status": grant.status, "requested_by": grant.requested_by,
            "approved_by": grant.approved_by, "policy_revision": int(grant.policy_revision),
            "subject_revision": int(grant.subject_revision), "content_digest": grant.content_digest,
            "effective_at": grant.effective_at, "expires_at": grant.expires_at,
            "grant": grant.grant_json, "reason": grant.reason}


async def get_installation(db, identifier, *, lock=False):
    skill = await skill_service._find_skill(db, identifier)
    installation = await skill_service._installation(db, skill.id, for_update=lock) if skill else None
    if installation is None or installation.active_version is None:
        raise SkillNotFoundError(identifier)
    return installation


async def inspect_grant(db, identifier, actor_id):
    if not await has_role(db, actor_id, "skill_admin") and not await has_role(db, actor_id, "security_admin"):
        raise denied()
    installation = await get_installation(db, identifier)
    grant = await db.get(AuthorizationGrant, installation.authorization_grant_id) if installation.authorization_grant_id else None
    return {"installation_id": installation.id, "revision": installation.revision, "authorization": summary(grant),
            "can_request": await has_role(db, actor_id, "skill_admin"),
            "can_decide": await has_role(db, actor_id, "security_admin") and (grant is None or grant.requested_by != actor_id)}


async def request(db, identifier, actor_id, *, expected_revision, reason, expires_at):
    if not await has_role(db, actor_id, "skill_admin"):
        raise denied()
    installation = await get_installation(db, identifier, lock=True)
    skill_service._assert_revision(installation, expected_revision)
    version = installation.active_version
    await skill_service._verify_version_storage(db, version)
    cap, payload = await subject(db, installation, version)
    # A new request has a distinct revision even if capability content repeats.
    # Historical approvals/revocations remain immutable audit facts.
    cap.revision = int(cap.revision) + 1
    grant = await request_grant(db, requester_id=actor_id, target_type="skill_installation",
                                target_id=f"{installation.id}:{cap.revision}", grant=payload, reason=reason,
                                subject_revision=cap.revision, effective_at=datetime.now(UTC), expires_at=expires_at)
    installation.authorization_grant_id = grant.id
    installation.status = SkillInstallationStatus.DISABLED
    installation.settings = {**(installation.settings or {}), "default": False}
    installation.revision = int(installation.revision) + 1
    await record_audit(db, action="skill.authorization_requested", target_type="authorization_grant", target_id=grant.id,
                       actor_id=actor_id, actor_role="skill_admin", result="succeeded", reason=reason,
                       scope_type="global", scope_id="global", content_digest=grant.content_digest,
                       subject_revision=grant.subject_revision, policy_revision=grant.policy_revision,
                       after={"installation_id": installation.id, "status": "requested"})
    await skill_service._bump_registry(db, skill_id=installation.skill_id, event_type="skill_authorization_requested")
    await persist_service_write(db, lambda: skill_service._refresh_registry_after_commit(db, operation="authorization request"))
    return summary(grant)


async def decide(db, identifier, actor_id, grant_id, decision, *, expected_policy_revision,
                 expected_subject_revision, expected_content_digest, reason):
    installation = await get_installation(db, identifier, lock=True)
    if installation.authorization_grant_id != grant_id:
        raise SkillConflictError("Skill authorization request changed")
    if decision == "approve":
        grant = await approve_grant(db, approver_id=actor_id, grant_id=grant_id, reason=reason,
                                    expected_policy_revision=expected_policy_revision,
                                    expected_subject_revision=expected_subject_revision, expected_content_digest=expected_content_digest)
        await skill_service._verify_version_storage(db, installation.active_version)
        await authorized_grant(db, installation, installation.active_version, require_enabled=False)
    elif decision == "revoke":
        grant = await revoke_grant(db, revoker_id=actor_id, grant_id=grant_id, reason=reason,
                                   expected_policy_revision=expected_policy_revision,
                                   expected_subject_revision=expected_subject_revision, expected_content_digest=expected_content_digest)
        installation.status = SkillInstallationStatus.DISABLED
        installation.settings = {**(installation.settings or {}), "default": False}
    else:
        raise SkillConflictError("Unknown authorization decision")
    installation.revision = int(installation.revision) + 1
    await record_audit(db, action=f"skill.authorization_{decision}", target_type="authorization_grant", target_id=grant.id,
                       actor_id=actor_id, actor_role="security_admin", result="succeeded", reason=reason,
                       scope_type="global", scope_id="global", content_digest=grant.content_digest,
                       subject_revision=grant.subject_revision, policy_revision=grant.policy_revision,
                       after={"status": grant.status, "installation_id": installation.id})
    await skill_service._bump_registry(db, skill_id=installation.skill_id, event_type=f"skill_authorization_{decision}")
    await persist_service_write(db, lambda: skill_service._refresh_registry_after_commit(db, operation="authorization decision"))
    return summary(grant)
