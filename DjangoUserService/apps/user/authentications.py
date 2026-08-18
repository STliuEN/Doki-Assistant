"""JWT authentication and access/refresh token lifecycle."""

import logging
import os
import time
import uuid

import jwt
from django.conf import settings
from django.core.cache import cache
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import APIException, AuthenticationFailed

from .models import User, UserStatusChoice

logger = logging.getLogger(__name__)

ExpiredSignatureError = jwt.ExpiredSignatureError
InvalidTokenError = getattr(jwt, "InvalidTokenError", Exception)

JWT_ALGORITHM = os.getenv("ALGORITHM", "HS256")
JWT_ISSUER = os.getenv("JWT_ISSUER", "doki-user-service")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "doki-api")
JWT_BLACKLIST_KEY_PREFIX = os.getenv("JWT_BLACKLIST_KEY_PREFIX", "blacklist").strip(": ") or "blacklist"
JWT_ACCESS_TTL_SECONDS = max(int(os.getenv("JWT_ACCESS_TTL_SECONDS", "900")), 60)
JWT_REFRESH_TTL_SECONDS = max(
    int(os.getenv("JWT_REFRESH_TTL_SECONDS", "2592000")),
    JWT_ACCESS_TTL_SECONDS,
)


def blacklist_key(jti: str) -> str:
    """Return the logical Django cache key for a revoked token."""
    return f"{JWT_BLACKLIST_KEY_PREFIX}:{jti}"


class TokenRevocationUnavailable(APIException):
    status_code = 503
    default_detail = "Token revocation service unavailable"
    default_code = "token_revocation_unavailable"


def decode_token(token: str, *, verify_exp: bool = True) -> dict:
    """Decode a token and require this service's issuer and audience."""
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[JWT_ALGORITHM],
        options={
            "verify_exp": verify_exp,
            "verify_iss": False,
            "verify_aud": False,
            "require": ["user_id", "token_type", "iss", "aud", "exp", "iat", "nbf", "jti", "sid", "ver"],
        },
    )
    if payload.get("iss") != JWT_ISSUER:
        raise InvalidTokenError("invalid issuer")
    if payload.get("aud") != JWT_AUDIENCE:
        raise InvalidTokenError("invalid audience")
    for claim in ("user_id", "token_type", "jti", "sid"):
        value = payload.get(claim)
        if not isinstance(value, str) or not value.strip():
            raise InvalidTokenError(f"invalid {claim}")
    version = payload.get("ver")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise InvalidTokenError("invalid token version")
    return payload


def is_token_blacklisted(jti: str) -> bool:
    try:
        return bool(cache.get(blacklist_key(jti)))
    except Exception as exc:
        logger.exception("JWT blacklist lookup failed")
        raise TokenRevocationUnavailable from exc


class JWTAuthentication(BaseAuthentication):
    """Authenticate access tokens and reject refresh credentials."""

    def authenticate(self, request) -> tuple[User, str] | None:
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return None

        try:
            auth_type, token = auth_header.split(" ", 1)
            if auth_type.lower() != "bearer" or not token.strip():
                raise AuthenticationFailed("Bearer token required")
        except ValueError as exc:
            raise AuthenticationFailed("Invalid Authorization header") from exc

        try:
            payload = decode_token(token)
        except ExpiredSignatureError as exc:
            raise AuthenticationFailed("Token expired") from exc
        except (InvalidTokenError, jwt.DecodeError) as exc:
            raise AuthenticationFailed("Invalid token") from exc
        except Exception as exc:
            raise AuthenticationFailed("Invalid token") from exc

        if payload.get("token_type") != "access":
            raise AuthenticationFailed("Access token required")

        jti = payload.get("jti")
        if not jti:
            raise AuthenticationFailed("Token missing jti")
        if is_token_blacklisted(str(jti)):
            raise AuthenticationFailed("Token revoked")

        user_id = payload.get("user_id")
        if not user_id:
            raise AuthenticationFailed("Token missing user ID")
        try:
            user = User.objects.get(uuid=user_id)
        except User.DoesNotExist as exc:
            raise AuthenticationFailed("User not found") from exc
        if user.status != UserStatusChoice.ACTIVE or not getattr(user, "is_active", True):
            raise AuthenticationFailed("User is not active")
        if payload["ver"] != int(getattr(user, "token_version", 1)):
            raise AuthenticationFailed("Token version is no longer valid")

        return user, token

    def authenticate_header(self, request) -> str:
        return "Bearer"


