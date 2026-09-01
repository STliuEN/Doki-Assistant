from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.errors import (
    AUTH_ACCOUNT_DISABLED,
    AUTH_ACCOUNT_LOCKED,
    AUTH_CONFLICT,
    AUTH_INVALID_CREDENTIALS,
    AUTH_REFRESH_INVALID,
    AUTH_REFRESH_REPLAY,
    AUTH_SESSION_INVALID,
    AUTH_VALIDATION,
    AuthError,
)
from app.auth.passwords import hash_password, verify_password
from app.auth.tokens import digest_token, issue_access_token, new_refresh_material
from app.models.identity_domain import AuthSession, AuthSessionMetadata, RefreshToken, TokenRevocation, User, UserProfile

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PHONE_RE = re.compile(r"^\+[1-9][0-9]{6,14}$")


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    session_id: str
    access_expires_at: datetime
    refresh_expires_at: datetime

    def as_dict(self, *, include_refresh: bool = False) -> dict[str, object]:
        value = {
            "token": self.access_token,
            "session_id": self.session_id,
            "expire_time": int(self.access_expires_at.timestamp()),
        }
        if include_refresh:
            value["refresh_token"] = self.refresh_token
        return value


def normalize_email(value: str) -> str:
    if not isinstance(value, str):
        raise AuthError(AUTH_VALIDATION, "Invalid email address", status_code=400)
    normalized = value.strip().casefold()
    if len(normalized) > 254 or not _EMAIL_RE.fullmatch(normalized):
        raise AuthError(AUTH_VALIDATION, "Invalid email address", status_code=400)
    return normalized


def normalize_username(value: str) -> str:
    if not isinstance(value, str):
        raise AuthError(AUTH_VALIDATION, "Invalid username", status_code=400)
    normalized = value.strip()
    if not 1 <= len(normalized) <= 150 or any(char.isspace() for char in normalized):
        raise AuthError(AUTH_VALIDATION, "Invalid username", status_code=400)
    return normalized


