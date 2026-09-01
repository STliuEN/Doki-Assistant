from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, Depends, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.auth.audit import record_audit
from app.auth.authorization import (
    ROLE_SECURITY_ADMIN,
    ROLE_SKILL_ADMIN,
    approve_grant,
    assign_default_user_role,
    request_grant,
    revoke_grant,
    role_names,
)
from app.auth.errors import AUTH_VALIDATION, AuthError
from app.auth.repository import AuthRepository
from app.auth.tokens import REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH, REFRESH_COOKIE_SAMESITE, auth_jwt_secret, decode_access_token
from app.core.success_response import success_response
from app.db.db_config import AsyncSessionLocal
from app.db.uow import SqlUnitOfWork
from app.schemas.api import ApiResponse
from app.utils.auth_utils import get_current_auth, require_security_admin, security

user_router = APIRouter(tags=["user"], prefix="/user")


class RegisterPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=150)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=1024)
    confirm_password: str = Field(min_length=8, max_length=1024)
    telephone: str | None = Field(default=None, max_length=32)
    gender: str | None = Field(default=None, max_length=32)
    bio: str | None = Field(default=None, max_length=4096)


class LoginPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str | None = Field(default=None, min_length=1, max_length=254)
    email: str | None = Field(default=None, min_length=3, max_length=254)
    identifier: str | None = Field(default=None, min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class PasswordPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    old_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=8, max_length=1024)
    confirm_password: str = Field(min_length=8, max_length=1024)


class ProfilePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str | None = Field(default=None, min_length=1, max_length=150)
    telephone: str | None = Field(default=None, max_length=32)
    gender: str | None = Field(default=None, max_length=32)
    bio: str | None = Field(default=None, max_length=4096)
    avatar: str | None = Field(default=None, max_length=1024)


class GrantPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: str = Field(min_length=1, max_length=64)
    target_id: str = Field(min_length=1, max_length=255)
    grant: dict[str, object]
    reason: str = Field(min_length=1, max_length=4096)
    policy_revision: int = Field(default=1, ge=1)
    subject_revision: int = Field(default=1, ge=1)
    effective_at: datetime | None = None
    expires_at: datetime | None = None


class GrantDecisionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=4096)
    expected_policy_revision: int = Field(ge=1)
    expected_subject_revision: int = Field(ge=1)
    expected_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


def _correlation_id(request: Request) -> str:
    existing = getattr(request.state, "e3_correlation_id", None)
    if existing:
        return str(existing)
    candidate = request.headers.get("X-Correlation-ID")
    try:
        correlation_id = str(UUID(candidate)) if candidate else str(uuid4())
    except (ValueError, TypeError):
        correlation_id = str(uuid4())
    request.state.e3_correlation_id = correlation_id
    return correlation_id


def _set_refresh_cookie(response: Response, raw_token: str, expires_at: datetime) -> None:
    secure = os.getenv("AUTH_REFRESH_COOKIE_SECURE", "false").lower() == "true"
    max_age = max(0, int((expires_at - datetime.now(UTC)).total_seconds()))
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_token,
        max_age=max_age,
        expires=max_age,
        httponly=True,
        secure=secure,
        samesite=REFRESH_COOKIE_SAMESITE,
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH, samesite=REFRESH_COOKIE_SAMESITE)


