from __future__ import annotations

import os

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.authorization import has_role
from app.auth.errors import AuthError
from app.auth.repository import AuthRepository
from app.auth.tokens import auth_jwt_secret, decode_access_token
from app.core.environment import is_production_environment, normalize_environment
from app.db.db_config import AsyncSessionLocal

security = HTTPBearer(auto_error=False)


def _is_insecure_secret(value: str | None) -> bool:
    if not value or len(value.strip()) < 32:
        return True
    normalized = value.strip().lower()
    return any(marker in normalized for marker in ("replace-with", "replace_with", "your-secret", "example"))


def validate_security_configuration() -> None:
    jwt_secret = auth_jwt_secret()
    environment = normalize_environment()
    if not is_production_environment(environment):
        return
    errors: list[str] = []
    model_secret = os.getenv("MODEL_CONFIG_ENCRYPTION_KEY")
    if _is_insecure_secret(model_secret):
        errors.append("MODEL_CONFIG_ENCRYPTION_KEY must be a non-placeholder secret of at least 32 characters")
    if jwt_secret and model_secret and jwt_secret == model_secret:
        errors.append("AUTH_JWT_SECRET and MODEL_CONFIG_ENCRYPTION_KEY must be different")
    if errors:
        raise RuntimeError("Invalid security configuration: " + "; ".join(errors))


async def get_current_auth(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict[str, object]:
    if credentials is None or not credentials.credentials:
        raise AuthError("AUTH_MISSING_TOKEN", "Authentication required", status_code=401)
    claims = decode_access_token(credentials.credentials)
    if claims is None:
        raise AuthError("AUTH_INVALID_TOKEN", "Authentication required", status_code=401)
    async with AsyncSessionLocal() as session:
        repository = AuthRepository(session)
        user = await repository.validate_access_claims(claims)
        profile = await repository.get_profile(user.id)
        request.state.e3_auth_user_id = str(user.id)
        await session.commit()
        return {"user": user, "profile": profile, "claims": claims}


async def get_current_user_id(principal: dict[str, object] = Depends(get_current_auth)) -> str:
    return str(principal["user"].id)


async def is_admin_user(user_id: str, credentials: HTTPAuthorizationCredentials | None = None) -> bool:
    del credentials
    async with AsyncSessionLocal() as session:
        return await has_role(session, user_id, "skill_admin") or await has_role(session, user_id, "security_admin")


async def require_admin_user(user_id: str = Depends(get_current_user_id)) -> str:
    if await is_admin_user(user_id):
        return user_id
    raise AuthError("AUTH_FORBIDDEN", "Administrator permission required", status_code=403)


async def require_security_admin(user_id: str = Depends(get_current_user_id)) -> str:
    async with AsyncSessionLocal() as session:
        if await has_role(session, user_id, "security_admin"):
            return user_id
    raise AuthError("AUTH_FORBIDDEN", "Security administrator permission required", status_code=403)


async def require_skill_admin(user_id: str = Depends(get_current_user_id)) -> str:
    async with AsyncSessionLocal() as session:
        if await has_role(session, user_id, "skill_admin"):
            return user_id
    raise AuthError("AUTH_FORBIDDEN", "Skill administrator permission required", status_code=403)