def normalize_phone(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise AuthError(AUTH_VALIDATION, "Invalid phone number", status_code=400)
    normalized = value.strip().replace(" ", "").replace("-", "")
    if not _PHONE_RE.fullmatch(normalized):
        raise AuthError(AUTH_VALIDATION, "Invalid phone number", status_code=400)
    return normalized


def _error_for_status(status: str) -> AuthError:
    if status == "disabled":
        return AuthError(AUTH_ACCOUNT_DISABLED, "Account is disabled", status_code=403)
    if status == "locked":
        return AuthError(AUTH_ACCOUNT_LOCKED, "Account is locked", status_code=403)
    return AuthError(AUTH_INVALID_CREDENTIALS, "Invalid credentials", status_code=401)


class AuthRepository:
    """SQL-only authentication operations; transaction ownership stays with the caller."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get_user_by_identifier(self, identifier: str) -> User | None:
        if not isinstance(identifier, str) or not identifier.strip():
            return None
        value = identifier.strip()
        email = value.casefold()
        result = await self.session.execute(select(User).where(or_(func.lower(User.username) == value.casefold(), User.email_normalized == email)))
        return result.scalar_one_or_none()

    async def get_user(self, user_id: str) -> User | None:
        return await self.session.get(User, user_id)

    async def get_profile(self, user_id: str, *, create: bool = False) -> UserProfile | None:
        profile = await self.session.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
        if profile is None and create:
            profile = UserProfile(user_id=user_id)
            self.session.add(profile)
            await self.session.flush()
        return profile

    @staticmethod
    def user_to_dict(user: User, profile: UserProfile | None = None) -> dict[str, object]:
        value: dict[str, object] = {
            "id": user.id,
            "user_id": user.id,
            "username": user.username,
            "email": user.email_display,
            "telephone": user.phone_display,
            "phone": user.phone_display,
            "status": user.status,
        }
        if profile is not None:
            value.update(
                {
                    "gender": profile.gender,
                    "bio": profile.bio,
                    "avatar": profile.avatar,
                    "last_login": profile.last_login.isoformat() if profile.last_login else None,
                }
            )
        return value

    async def create_user(
        self,
        *,
        username: str,
        email: str,
        password: str,
        telephone: str | None = None,
        gender: str | None = None,
        bio: str | None = None,
        avatar: str | None = None,
        user_id: str | None = None,
        password_hash_value: str | None = None,
        user_agent: str | None = None,
        device_label: str | None = None,
        ip_digest: str | None = None,
    ) -> tuple[User, UserProfile, IssuedTokens]:
        username = normalize_username(username)
        email_normalized = normalize_email(email)
        telephone = normalize_phone(telephone)
        if password_hash_value is None:
            if not isinstance(password, str) or not password:
                raise AuthError(AUTH_VALIDATION, "Password is required", status_code=400)
            password_hash_value = hash_password(password)
        if len(password_hash_value) > 255:
            raise AuthError(AUTH_VALIDATION, "Password hash is invalid", status_code=400)
        existing = await self.session.scalar(
            select(User).where(or_(func.lower(User.username) == username.casefold(), User.email_normalized == email_normalized))
        )
        if existing is not None:
            raise AuthError(AUTH_CONFLICT, "Account already exists", status_code=409)
        user = User(
            id=user_id or str(uuid4()),
            username=username,
            email_display=email.strip(),
            email_normalized=email_normalized,
            phone_display=telephone,
            phone_e164=telephone,
            password_hash=password_hash_value,
            status="active",
            token_version=1,
        )
        profile = UserProfile(
            user_id=user.id,
            gender=str(gender) if gender is not None else None,
            bio=bio,
            avatar=avatar,
        )
        self.session.add_all([user, profile])
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise AuthError(AUTH_CONFLICT, "Account already exists", status_code=409) from exc
        return (
            user,
            profile,
            await self._issue_session(
                user,
                user_agent=user_agent,
                device_label=device_label,
                ip_digest=ip_digest,
            ),
        )

    async def authenticate(
        self,
        identifier: str,
        password: str,
        *,
        user_agent: str | None = None,
        device_label: str | None = None,
        ip_digest: str | None = None,
    ) -> tuple[User, UserProfile, IssuedTokens]:
        user = await self._get_user_by_identifier(identifier)
        if user is None:
            raise _error_for_status("unknown")
        if user.status != "active":
            raise _error_for_status(user.status)
        verification = verify_password(user.password_hash, password)
        if not verification.verified:
            raise _error_for_status("unknown")
        if verification.needs_rehash:
            user.password_hash = hash_password(password)
        profile = await self.get_profile(user.id, create=True)
        profile.last_login = datetime.now(UTC)
        await self.session.flush()
        return (
            user,
            profile,
            await self._issue_session(
                user,
                user_agent=user_agent,
                device_label=device_label,
                ip_digest=ip_digest,
            ),
        )

    async def _issue_session(
        self,
        user: User,
        *,
        user_agent: str | None = None,
        device_label: str | None = None,
        ip_digest: str | None = None,
    ) -> IssuedTokens:
        now = datetime.now(UTC)
        session_id = str(uuid4())
        session = AuthSession(
            id=session_id,
            user_id=user.id,
            status="active",
            issued_token_version=int(user.token_version),
            expires_at=now + timedelta(seconds=30 * 24 * 60 * 60),
        )
        material = new_refresh_material(now=now)
        refresh = RefreshToken(
            session_id=session_id,
            family_id=session_id,
            token_digest=material.token_digest,
            jti_digest=material.jti_digest,
            status="active",
            expires_at=material.expires_at,
        )
        self.session.add(session)
        await self.session.flush()
        self.session.add(
            AuthSessionMetadata(
                session_id=session_id,
                user_agent=(user_agent or "")[:512] or None,
                device_label=(device_label or "")[:128] or None,
                ip_digest=ip_digest,
            )
        )
        self.session.add(refresh)
        await self.session.flush()
        access_token, access_expires_at, _ = issue_access_token(
            user_id=user.id,
            session_id=session.id,
            token_version=int(user.token_version),
            now=now,
        )
        return IssuedTokens(
            access_token=access_token,
            refresh_token=material.token,
            session_id=session.id,
            access_expires_at=access_expires_at,
            refresh_expires_at=material.expires_at,
        )

    async def validate_access_claims(self, claims: dict[str, object]) -> User:
        user_id = str(claims.get("sub", ""))
        session_id = str(claims.get("sid", ""))
        version = claims.get("ver")
        if not user_id or not session_id or isinstance(version, bool) or not isinstance(version, int):
            raise AuthError(AUTH_SESSION_INVALID, "Session is invalid", status_code=401)
        user = await self.session.get(User, user_id)
        session = await self.session.get(AuthSession, session_id)
        now = datetime.now(UTC)
        if user is None or session is None or session.user_id != user.id:
            raise AuthError(AUTH_SESSION_INVALID, "Session is invalid", status_code=401)
        if user.status != "active":
            raise _error_for_status(user.status)
        session_expires_at = _utc(session.expires_at)
        if (
            session.status != "active"
            or (session_expires_at is not None and session_expires_at <= now)
            or int(user.token_version) != version
            or int(session.issued_token_version) != version
        ):
            raise AuthError(AUTH_SESSION_INVALID, "Session is invalid", status_code=401)
        session.last_seen_at = now
        await self.session.flush()
        return user

    async def refresh(self, raw_token: str) -> tuple[User, IssuedTokens]:
        if not isinstance(raw_token, str) or not raw_token or len(raw_token) > 512:
            raise AuthError(AUTH_REFRESH_INVALID, "Refresh token is invalid", status_code=401)
        digest = digest_token(raw_token)
        token = await self.session.scalar(select(RefreshToken).where(RefreshToken.token_digest == digest).with_for_update())
        if token is None:
            raise AuthError(AUTH_REFRESH_INVALID, "Refresh token is invalid", status_code=401)
        now = datetime.now(UTC)
        token_expires_at = _utc(token.expires_at)
        if token.status != "active" or (token_expires_at is not None and token_expires_at <= now):
            if token.status == "consumed":
                await self._revoke_family(token.family_id, "refresh replay")
                session = await self.session.get(AuthSession, token.session_id)
                raise AuthError(
                    AUTH_REFRESH_REPLAY,
                    "Refresh token replay detected",
                    status_code=401,
                    audit_actor_id=session.user_id if session is not None else None,
                    audit_target_id=token.family_id,
                )
            raise AuthError(AUTH_REFRESH_INVALID, "Refresh token is invalid", status_code=401)
        session = await self.session.get(AuthSession, token.session_id, with_for_update=True)
        session_expires_at = _utc(session.expires_at) if session is not None else None
        if session is None or session.status != "active" or (session_expires_at is not None and session_expires_at <= now):
            raise AuthError(AUTH_SESSION_INVALID, "Session is invalid", status_code=401)
        user = await self.session.get(User, session.user_id, with_for_update=True)
        if user is None or user.status != "active" or int(user.token_version) != int(session.issued_token_version):
            raise AuthError(AUTH_SESSION_INVALID, "Session is invalid", status_code=401)
        material = new_refresh_material(now=now)
        child = RefreshToken(
            session_id=session.id,
            family_id=token.family_id,
            token_digest=material.token_digest,
            jti_digest=material.jti_digest,
            parent_token_id=token.id,
            status="active",
            expires_at=material.expires_at,
        )
        token.status = "consumed"
        token.consumed_at = now
        token.replaced_by_token_id = child.id
        token.revision = int(token.revision) + 1
        self.session.add(child)
        await self.session.flush()
        access_token, access_expires_at, _ = issue_access_token(
            user_id=user.id,
            session_id=session.id,
            token_version=int(user.token_version),
            now=now,
        )
        return user, IssuedTokens(
            access_token=access_token,
            refresh_token=material.token,
            session_id=session.id,
            access_expires_at=access_expires_at,
            refresh_expires_at=material.expires_at,
        )

    async def _revoke_family(self, family_id: str, reason: str) -> None:
        now = datetime.now(UTC)
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.status != "revoked")
            .values(status="revoked", revoked_at=now, revision=RefreshToken.revision + 1)
        )
        token = await self.session.scalar(select(RefreshToken).where(RefreshToken.family_id == family_id).limit(1))
        if token is None:
            return
        session = await self.session.get(AuthSession, token.session_id)
        if session is not None:
            session.status = "revoked"
            session.revoked_at = now
            session.revoke_reason = reason[:4096]
            await self._append_session_revocation(session, reason)
        await self.session.flush()

    async def _append_session_revocation(self, session: AuthSession, reason: str) -> None:
        existing = await self.session.scalar(
            select(TokenRevocation).where(TokenRevocation.scope_type == "session", TokenRevocation.scope_key == session.id)
        )
        if existing is None:
            self.session.add(
                TokenRevocation(
                    scope_type="session",
                    scope_key=session.id,
                    session_id=session.id,
                    user_id=session.user_id,
                    reason=reason[:4096],
                    expires_at=session.expires_at,
                )
            )

    async def logout(self, *, session_id: str | None = None, raw_refresh_token: str | None = None, reason: str = "logout") -> None:
        session = await self.session.get(AuthSession, session_id) if session_id else None
        if session is None and raw_refresh_token:
            token = await self.session.scalar(select(RefreshToken).where(RefreshToken.token_digest == digest_token(raw_refresh_token)))
            if token is not None:
                session = await self.session.get(AuthSession, token.session_id)
        if session is None:
            return
        now = datetime.now(UTC)
        session.status = "revoked"
        session.revoked_at = now
        session.revoke_reason = reason[:4096]
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.session_id == session.id, RefreshToken.status != "revoked")
            .values(status="revoked", revoked_at=now, revision=RefreshToken.revision + 1)
        )
        await self._append_session_revocation(session, reason)
        await self.session.flush()

    async def change_password(
        self,
        user: User,
        old_password: str,
        new_password: str,
        *,
        user_agent: str | None = None,
        device_label: str | None = None,
        ip_digest: str | None = None,
    ) -> IssuedTokens:
        verification = verify_password(user.password_hash, old_password)
        if not verification.verified:
            raise AuthError(AUTH_INVALID_CREDENTIALS, "Invalid credentials", status_code=401)
        if not isinstance(new_password, str) or len(new_password) < 8 or len(new_password) > 1024:
            raise AuthError(AUTH_VALIDATION, "Password does not meet requirements", status_code=400)
        user.password_hash = hash_password(new_password)
        user.token_version = int(user.token_version) + 1
        now = datetime.now(UTC)
        sessions = (await self.session.scalars(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.status == "active"))).all()
        for session in sessions:
            session.status = "revoked"
            session.revoked_at = now
            session.revoke_reason = "password changed"
            await self.session.execute(
                update(RefreshToken)
                .where(RefreshToken.session_id == session.id, RefreshToken.status != "revoked")
                .values(status="revoked", revoked_at=now, revision=RefreshToken.revision + 1)
            )
            await self._append_session_revocation(session, "password changed")
        self.session.add(
            TokenRevocation(
                scope_type="user_version",
                scope_key=f"{user.id}:{user.token_version}",
                user_id=user.id,
                token_version=int(user.token_version),
                reason="password changed",
            )
        )
        await self.session.flush()
        return await self._issue_session(
            user,
            user_agent=user_agent,
            device_label=device_label,
            ip_digest=ip_digest,
        )

    async def update_profile(self, user: User, values: dict[str, object]) -> UserProfile:
        profile = await self.get_profile(user.id, create=True)
        allowed = {"gender", "bio", "avatar"}
        for key, value in values.items():
            if key in allowed:
                if key == "bio" and value is not None and (not isinstance(value, str) or len(value) > 4096):
                    raise AuthError(AUTH_VALIDATION, "Invalid profile value", status_code=400)
                if key == "avatar" and value is not None and (not isinstance(value, str) or len(value) > 1024):
                    raise AuthError(AUTH_VALIDATION, "Invalid profile value", status_code=400)
                setattr(profile, key, None if value is None else str(value))
        await self.session.flush()
        return profile

    async def update_identity(
        self,
        user: User,
        *,
        username: str | None = None,
        telephone: str | None = None,
        update_username: bool = False,
        update_telephone: bool = False,
    ) -> None:
        new_username = normalize_username(username) if update_username and username is not None else user.username
        new_phone = normalize_phone(telephone) if update_telephone else user.phone_e164
        conditions = [func.lower(User.username) == new_username.casefold()]
        if new_phone is not None:
            conditions.append(User.phone_e164 == new_phone)
        conflict = await self.session.scalar(select(User.id).where(User.id != user.id, or_(*conditions)))
        if conflict is not None:
            raise AuthError(AUTH_CONFLICT, "Account identity already exists", status_code=409)
        if update_username:
            user.username = new_username
        if update_telephone:
            user.phone_display = new_phone
            user.phone_e164 = new_phone
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise AuthError(AUTH_CONFLICT, "Account identity already exists", status_code=409) from exc

    async def list_sessions(self, user_id: str) -> list[dict[str, object]]:
        rows = (await self.session.scalars(select(AuthSession).where(AuthSession.user_id == user_id).order_by(AuthSession.created_at.desc()))).all()
        metadata_rows = (
            (await self.session.scalars(select(AuthSessionMetadata).where(AuthSessionMetadata.session_id.in_([row.id for row in rows])))).all()
            if rows
            else []
        )
        metadata = {row.session_id: row for row in metadata_rows}
        now = datetime.now(UTC)
        return [
            {
                "session_id": row.id,
                "status": "expired" if row.status == "active" and _utc(row.expires_at) is not None and _utc(row.expires_at) <= now else row.status,
                "device_label": metadata.get(row.id).device_label if metadata.get(row.id) else None,
                "user_agent": metadata.get(row.id).user_agent if metadata.get(row.id) else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            }
            for row in rows
        ]

    async def revoke_session(self, user_id: str, session_id: str) -> None:
        session = await self.session.get(AuthSession, session_id)
        if session is None or session.user_id != user_id:
            raise AuthError(AUTH_SESSION_INVALID, "Session is invalid", status_code=404)
        await self.logout(session_id=session.id, reason="session revoked")
