from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.errors import AUTH_CONFLICT, AUTH_FORBIDDEN, AUTH_VALIDATION, AuthError
from app.models.identity_domain import AuthorizationGrant, Role, RoleBinding, User

ROLE_USER = "user"
ROLE_SKILL_ADMIN = "skill_admin"
ROLE_SECURITY_ADMIN = "security_admin"
GLOBAL_SCOPE_TYPE = "global"
GLOBAL_SCOPE_ID = "global"
POLICY_REVISION = 1


def content_digest(value: dict[str, object]) -> str:
    rendered = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _utc(value: datetime | None, *, require_timezone: bool = False) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        if require_timezone:
            raise AuthError(AUTH_VALIDATION, "Grant timestamps must include timezone", status_code=400)
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _grant_context(row: AuthorizationGrant) -> dict[str, object]:
    return {
        "scope_type": row.scope_type,
        "scope_id": row.scope_id,
        "policy_revision": int(row.policy_revision),
        "subject_revision": int(row.subject_revision),
        "content_digest": row.content_digest,
        "effective_at": row.effective_at,
        "expires_at": row.expires_at,
    }


def _validate_grant_snapshot(
    row: AuthorizationGrant,
    *,
    expected_policy_revision: int,
    expected_subject_revision: int,
    expected_content_digest: str,
    reject_expired: bool,
) -> None:
    actual_digest = content_digest(row.grant_json)
    if actual_digest != row.content_digest:
        raise AuthError(
            AUTH_CONFLICT,
            "Grant content digest drifted",
            status_code=409,
            audit_target_id=row.id,
            audit_context=_grant_context(row),
        )
    if (
        int(row.policy_revision) != POLICY_REVISION
        or int(row.policy_revision) != expected_policy_revision
        or int(row.subject_revision) != expected_subject_revision
        or row.content_digest != expected_content_digest
    ):
        raise AuthError(
            AUTH_CONFLICT,
            "Grant revision snapshot drifted",
            status_code=409,
            audit_target_id=row.id,
            audit_context=_grant_context(row),
        )
    expires_at = _utc(row.expires_at)
    if reject_expired and expires_at is not None and expires_at <= datetime.now(UTC):
        raise AuthError(
            AUTH_CONFLICT,
            "Grant expired before approval",
            status_code=409,
            audit_target_id=row.id,
            audit_context=_grant_context(row),
        )


async def has_role(
    session: AsyncSession,
    user_id: str,
    role_name: str,
    *,
    scope_type: str = GLOBAL_SCOPE_TYPE,
    scope_id: str = GLOBAL_SCOPE_ID,
) -> bool:
    now = datetime.now(UTC)
    row = await session.scalar(
        select(RoleBinding.id)
        .join(Role, Role.id == RoleBinding.role_id)
        .where(
            RoleBinding.user_id == user_id,
            Role.name == role_name,
            Role.status == "active",
            RoleBinding.status == "active",
            RoleBinding.scope_type == scope_type,
            RoleBinding.scope_id == scope_id,
            RoleBinding.effective_at <= now,
            (RoleBinding.expires_at.is_(None) | (RoleBinding.expires_at > now)),
        )
    )
    return row is not None


async def role_names(session: AsyncSession, user_id: str) -> set[str]:
    values = await session.scalars(
        select(Role.name)
        .join(RoleBinding, RoleBinding.role_id == Role.id)
        .where(
            RoleBinding.user_id == user_id,
            RoleBinding.status == "active",
            Role.status == "active",
            RoleBinding.scope_type == GLOBAL_SCOPE_TYPE,
            RoleBinding.scope_id == GLOBAL_SCOPE_ID,
        )
    )
    return set(values)


async def ensure_roles(session: AsyncSession) -> dict[str, Role]:
    descriptions = {
        ROLE_USER: "Default authenticated user",
        ROLE_SKILL_ADMIN: "Skill package administrator",
        ROLE_SECURITY_ADMIN: "Security and authorization administrator",
    }
    roles: dict[str, Role] = {}
    for name, description in descriptions.items():
        role = await session.scalar(select(Role).where(Role.name == name))
        if role is None:
            role = Role(id=str(uuid4()), name=name, description=description, status="active", revision=POLICY_REVISION)
            session.add(role)
            try:
                await session.flush()
            except IntegrityError as exc:
                raise AuthError(AUTH_CONFLICT, "Role bootstrap conflict", status_code=409) from exc
        roles[name] = role
    return roles


async def assign_default_user_role(session: AsyncSession, user_id: str) -> RoleBinding:
    roles = await ensure_roles(session)
    existing = await session.scalar(
        select(RoleBinding).where(
            RoleBinding.user_id == user_id,
            RoleBinding.role_id == roles[ROLE_USER].id,
            RoleBinding.scope_type == GLOBAL_SCOPE_TYPE,
            RoleBinding.scope_id == GLOBAL_SCOPE_ID,
        )
    )
    if existing is not None:
        return existing
    binding = RoleBinding(
        id=str(uuid4()),
        user_id=user_id,
        role_id=roles[ROLE_USER].id,
        scope_type=GLOBAL_SCOPE_TYPE,
        scope_id=GLOBAL_SCOPE_ID,
        status="active",
        revision=POLICY_REVISION,
    )
    session.add(binding)
    await session.flush()
    return binding


