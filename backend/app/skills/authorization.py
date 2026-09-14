"""Live SQL authorization for A/limited-B Skills, independent of registry caches."""

import os
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import UTC, datetime

from sqlalchemy import select

from app.auth.authorization import POLICY_REVISION, _utc, content_digest, has_role
from app.auth.errors import AuthError
from app.models.identity_domain import AuthorizationGrant, User
from app.models.skill_domain import SkillCapabilityGrant, SkillInstallationStatus, SkillRunBinding

_AUTHORIZATION_SESSION = ContextVar("skill_authorization_session", default=None)


def live_checks_enabled():
    # Offline test/benchmark callers opt in to integration checks explicitly.
    return os.getenv("ENV", "dev").casefold() not in {"test", "testing"} or os.getenv("E6E7_ENABLED", "false").lower() == "true"


def denied(message="Skill authorization is missing, expired, revoked or changed"):
    return AuthError("SKILL_AUTHORIZATION_REQUIRED", message, status_code=403)


async def subject(db, installation, version):
    from app.skills.service import _effective_grants

    cap = await db.scalar(select(SkillCapabilityGrant).where(
        SkillCapabilityGrant.installation_id == installation.id,
        SkillCapabilityGrant.skill_version_id == version.id,
    ).execution_options(populate_existing=True))
    expected = _effective_grants(version, (installation.settings or {}).get("tools", []))
    if cap is None or cap.revoked_at is not None or cap.grants != expected:
        raise denied("Skill capability configuration changed")
    if not (version.manifest or {}).get("compatibility", {}).get("runtime_ready"):
        raise denied("Executable Skill packages remain unsupported")
    from app.agent.skill_registry import tool_registry

    for tool_id in expected["tools"]:
        try:
            tool = tool_registry.get(tool_id)
        except KeyError:
            raise denied("Skill contains an unavailable tool") from None
        if tool.source != "local" or not tool.enabled or not tool.available:
            raise denied("External or unavailable tools are unsupported in this stage")
    return cap, {"installation_id": installation.id, "skill_id": installation.skill_id,
                 "version_id": version.id, "package_digest": version.package_digest,
                 "scope_type": "global", "scope_id": "global", "capabilities": expected}


async def authorized_grant(db, installation, version, *, require_enabled=True):
    if require_enabled and installation.status != SkillInstallationStatus.ENABLED:
        raise denied()
    cap, payload = await subject(db, installation, version)
    grant = await db.scalar(select(AuthorizationGrant).where(
        AuthorizationGrant.id == installation.authorization_grant_id,
    ).with_for_update().execution_options(populate_existing=True))
    now = datetime.now(UTC)
    if (grant is None or grant.status != "approved" or not grant.approved_by
            or grant.approved_by == grant.requested_by or grant.policy_revision != POLICY_REVISION
            or grant.subject_revision != cap.revision or grant.grant_json != payload
            or grant.content_digest != content_digest(payload)
            or grant.target_type != "skill_installation"
            or grant.target_id != f"{installation.id}:{cap.revision}"
            or (grant.scope_type, grant.scope_id) != ("global", "global")
            or _utc(grant.effective_at) is None or _utc(grant.effective_at) > now
            or (grant.expires_at is not None and _utc(grant.expires_at) <= now)):
        raise denied()
    if not await has_role(db, grant.requested_by, "skill_admin") or not await has_role(db, grant.approved_by, "security_admin"):
        raise denied("An approving administrator no longer has the required role")
    for user_id in (grant.requested_by, grant.approved_by):
        user = await db.get(User, user_id, populate_existing=True)
        if user is None or user.status != "active":
            raise denied()
    return grant


def grant_snapshot(grant):
    return {"grant_id": grant.id, "policy_revision": int(grant.policy_revision),
            "subject_revision": int(grant.subject_revision), "content_digest": grant.content_digest,
            "expires_at": _utc(grant.expires_at).isoformat() if grant.expires_at else None}


async def validate_run(db, user_id, run_id, *, session_id=None, tool_id=None, skill_id=None, resource_path=None):
    from app.skills.service import skill_service

    user = await db.get(User, user_id, populate_existing=True)
    binding = await db.get(SkillRunBinding, run_id, populate_existing=True)
    if (user is None or user.status != "active" or binding is None or binding.user_id != user_id
            or binding.session_id != session_id):
        raise denied("Run owner or session does not match")
    grants = binding.effective_grants or {}
    sources = (grants.get("tool_grant_sources") or {}).get(tool_id, [])
    if tool_id and (tool_id not in grants.get("tools", []) or not sources):
        raise denied("Tool has no granted Skill source in this run")
    selected = set()
    for captured in binding.skill_bindings or []:
        installation = await skill_service._installation(db, captured["skill_id"], for_update=True)
        if installation is None or installation.active_version is None:
            raise denied()
        version = installation.active_version
        await skill_service._verify_version_storage(db, version)
        # Lock the approved row throughout the protected operation. Revoke and
        # lifecycle writes cannot interleave between the check and a side effect.
        await db.execute(select(AuthorizationGrant.id).where(
            AuthorizationGrant.id == installation.authorization_grant_id,
        ).with_for_update())
        grant = await authorized_grant(db, installation, version)
        if (captured.get("version_id") != version.id or captured.get("digest") != version.package_digest
                or captured.get("installation_revision") != int(installation.revision)
                or captured.get("authorization") != grant_snapshot(grant)
                or grants.get("skills", {}).get(installation.skill_id) != grant.grant_json["capabilities"]):
            raise denied("Run grant snapshot changed")
        selected.add(installation.skill_id)
        if skill_id == installation.skill_id and resource_path is not None:
            if resource_path not in grant.grant_json["capabilities"]["resources"]["read"]:
                raise denied("Resource is outside the approved capability set")
    if tool_id and not selected.intersection(sources):
        raise denied()
    if skill_id and skill_id not in selected:
        raise denied()
    return binding


@asynccontextmanager
async def execution_authority(*, tool_id=None, skill_id=None, resource_path=None):
    from app.agent.tool_context import (
        get_current_run_binding_from_context,
        get_current_session_id_from_context,
        get_current_user_id_from_context,
    )
    from app.db.db_config import AsyncSessionLocal

    owner = get_current_user_id_from_context()
    binding = get_current_run_binding_from_context() or {}
    if not owner or not binding.get("run_id"):
        raise denied("A durable SQL run binding is required")
    existing = _AUTHORIZATION_SESSION.get()
    if existing is not None:
        await validate_run(existing, owner, binding["run_id"], session_id=get_current_session_id_from_context(),
                           tool_id=tool_id, skill_id=skill_id, resource_path=resource_path)
        yield existing
        return
    async with AsyncSessionLocal() as db, db.begin():
        await validate_run(db, owner, binding["run_id"], session_id=get_current_session_id_from_context(),
                           tool_id=tool_id, skill_id=skill_id, resource_path=resource_path)
        token = _AUTHORIZATION_SESSION.set(db)
        try:
            yield db
        finally:
            _AUTHORIZATION_SESSION.reset(token)


@asynccontextmanager
async def job_authority(factory, payload):
    origin = payload.get("skill_origin")
    if not origin:
        yield
        return
    from app.jobs.runner import JobHandlerError
    try:
        async with factory() as db, db.begin():
            await validate_run(db, payload.get("owner_id"), origin.get("run_id"), session_id=origin.get("session_id"))
            yield
    except AuthError as exc:
        raise JobHandlerError("skill_authorization_revoked", "Job's originating Skill is no longer authorized", permanent=True) from exc
