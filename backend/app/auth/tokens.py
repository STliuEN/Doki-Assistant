from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from jose import JWTError, jwt

ACCESS_TOKEN_TTL_SECONDS = 15 * 60
REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60
REFRESH_COOKIE_NAME = "doki_refresh"
REFRESH_COOKIE_PATH = "/user/refresh-token/"
REFRESH_COOKIE_SAMESITE = "strict"

_INSECURE_SECRET_MARKERS = (
    "replace-with",
    "replace_with",
    "your-secret",
    "example",
    "change-me",
)


def auth_jwt_secret() -> str:
    value = os.getenv("AUTH_JWT_SECRET", "").strip()
    if len(value) < 32 or any(marker in value.casefold() for marker in _INSECURE_SECRET_MARKERS):
        raise RuntimeError("AUTH_JWT_SECRET must be an explicit non-placeholder secret of at least 32 characters")
    return value


def auth_jwt_issuer() -> str:
    return os.getenv("AUTH_JWT_ISSUER", "doki-e3-auth")


def auth_jwt_audience() -> str:
    return os.getenv("AUTH_JWT_AUDIENCE", "doki-api")


@dataclass(frozen=True, slots=True)
class RefreshMaterial:
    token: str
    jti: str
    token_digest: str
    jti_digest: str
    expires_at: datetime


def digest_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def issue_access_token(
    *,
    user_id: str,
    session_id: str,
    token_version: int,
    now: datetime | None = None,
    jti: str | None = None,
) -> tuple[str, datetime, str]:
    if not _canonical_uuid(user_id) or not _canonical_uuid(session_id):
        raise ValueError("access token subjects must be canonical lowercase UUIDs")
    issued_at = (now or datetime.now(UTC)).astimezone(UTC)
    expires_at = issued_at + timedelta(seconds=ACCESS_TOKEN_TTL_SECONDS)
    token_jti = jti or str(uuid4())
    claims = {
        "sub": user_id,
        "user_id": user_id,
        "iss": auth_jwt_issuer(),
        "aud": auth_jwt_audience(),
        "jti": token_jti,
        "sid": session_id,
        "ver": int(token_version),
        "token_type": "access",
        "iat": int(issued_at.timestamp()),
        "nbf": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(claims, auth_jwt_secret(), algorithm="HS256"), expires_at, token_jti


def decode_access_token(token: str) -> dict[str, object] | None:
    if not isinstance(token, str) or not token or len(token) > 4096:
        return None
    try:
        payload = jwt.decode(
            token,
            auth_jwt_secret(),
            algorithms=["HS256"],
            audience=auth_jwt_audience(),
            issuer=auth_jwt_issuer(),
            options={"require_sub": True, "require_iat": True, "require_nbf": True, "require_exp": True},
        )
    except JWTError:
        return None
    if payload.get("token_type") != "access":
        return None
    required_strings = ("sub", "user_id", "iss", "aud", "jti", "sid")
    if any(not isinstance(payload.get(key), str) or not str(payload[key]).strip() for key in required_strings):
        return None
    if payload.get("sub") != payload.get("user_id"):
        return None
    if any(not _canonical_uuid(payload.get(key)) for key in ("sub", "user_id", "jti", "sid")):
        return None
    version = payload.get("ver")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        return None
    for key in ("iat", "nbf", "exp"):
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            return None
    return payload


def new_refresh_material(*, now: datetime | None = None) -> RefreshMaterial:
    issued_at = (now or datetime.now(UTC)).astimezone(UTC)
    token = secrets.token_urlsafe(48)
    jti = str(uuid4())
    return RefreshMaterial(
        token=token,
        jti=jti,
        token_digest=digest_token(token),
        jti_digest=digest_token(jti),
        expires_at=issued_at + timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS),
    )