async def bootstrap_admins(session: AsyncSession, *, skill_admin_id: str, security_admin_id: str) -> dict[str, str]:
    if skill_admin_id == security_admin_id:
        raise AuthError(AUTH_VALIDATION, "Administrator identities must be different", status_code=400)
    users = {
        skill_admin_id: await session.get(User, skill_admin_id),
        security_admin_id: await session.get(User, security_admin_id),
    }
    if any(user is None or user.status != "active" for user in users.values()):
        raise AuthError(AUTH_VALIDATION, "Bootstrap users must be active", status_code=400)
    roles = await ensure_roles(session)
    existing_admin = await session.scalar(
        select(RoleBinding.id)
        .join(Role, Role.id == RoleBinding.role_id)
        .where(Role.name.in_([ROLE_SKILL_ADMIN, ROLE_SECURITY_ADMIN]), RoleBinding.status == "active")
    )
    if existing_admin is not None:
        raise AuthError(AUTH_CONFLICT, "Administrator bootstrap has already completed", status_code=409)
    for user_id, role_name in ((skill_admin_id, ROLE_SKILL_ADMIN), (security_admin_id, ROLE_SECURITY_ADMIN)):
        session.add(
            RoleBinding(
                id=str(uuid4()),
                user_id=user_id,
                role_id=roles[role_name].id,
                scope_type=GLOBAL_SCOPE_TYPE,
                scope_id=GLOBAL_SCOPE_ID,
                status="active",
                revision=POLICY_REVISION,
            )
        )
    await session.flush()
    return {"skill_admin_id": skill_admin_id, "security_admin_id": security_admin_id}


async def request_grant(
    session: AsyncSession,
    *,
    requester_id: str,
    target_type: str,
    target_id: str,
    grant: dict[str, object],
    reason: str,
    policy_revision: int = POLICY_REVISION,
    subject_revision: int = 1,
    effective_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> AuthorizationGrant:
    if not target_type or not target_id or not reason:
        raise AuthError(AUTH_VALIDATION, "Grant target and reason are required", status_code=400)
    if not isinstance(grant, dict) or not grant:
        raise AuthError(AUTH_VALIDATION, "Grant payload is invalid", status_code=400)
    if policy_revision != POLICY_REVISION:
        raise AuthError(AUTH_CONFLICT, "Grant policy revision drifted", status_code=409)
    effective_at = _utc(effective_at, require_timezone=True)
    expires_at = _utc(expires_at, require_timezone=True)
    if expires_at is not None and expires_at <= (effective_at or datetime.now(UTC)):
        raise AuthError(AUTH_VALIDATION, "Grant expiry must be after its effective time", status_code=400)
    if not await has_role(session, requester_id, ROLE_SKILL_ADMIN):
        raise AuthError(AUTH_FORBIDDEN, "Skill administrator permission required", status_code=403)
    row = AuthorizationGrant(
        id=str(uuid4()),
        target_type=target_type[:64],
        target_id=target_id[:255],
        scope_type=GLOBAL_SCOPE_TYPE,
        scope_id=GLOBAL_SCOPE_ID,
        requested_by=requester_id,
        grant_json=grant,
        policy_revision=policy_revision,
        subject_revision=subject_revision,
        content_digest=content_digest(grant),
        effective_at=effective_at,
        expires_at=expires_at,
        status="requested",
        reason=reason[:4096],
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise AuthError(AUTH_CONFLICT, "Equivalent grant already exists", status_code=409) from exc
    return row


async def approve_grant(
    session: AsyncSession,
    *,
    approver_id: str,
    grant_id: str,
    reason: str,
    expected_policy_revision: int,
    expected_subject_revision: int,
    expected_content_digest: str,
) -> AuthorizationGrant:
    if not await has_role(session, approver_id, ROLE_SECURITY_ADMIN):
        raise AuthError(AUTH_FORBIDDEN, "Security administrator permission required", status_code=403)
    row = await session.get(AuthorizationGrant, grant_id, with_for_update=True)
    if row is None or row.status != "requested":
        raise AuthError(AUTH_VALIDATION, "Grant is not awaiting approval", status_code=400)
    if row.requested_by == approver_id:
        raise AuthError(AUTH_FORBIDDEN, "Grant requester and approver must be different", status_code=403)
    _validate_grant_snapshot(
        row,
        expected_policy_revision=expected_policy_revision,
        expected_subject_revision=expected_subject_revision,
        expected_content_digest=expected_content_digest,
        reject_expired=True,
    )
    row.approved_by = approver_id
    row.status = "approved"
    row.effective_at = row.effective_at or datetime.now(UTC)
    row.reason = reason[:4096] or row.reason
    await session.flush()
    return row


async def revoke_grant(
    session: AsyncSession,
    *,
    revoker_id: str,
    grant_id: str,
    reason: str,
    expected_policy_revision: int,
    expected_subject_revision: int,
    expected_content_digest: str,
) -> AuthorizationGrant:
    if not await has_role(session, revoker_id, ROLE_SECURITY_ADMIN):
        raise AuthError(AUTH_FORBIDDEN, "Security administrator permission required", status_code=403)
    row = await session.get(AuthorizationGrant, grant_id, with_for_update=True)
    if row is None or row.status != "approved":
        raise AuthError(AUTH_VALIDATION, "Only an approved grant can be revoked", status_code=400)
    _validate_grant_snapshot(
        row,
        expected_policy_revision=expected_policy_revision,
        expected_subject_revision=expected_subject_revision,
        expected_content_digest=expected_content_digest,
        reject_expired=False,
    )
    row.revoked_by = revoker_id
    row.status = "revoked"
    row.reason = reason[:4096] or row.reason
    await session.flush()
    return row