class JWTTokenGenerator:
    """Create, rotate, and revoke JWT access/refresh pairs."""

    @staticmethod
    def generate_token(
        user,
        *,
        token_type: str = "access",
        session_id: str | None = None,
    ) -> tuple[str, int]:
        if token_type not in {"access", "refresh"}:
            raise ValueError("Unsupported token type")
        now = int(time.time())
        ttl = JWT_ACCESS_TTL_SECONDS if token_type == "access" else JWT_REFRESH_TTL_SECONDS
        expire_time = now + ttl
        payload = {
            "user_id": str(user.uuid),
            "username": user.username,
            "email": user.email,
            "token_type": token_type,
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "exp": expire_time,
            "iat": now,
            "nbf": now,
            "jti": str(uuid.uuid4()),
            "sid": session_id or str(uuid.uuid4()),
            "ver": int(getattr(user, "token_version", 1)),
        }
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)
        if isinstance(token, bytes):
            token = token.decode("utf-8")
        return token, expire_time

    @staticmethod
    def generate_token_pair(user) -> dict[str, str | int]:
        session_id = str(uuid.uuid4())
        access_token, expire_time = JWTTokenGenerator.generate_token(
            user,
            token_type="access",
            session_id=session_id,
        )
        refresh_token, refresh_expire_time = JWTTokenGenerator.generate_token(
            user,
            token_type="refresh",
            session_id=session_id,
        )
        return {
            "token": access_token,
            "refresh_token": refresh_token,
            "expire_time": expire_time,
            "refresh_expire_time": refresh_expire_time,
        }

    @staticmethod
    def refresh_token(token: str) -> dict[str, str | int]:
        """Consume one refresh token and rotate it exactly once."""
        try:
            payload = decode_token(token, verify_exp=True)
            if payload.get("token_type") != "refresh":
                raise AuthenticationFailed("Refresh token required")

            user_id = payload.get("user_id")
            jti = payload.get("jti")
            if not user_id or not jti:
                raise AuthenticationFailed("Invalid refresh token")
            if is_token_blacklisted(str(jti)):
                raise AuthenticationFailed("Refresh token revoked")

            user = User.objects.get(uuid=user_id)
            if user.status != UserStatusChoice.ACTIVE or not getattr(user, "is_active", True):
                raise AuthenticationFailed("User is not active")
            if payload["ver"] != int(getattr(user, "token_version", 1)):
                raise AuthenticationFailed("Token version is no longer valid")

            # RedisCache.add is atomic. Concurrent replay cannot mint two pairs.
            if not JWTTokenGenerator.blacklist_token(token, once=True):
                raise AuthenticationFailed("Refresh token already used")
            return JWTTokenGenerator.generate_token_pair(user)
        except AuthenticationFailed:
            raise
        except TokenRevocationUnavailable:
            raise
        except ExpiredSignatureError as exc:
            raise AuthenticationFailed("Refresh token expired") from exc
        except (User.DoesNotExist, InvalidTokenError, jwt.DecodeError) as exc:
            raise AuthenticationFailed("Token refresh failed") from exc
        except Exception as exc:
            raise AuthenticationFailed("Token refresh failed") from exc

    @staticmethod
    def blacklist_token(token: str, *, once: bool = False) -> bool:
        """Revoke a token for the remaining lifetime of its exp claim."""
        try:
            payload = decode_token(token, verify_exp=False)
            jti = payload.get("jti")
            exp = int(payload.get("exp", 0))
            if not jti:
                return False
            ttl = max(exp - int(time.time()), 1)
            key = blacklist_key(str(jti))
        except Exception as exc:
            logger.warning("JWT blacklist rejected an invalid token: %s", exc)
            return False

        try:
            if once:
                return bool(cache.add(key, "1", timeout=ttl))
            cache.set(key, "1", timeout=ttl)
            return True
        except Exception as exc:
            logger.exception("JWT blacklist write failed")
            raise TokenRevocationUnavailable from exc