def _request_metadata(request: Request) -> dict[str, str | None]:
    """Capture bounded session metadata without retaining the source IP."""

    user_agent = request.headers.get("user-agent")
    device_label = request.headers.get("x-device-label")
    host = request.client.host if request.client is not None else None
    ip_digest = None
    if host:
        ip_digest = hmac.new(
            auth_jwt_secret().encode("utf-8"),
            host.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    return {
        "user_agent": user_agent[:512] if user_agent else None,
        "device_label": device_label[:128] if device_label else None,
        "ip_digest": ip_digest,
    }


def _audit_target_type(action: str) -> str:
    if action.startswith(("grant.", "role.")):
        return "authorization_grant"
    if action.startswith(("auth.", "profile.", "password.", "session.")):
        return "user"
    return "system"


async def _record_failure(
    session,
    *,
    correlation_id: str,
    action: str,
    error: AuthError,
    actor_id: str | None = None,
    target_id: str | None = None,
) -> None:
    context = error.audit_context
    await record_audit(
        session,
        correlation_id=correlation_id,
        action=action,
        target_type=_audit_target_type(action),
        target_id=target_id,
        result="denied" if error.status_code == 403 else "failure",
        reason=error.message,
        actor_type="user" if actor_id else "anonymous",
        actor_id=actor_id,
        error_code=error.code,
        after={"status_code": error.status_code},
        scope_type=context.get("scope_type"),
        scope_id=context.get("scope_id"),
        policy_revision=context.get("policy_revision"),
        subject_revision=context.get("subject_revision"),
        content_digest=context.get("content_digest"),
        effective_at=context.get("effective_at"),
        expires_at=context.get("expires_at"),
    )


@asynccontextmanager
async def _auth_uow(request: Request, action: str) -> AsyncIterator[SqlUnitOfWork]:
    """Keep auth state changes and their failure audit in one caller-owned UoW."""

    correlation_id = _correlation_id(request)
    async with SqlUnitOfWork(AsyncSessionLocal) as uow:
        try:
            yield uow
        except AuthError as exc:
            session = uow.require_session()
            if not session.is_active:
                await session.rollback()
            await _record_failure(
                session,
                correlation_id=correlation_id,
                action=action,
                error=exc,
                actor_id=getattr(exc, "audit_actor_id", None) or getattr(request.state, "e3_auth_user_id", None),
                target_id=getattr(exc, "audit_target_id", None),
            )
            await uow.commit()
            request.state.e3_auth_audited = True
            raise


async def _record_success(
    session,
    *,
    correlation_id: str,
    action: str,
    actor_id: str | None,
    target_id: str | None,
    reason: str,
    before=None,
    after=None,
    actor_role: str | None = None,
    error_code: str | None = None,
    result: str = "success",
    scope_type: str | None = None,
    scope_id: str | None = None,
    policy_revision: int | None = None,
    subject_revision: int | None = None,
    content_digest: str | None = None,
    grant_diff=None,
    effective_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> None:
    await record_audit(
        session,
        correlation_id=correlation_id,
        action=action,
        target_type=_audit_target_type(action),
        target_id=target_id,
        result=result,
        reason=reason,
        actor_id=actor_id,
        actor_role=actor_role,
        before=before,
        after=after,
        error_code=error_code,
        scope_type=scope_type,
        scope_id=scope_id,
        policy_revision=policy_revision,
        subject_revision=subject_revision,
        content_digest=content_digest,
        grant_diff=grant_diff,
        effective_at=effective_at,
        expires_at=expires_at,
    )


def _grant_response(row) -> dict[str, object]:
    return {
        "grant_id": row.id,
        "status": row.status,
        "policy_revision": int(row.policy_revision),
        "subject_revision": int(row.subject_revision),
        "content_digest": row.content_digest,
        "effective_at": row.effective_at.isoformat() if row.effective_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
    }


@user_router.post("/register/", response_model=ApiResponse[object])
async def register(payload: RegisterPayload, request: Request, response: Response):
    correlation_id = _correlation_id(request)
    if payload.password != payload.confirm_password:
        raise AuthError(AUTH_VALIDATION, "Passwords do not match", status_code=400)
    metadata = _request_metadata(request)
    async with _auth_uow(request, "auth.register") as uow:
        repository = AuthRepository(uow.require_session())
        user, profile, tokens = await repository.create_user(
            username=payload.username,
            email=payload.email,
            password=payload.password,
            telephone=payload.telephone,
            gender=payload.gender,
            bio=payload.bio,
            **metadata,
        )
        await assign_default_user_role(uow.require_session(), user.id)
        await _record_success(
            uow.require_session(),
            correlation_id=correlation_id,
            action="auth.register",
            actor_id=user.id,
            target_id=user.id,
            reason="registration succeeded",
            after={"status": user.status},
        )
        await uow.commit()
    _set_refresh_cookie(response, tokens.refresh_token, tokens.refresh_expires_at)
    return success_response(
        message="registration succeeded",
        data={"token": tokens.access_token, "user": repository.user_to_dict(user, profile), "expire_time": int(tokens.access_expires_at.timestamp())},
        correlation_id=correlation_id,
    )


@user_router.post("/login/", response_model=ApiResponse[object])
async def login(payload: LoginPayload, request: Request, response: Response):
    correlation_id = _correlation_id(request)
    identifier = payload.identifier or payload.username or payload.email
    if not identifier:
        raise AuthError(AUTH_VALIDATION, "Username or email is required", status_code=400)
    metadata = _request_metadata(request)
    async with _auth_uow(request, "auth.login") as uow:
        repository = AuthRepository(uow.require_session())
        user, profile, tokens = await repository.authenticate(identifier, payload.password, **metadata)
        await _record_success(
            uow.require_session(),
            correlation_id=correlation_id,
            action="auth.login",
            actor_id=user.id,
            target_id=user.id,
            reason="login succeeded",
        )
        await uow.commit()
    _set_refresh_cookie(response, tokens.refresh_token, tokens.refresh_expires_at)
    return success_response(
        message="login succeeded",
        data={"token": tokens.access_token, "user": repository.user_to_dict(user, profile), "expire_time": int(tokens.access_expires_at.timestamp())},
        correlation_id=correlation_id,
    )


@user_router.post("/refresh-token/", response_model=ApiResponse[object])
async def refresh_token(request: Request, response: Response, doki_refresh: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME)):
    correlation_id = _correlation_id(request)
    if not doki_refresh:
        raise AuthError("AUTH_REFRESH_INVALID", "Refresh token is invalid", status_code=401)
    async with _auth_uow(request, "auth.refresh") as uow:
        repository = AuthRepository(uow.require_session())
        user, tokens = await repository.refresh(doki_refresh)
        await _record_success(
            uow.require_session(),
            correlation_id=correlation_id,
            action="auth.refresh",
            actor_id=user.id,
            target_id=user.id,
            reason="refresh rotation succeeded",
        )
        await uow.commit()
    _set_refresh_cookie(response, tokens.refresh_token, tokens.refresh_expires_at)
    return success_response(
        message="token refreshed",
        data={"token": tokens.access_token, "expire_time": int(tokens.access_expires_at.timestamp()), "session_id": tokens.session_id},
        correlation_id=correlation_id,
    )


@user_router.post("/logout/", response_model=ApiResponse[object])
async def logout(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    doki_refresh: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
):
    correlation_id = _correlation_id(request)
    session_id = None
    actor_id = None
    if credentials is not None:
        claims = decode_access_token(credentials.credentials)
        if claims is None:
            raise AuthError("AUTH_INVALID_TOKEN", "Authentication required", status_code=401)
        session_id = str(claims.get("sid"))
        actor_id = str(claims.get("sub"))
    elif not doki_refresh:
        raise AuthError("AUTH_MISSING_TOKEN", "Authentication required", status_code=401)
    async with _auth_uow(request, "auth.logout") as uow:
        repository = AuthRepository(uow.require_session())
        await repository.logout(session_id=session_id, raw_refresh_token=doki_refresh, reason="logout")
        await _record_success(
            uow.require_session(),
            correlation_id=correlation_id,
            action="auth.logout",
            actor_id=actor_id,
            target_id=session_id,
            reason="logout requested",
        )
        await uow.commit()
    _clear_refresh_cookie(response)
    return success_response(message="logout succeeded", correlation_id=correlation_id)


@user_router.get("/detail/", response_model=ApiResponse[object])
async def get_user_info(request: Request, principal: dict[str, object] = Depends(get_current_auth)):
    user = principal["user"]
    profile = principal.get("profile")
    correlation_id = _correlation_id(request)
    return success_response(data=AuthRepository.user_to_dict(user, profile), correlation_id=correlation_id)


@user_router.put("/update/", response_model=ApiResponse[object])
async def update_user(payload: ProfilePayload, request: Request, principal: dict[str, object] = Depends(get_current_auth)):
    correlation_id = _correlation_id(request)
    user_id = str(principal["user"].id)
    values = payload.model_dump(exclude_unset=True)
    async with _auth_uow(request, "profile.update") as uow:
        repository = AuthRepository(uow.require_session())
        user = await repository.get_user(user_id)
        if user is None:
            raise AuthError("AUTH_SESSION_INVALID", "Session is invalid", status_code=401)
        profile_values = {key: value for key, value in values.items() if key in {"gender", "bio", "avatar"}}
        profile = await repository.update_profile(user, profile_values)
        await repository.update_identity(
            user,
            username=values.get("username"),
            telephone=values.get("telephone"),
            update_username="username" in values,
            update_telephone="telephone" in values,
        )
        await _record_success(
            uow.require_session(),
            correlation_id=correlation_id,
            action="profile.update",
            actor_id=user.id,
            target_id=user.id,
            reason="profile updated",
            after=values,
        )
        await uow.commit()
    return success_response(message="profile updated", data={"user": repository.user_to_dict(user, profile)}, correlation_id=correlation_id)


@user_router.post("/reset-password/", response_model=ApiResponse[object])
async def reset_password(payload: PasswordPayload, request: Request, response: Response, principal: dict[str, object] = Depends(get_current_auth)):
    correlation_id = _correlation_id(request)
    if payload.new_password != payload.confirm_password:
        raise AuthError(AUTH_VALIDATION, "Passwords do not match", status_code=400)
    user_id = str(principal["user"].id)
    metadata = _request_metadata(request)
    async with _auth_uow(request, "password.change") as uow:
        repository = AuthRepository(uow.require_session())
        user = await repository.get_user(user_id)
        if user is None:
            raise AuthError("AUTH_SESSION_INVALID", "Session is invalid", status_code=401)
        tokens = await repository.change_password(user, payload.old_password, payload.new_password, **metadata)
        await _record_success(
            uow.require_session(),
            correlation_id=correlation_id,
            action="password.change",
            actor_id=user.id,
            target_id=user.id,
            reason="password changed",
        )
        await uow.commit()
    _set_refresh_cookie(response, tokens.refresh_token, tokens.refresh_expires_at)
    return success_response(
        message="password changed",
        data={"token": tokens.access_token, "expire_time": int(tokens.access_expires_at.timestamp())},
        correlation_id=correlation_id,
    )


@user_router.get("/sessions/", response_model=ApiResponse[object])
async def sessions(request: Request, principal: dict[str, object] = Depends(get_current_auth)):
    correlation_id = _correlation_id(request)
    async with AsyncSessionLocal() as session:
        repository = AuthRepository(session)
        values = await repository.list_sessions(str(principal["user"].id))
    return success_response(data={"sessions": values}, correlation_id=correlation_id)


@user_router.post("/sessions/{session_id}/revoke/", response_model=ApiResponse[object])
async def revoke_session(session_id: str, request: Request, principal: dict[str, object] = Depends(get_current_auth)):
    correlation_id = _correlation_id(request)
    user_id = str(principal["user"].id)
    async with _auth_uow(request, "session.revoke") as uow:
        repository = AuthRepository(uow.require_session())
        await repository.revoke_session(user_id, session_id)
        await _record_success(
            uow.require_session(),
            correlation_id=correlation_id,
            action="session.revoke",
            actor_id=user_id,
            target_id=session_id,
            reason="session revoked",
        )
        await uow.commit()
    return success_response(message="session revoked", correlation_id=correlation_id)


@user_router.post("/grants/", response_model=ApiResponse[object])
async def create_grant(payload: GrantPayload, request: Request, principal: dict[str, object] = Depends(get_current_auth)):
    correlation_id = _correlation_id(request)
    requester_id = str(principal["user"].id)
    async with _auth_uow(request, "grant.request") as uow:
        row = await request_grant(
            uow.require_session(),
            requester_id=requester_id,
            target_type=payload.target_type,
            target_id=payload.target_id,
            grant=payload.grant,
            reason=payload.reason,
            policy_revision=payload.policy_revision,
            subject_revision=payload.subject_revision,
            effective_at=payload.effective_at,
            expires_at=payload.expires_at,
        )
        roles = await role_names(uow.require_session(), requester_id)
        await _record_success(
            uow.require_session(),
            correlation_id=correlation_id,
            action="grant.request",
            actor_id=requester_id,
            target_id=row.id,
            actor_role=ROLE_SKILL_ADMIN if ROLE_SKILL_ADMIN in roles else None,
            reason=payload.reason,
            after={"status": row.status, "target_type": row.target_type, "target_id": row.target_id},
            scope_type=row.scope_type,
            scope_id=row.scope_id,
            policy_revision=int(row.policy_revision),
            subject_revision=int(row.subject_revision),
            content_digest=row.content_digest,
            grant_diff={"requested": row.grant_json},
            effective_at=row.effective_at,
            expires_at=row.expires_at,
        )
        await uow.commit()
    return success_response(message="grant requested", data=_grant_response(row), correlation_id=correlation_id)


@user_router.post("/grants/{grant_id}/approve/", response_model=ApiResponse[object])
async def approve_grant_route(grant_id: str, payload: GrantDecisionPayload, request: Request, approver_id: str = Depends(require_security_admin)):
    correlation_id = _correlation_id(request)
    async with _auth_uow(request, "grant.approve") as uow:
        row = await approve_grant(
            uow.require_session(),
            approver_id=approver_id,
            grant_id=grant_id,
            reason=payload.reason,
            expected_policy_revision=payload.expected_policy_revision,
            expected_subject_revision=payload.expected_subject_revision,
            expected_content_digest=payload.expected_content_digest,
        )
        await _record_success(
            uow.require_session(),
            correlation_id=correlation_id,
            action="grant.approve",
            actor_id=approver_id,
            target_id=row.id,
            actor_role=ROLE_SECURITY_ADMIN,
            reason=payload.reason or "grant approved",
            after={"status": row.status, "approved_by": approver_id},
            scope_type=row.scope_type,
            scope_id=row.scope_id,
            policy_revision=int(row.policy_revision),
            subject_revision=int(row.subject_revision),
            content_digest=row.content_digest,
            grant_diff={"approved": row.grant_json},
            effective_at=row.effective_at,
            expires_at=row.expires_at,
        )
        await uow.commit()
    return success_response(message="grant approved", data=_grant_response(row), correlation_id=correlation_id)


@user_router.post("/grants/{grant_id}/revoke/", response_model=ApiResponse[object])
async def revoke_grant_route(grant_id: str, payload: GrantDecisionPayload, request: Request, revoker_id: str = Depends(require_security_admin)):
    correlation_id = _correlation_id(request)
    async with _auth_uow(request, "grant.revoke") as uow:
        row = await revoke_grant(
            uow.require_session(),
            revoker_id=revoker_id,
            grant_id=grant_id,
            reason=payload.reason,
            expected_policy_revision=payload.expected_policy_revision,
            expected_subject_revision=payload.expected_subject_revision,
            expected_content_digest=payload.expected_content_digest,
        )
        await _record_success(
            uow.require_session(),
            correlation_id=correlation_id,
            action="grant.revoke",
            actor_id=revoker_id,
            target_id=row.id,
            actor_role=ROLE_SECURITY_ADMIN,
            reason=payload.reason or "grant revoked",
            after={"status": row.status, "revoked_by": revoker_id},
            scope_type=row.scope_type,
            scope_id=row.scope_id,
            policy_revision=int(row.policy_revision),
            subject_revision=int(row.subject_revision),
            content_digest=row.content_digest,
            grant_diff={"revoked": row.grant_json},
            effective_at=row.effective_at,
            expires_at=row.expires_at,
        )
        await uow.commit()
    return success_response(message="grant revoked", data=_grant_response(row), correlation_id=correlation_id)


@user_router.get("/audit/", response_model=ApiResponse[object])
async def audit_events(
    request: Request,
    correlation_id: UUID | None = Query(default=None),
    action: str | None = Query(default=None, min_length=1, max_length=128, pattern=r"^[a-z0-9_.-]+$"),
    limit: int = Query(default=200, ge=1, le=200),
    security_admin_id: str = Depends(require_security_admin),
):
    response_correlation_id = _correlation_id(request)
    from app.models.job_domain import AuditEvent

    async with AsyncSessionLocal() as session:
        statement = select(AuditEvent)
        if correlation_id is not None:
            statement = statement.where(AuditEvent.correlation_id == str(correlation_id))
        if action is not None:
            statement = statement.where(AuditEvent.action == action)
        rows = (await session.scalars(statement.order_by(AuditEvent.created_at.desc()).limit(limit))).all()
        await record_audit(
            session,
            correlation_id=response_correlation_id,
            actor_id=security_admin_id,
            actor_role=ROLE_SECURITY_ADMIN,
            action="audit.read",
            target_type="audit_event",
            target_id=str(correlation_id) if correlation_id else None,
            result="success",
            reason="audit events queried",
            after={"action_filter": action, "returned_count": len(rows)},
        )
        await session.commit()
    return success_response(
        data={
            "events": [
                {
                    "id": row.id,
                    "action": row.action,
                    "target_type": row.target_type,
                    "target_id": row.target_id,
                    "result": row.result,
                    "error_code": row.error_code,
                    "correlation_id": row.correlation_id,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ],
            "viewer": security_admin_id,
        },
        correlation_id=response_correlation_id,
    )
