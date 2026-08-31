from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.e2.common import (
    ascii_text,
    canonical_uuid,
    database_now,
    digest,
    generated_or_canonical_uuid,
    required_text,
    utc_datetime,
)
from app.e2.errors import E2PrimitiveConflictError, E2PrimitiveValidationError
from app.models.identity_domain import AuthSession, RefreshToken, Role, RoleBinding, TokenRevocation, User


class SyntheticAuthRepository:
    """Small auth-state primitives for E2 fixtures only.

    The repository stores caller-supplied digests and synthetic identifiers; it
    never signs tokens, reads Redis, imports users, or decides product access.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_user(
        self,
        *,
        email_normalized: str,
        password_hash: str = "synthetic-password-hash",
        email_display: str | None = None,
        username: str = "synthetic-user",
        phone_e164: str | None = None,
        user_id: str | None = None,
        token_version: int = 1,
    ) -> User:
        email_normalized = required_text(email_normalized, "email_normalized", 254)
        password_hash = required_text(password_hash, "password_hash", 255)
        username = required_text(username, "username", 150)
        if not isinstance(token_version, int) or token_version <= 0:
            raise E2PrimitiveValidationError("token_version must be positive")
        if phone_e164 is not None:
            phone_e164 = ascii_text(phone_e164, "phone_e164", 32)
        existing = await self.session.scalar(select(User).where(User.email_normalized == email_normalized))
        if existing is not None:
            raise E2PrimitiveConflictError("synthetic user email_normalized already exists")
        user = User(
            id=generated_or_canonical_uuid(user_id, "user_id"),
            username=username,
            email_display=email_display or email_normalized,
            email_normalized=email_normalized,
            phone_display=phone_e164,
            phone_e164=phone_e164,
            password_hash=password_hash,
            token_version=token_version,
        )
        self.session.add(user)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError as exc:
            raise E2PrimitiveConflictError("synthetic user uniqueness constraint rejected the insert") from exc
        return user

    async def create_session(
        self,
        *,
        user_id: str,
        expires_at: datetime,
        session_id: str | None = None,
        issued_token_version: int | None = None,
    ) -> AuthSession:
        user_id = canonical_uuid(user_id, "user_id")
        expires_at = utc_datetime(expires_at, "expires_at")
        if expires_at <= await database_now(self.session):
            raise E2PrimitiveValidationError("expires_at must be in the future")
        user = await self.session.get(User, user_id)
        if user is None:
            raise E2PrimitiveValidationError("synthetic session user does not exist")
        if user.status != "active":
            raise E2PrimitiveValidationError("synthetic session user is not active")
        token_version = int(user.token_version) if issued_token_version is None else issued_token_version
        if not isinstance(token_version, int) or token_version <= 0:
            raise E2PrimitiveValidationError("issued_token_version must be positive")
        session = AuthSession(
            id=generated_or_canonical_uuid(session_id, "session_id"),
            user_id=user_id,
            issued_token_version=token_version,
            expires_at=expires_at,
        )
        self.session.add(session)
        await self.session.flush()
        return session

    async def issue_refresh_token(
        self,
        *,
        session_id: str,
        token_digest: str,
        jti_digest: str,
        expires_at: datetime,
        family_id: str | None = None,
        parent_token_id: str | None = None,
        token_id: str | None = None,
    ) -> RefreshToken:
        session_id = canonical_uuid(session_id, "session_id")
        token_digest = digest(token_digest, "token_digest")
        jti_digest = digest(jti_digest, "jti_digest")
        expires_at = utc_datetime(expires_at, "expires_at")
        if expires_at <= await database_now(self.session):
            raise E2PrimitiveValidationError("expires_at must be in the future")
        auth_session = await self.session.get(AuthSession, session_id)
        if auth_session is None or auth_session.status != "active":
            raise E2PrimitiveValidationError("synthetic refresh token session is not active")
        parent = None
        if parent_token_id is not None:
            parent_token_id = canonical_uuid(parent_token_id, "parent_token_id")
            parent = await self.session.get(RefreshToken, parent_token_id)
            if parent is None:
                raise E2PrimitiveValidationError("parent_token_id does not exist")
            if parent.session_id != session_id:
                raise E2PrimitiveValidationError("parent refresh token belongs to another session")
        token = RefreshToken(
            id=generated_or_canonical_uuid(token_id, "token_id"),
            session_id=session_id,
            family_id=generated_or_canonical_uuid(family_id, "family_id"),
            token_digest=token_digest,
            jti_digest=jti_digest,
            parent_token_id=parent_token_id,
            expires_at=expires_at,
        )
        self.session.add(token)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError as exc:
            raise E2PrimitiveConflictError("synthetic refresh token uniqueness constraint rejected the insert") from exc
        return token

    async def rotate_refresh_token(
        self,
        *,
        parent_token_id: str,
        token_digest: str,
        jti_digest: str,
        expires_at: datetime,
        token_id: str | None = None,
    ) -> RefreshToken:
        parent_token_id = canonical_uuid(parent_token_id, "parent_token_id")
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.id == parent_token_id).with_for_update()
        )
        parent = result.scalar_one_or_none()
        if parent is None:
            raise E2PrimitiveValidationError("parent_token_id does not exist")
        now = await database_now(self.session)
        if parent.status != "active" or parent.expires_at <= now:
            raise E2PrimitiveConflictError("parent refresh token is not active")
        child = await self.issue_refresh_token(
            session_id=parent.session_id,
            family_id=parent.family_id,
            parent_token_id=parent.id,
            token_digest=token_digest,
            jti_digest=jti_digest,
            expires_at=expires_at,
            token_id=token_id,
        )
        parent.status = "consumed"
        parent.consumed_at = now
        parent.replaced_by_token_id = child.id
        parent.revision = int(parent.revision) + 1
        await self.session.flush()
        return child

    async def revoke(
        self,
        *,
        scope_type: str,
        scope_key: str,
        reason: str,
        token_digest: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        token_version: int | None = None,
        correlation_id: str | None = None,
        expires_at: datetime | None = None,
    ) -> TokenRevocation:
        scope_type = ascii_text(scope_type, "scope_type", 32)
        if scope_type not in {"token", "session", "user_version"}:
            raise E2PrimitiveValidationError("scope_type must be token, session, or user_version")
        scope_key = required_text(scope_key, "scope_key", 160)
        reason = required_text(reason, "reason", 4096)
        if token_digest is not None:
            token_digest = digest(token_digest, "token_digest")
        if session_id is not None:
            session_id = canonical_uuid(session_id, "session_id")
        if user_id is not None:
            user_id = canonical_uuid(user_id, "user_id")
        if token_version is not None and (not isinstance(token_version, int) or token_version <= 0):
            raise E2PrimitiveValidationError("token_version must be positive")
        if correlation_id is not None:
            correlation_id = canonical_uuid(correlation_id, "correlation_id")
        if expires_at is not None:
            expires_at = utc_datetime(expires_at, "expires_at")
        required_fields = {
            "token": token_digest is not None,
            "session": session_id is not None,
            "user_version": user_id is not None and token_version is not None,
        }
        if not required_fields[scope_type]:
            raise E2PrimitiveValidationError(f"{scope_type} revocation requires its matching identity fields")
        existing = await self.session.scalar(
            select(TokenRevocation).where(TokenRevocation.scope_type == scope_type, TokenRevocation.scope_key == scope_key)
        )
        if existing is not None:
            if existing.reason != reason:
                raise E2PrimitiveConflictError("synthetic revocation scope already has a different reason")
            return existing
        revocation = TokenRevocation(
            id=generated_or_canonical_uuid(None, "revocation_id"),
            scope_type=scope_type,
            scope_key=scope_key,
            token_digest=token_digest,
            session_id=session_id,
            user_id=user_id,
            token_version=token_version,
            reason=reason,
            correlation_id=correlation_id,
            expires_at=expires_at,
        )
        self.session.add(revocation)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError as exc:
            raise E2PrimitiveConflictError("synthetic revocation uniqueness constraint rejected the insert") from exc
        return revocation

    async def create_role(self, *, name: str, description: str = "synthetic role", role_id: str | None = None) -> Role:
        name = ascii_text(name, "role name", 64)
        description = required_text(description, "description", 512)
        existing = await self.session.scalar(select(Role).where(Role.name == name))
        if existing is not None:
            raise E2PrimitiveConflictError("synthetic role already exists")
        role = Role(id=generated_or_canonical_uuid(role_id, "role_id"), name=name, description=description)
        self.session.add(role)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError as exc:
            raise E2PrimitiveConflictError("synthetic role uniqueness constraint rejected the insert") from exc
        return role

    async def bind_role(
        self,
        *,
        user_id: str,
        role_id: str,
        scope_type: str = "global",
        scope_id: str = "global",
        effective_at: datetime | None = None,
        expires_at: datetime | None = None,
        binding_id: str | None = None,
    ) -> RoleBinding:
        user_id = canonical_uuid(user_id, "user_id")
        role_id = canonical_uuid(role_id, "role_id")
        scope_type = ascii_text(scope_type, "scope_type", 32)
        scope_id = ascii_text(scope_id, "scope_id", 64)
        if await self.session.get(User, user_id) is None:
            raise E2PrimitiveValidationError("synthetic role binding user does not exist")
        if await self.session.get(Role, role_id) is None:
            raise E2PrimitiveValidationError("synthetic role binding role does not exist")
        effective = utc_datetime(effective_at, "effective_at") if effective_at else await database_now(self.session)
        expires = utc_datetime(expires_at, "expires_at") if expires_at else None
        if expires is not None and expires <= effective:
            raise E2PrimitiveValidationError("expires_at must be after effective_at")
        existing = await self.session.scalar(
            select(RoleBinding).where(
                RoleBinding.user_id == user_id,
                RoleBinding.role_id == role_id,
                RoleBinding.scope_type == scope_type,
                RoleBinding.scope_id == scope_id,
            )
        )
        if existing is not None:
            return existing
        binding = RoleBinding(
            id=generated_or_canonical_uuid(binding_id, "binding_id"),
            user_id=user_id,
            role_id=role_id,
            scope_type=scope_type,
            scope_id=scope_id,
            effective_at=effective,
            expires_at=expires,
        )
        self.session.add(binding)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError as exc:
            raise E2PrimitiveConflictError("synthetic role binding uniqueness constraint rejected the insert") from exc
        return binding
