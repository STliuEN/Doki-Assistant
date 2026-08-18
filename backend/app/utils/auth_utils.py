import json
import os
from pathlib import Path
from typing import Any

import httpx
import yaml
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.environment import is_production_environment, normalize_environment
from app.core.failed_response import logger
from app.db.redis_config import connect_auth_redis, connect_redis, set_redis_cache

load_dotenv()

# Django JWT配置
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
JWT_ISSUER = os.getenv("JWT_ISSUER", "doki-user-service")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "doki-api")
JWT_BLACKLIST_KEY_PREFIX = os.getenv("JWT_BLACKLIST_KEY_PREFIX", "blacklist").strip(": ") or "blacklist"
DJANGO_CACHE_VERSION = os.getenv("DJANGO_CACHE_VERSION", "1")
DJANGO_API_TIMEOUT_SECONDS = float(os.getenv("DJANGO_API_TIMEOUT_SECONDS", "5"))
AUTH_STATE_VALIDATION_ENABLED = os.getenv("AUTH_STATE_VALIDATION_ENABLED", "true").lower() == "true"
AUTH_STATE_CACHE_SECONDS = max(int(os.getenv("AUTH_STATE_CACHE_SECONDS", "15")), 1)

# 创建Bearer认证方案
security = HTTPBearer()

CONFIG_DIR = Path(__file__).parents[1] / "config"
SECURITY_EXAMPLE_CONFIG_PATH = CONFIG_DIR / "security.example.yaml"
SECURITY_LOCAL_CONFIG_PATH = CONFIG_DIR / "security.local.yaml"


def get_security_config_path() -> Path:
    configured = os.getenv("SECURITY_CONFIG_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    if SECURITY_LOCAL_CONFIG_PATH.exists():
        return SECURITY_LOCAL_CONFIG_PATH
    return SECURITY_EXAMPLE_CONFIG_PATH


def _is_insecure_secret(value: str | None) -> bool:
    if not value or len(value.strip()) < 32:
        return True
    normalized = value.strip().lower()
    return any(marker in normalized for marker in ("replace-with", "replace_with", "your-secret", "example"))


def validate_security_configuration() -> None:
    environment = normalize_environment()
    if not is_production_environment(environment):
        return

    errors: list[str] = []
    jwt_secret = os.getenv("SECRET_KEY")
    model_secret = os.getenv("MODEL_CONFIG_ENCRYPTION_KEY")
    if _is_insecure_secret(jwt_secret):
        errors.append("SECRET_KEY must be a non-placeholder secret of at least 32 characters")
    if _is_insecure_secret(model_secret):
        errors.append("MODEL_CONFIG_ENCRYPTION_KEY must be a non-placeholder secret of at least 32 characters")
    if jwt_secret and model_secret and jwt_secret == model_secret:
        errors.append("SECRET_KEY and MODEL_CONFIG_ENCRYPTION_KEY must be different")
    if not os.getenv("JWT_REDIS_URL", "").strip():
        errors.append("JWT_REDIS_URL must be explicitly configured in production")
    if not AUTH_STATE_VALIDATION_ENABLED:
        errors.append("AUTH_STATE_VALIDATION_ENABLED must be true in production")
    if errors:
        raise RuntimeError("Invalid security configuration: " + "; ".join(errors))


def decode_django_jwt(token: str) -> dict[str, Any] | None:
    """解析Django生成的JWT token

    Args:
        token: JWT token字符串

    Returns:
        解析后的payload，如果解析失败返回None
    """
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_aud": False},
        )
        for claim in ("user_id", "token_type", "iss", "aud", "jti", "sid"):
            value = payload.get(claim)
            if not isinstance(value, str) or not value.strip():
                return None
        version = payload.get("ver")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            return None
        for claim in ("exp", "iat", "nbf"):
            value = payload.get(claim)
            if isinstance(value, bool) or not isinstance(value, int):
                return None
        if payload.get("token_type") != "access":
            return None
        if payload.get("iss") != JWT_ISSUER:
            return None
        if payload.get("aud") != JWT_AUDIENCE:
            return None
        return payload
    except JWTError:
        return None


async def validate_token_state(token: str, jti: str, redis_client) -> None:
    """Confirm the token still authenticates in Django, with a short success cache."""
    if not AUTH_STATE_VALIDATION_ENABLED:
        return

    cache_key = f"auth_state:valid:{jti}"
    try:
        if await redis_client.get(cache_key):
            return
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token state cache unavailable",
        ) from exc

    django_base_url = os.getenv("DJANGO_API_URL", "http://127.0.0.1:18001").rstrip("/")
    timeout = httpx.Timeout(DJANGO_API_TIMEOUT_SECONDS)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                f"{django_base_url}/user/detail/",
                headers={"Authorization": f"Bearer {token}"},
            )
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User authentication service unavailable",
        ) from exc

    if response.status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token user state is no longer valid",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User authentication service returned an invalid response",
        )
    try:
        await redis_client.setex(cache_key, AUTH_STATE_CACHE_SECONDS, "1")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token state cache unavailable",
        ) from exc


async def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """从Django JWT中获取当前用户UUID

    Args:
        credentials: HTTP认证凭据

    Returns:
        用户的UUID

    Raises:
        HTTPException: 认证失败时抛出
    """
    token = credentials.credentials
    payload = decode_django_jwt(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 检查JWT是否在黑名单中
    jti = str(payload["jti"])
    try:
        redis_client = await connect_auth_redis()
        logical_key = f"{JWT_BLACKLIST_KEY_PREFIX}:{jti}"
        revoked_values = await redis_client.mget(
            logical_key,
            f":{DJANGO_CACHE_VERSION}:{logical_key}",
        )

        if any(revoked_values):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Redis blacklist lookup failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token revocation service unavailable",
        ) from e

    await validate_token_state(token, jti, redis_client)

    # 从Django JWT中提取user_id（uuid）
    user_id: str = payload.get("user_id")

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not find user ID in token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_id


def _split_env_list(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def _read_security_admins() -> tuple[set[str], set[str]]:
    config_path = get_security_config_path()
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning(f"读取安全配置失败，使用环境变量管理员名单: {exc}")
        data = {}

    admin_config = data.get("admin") if isinstance(data, dict) else {}
    if not isinstance(admin_config, dict):
        admin_config = {}

    user_ids = admin_config.get("user_ids") or []
    usernames = admin_config.get("usernames") or []

    config_user_ids = {str(item).strip() for item in user_ids if str(item).strip()} if isinstance(user_ids, list) else set()
    config_usernames = {str(item).strip() for item in usernames if str(item).strip()} if isinstance(usernames, list) else set()

    return (
        config_user_ids | _split_env_list(os.getenv("ADMIN_USER_IDS")),
        config_usernames | _split_env_list(os.getenv("ADMIN_USERNAMES")),
    )


async def require_admin_user(
    user_id: str = Depends(get_current_user_id),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Require a logged-in administrator.

    Administrators are configured in app/config/security.local.yaml.
    ADMIN_USER_IDS and ADMIN_USERNAMES can add deployment-specific admins.
    """
    if await is_admin_user(user_id, credentials):
        return user_id

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Administrator permission required",
    )


async def is_admin_user(user_id: str, credentials: HTTPAuthorizationCredentials) -> bool:
    """Return whether the current user is an administrator."""
    admin_user_ids, admin_usernames = _read_security_admins()

    if user_id in admin_user_ids:
        return True

    user_info = await get_user_info_from_redis(user_id, credentials)
    username = None
    if isinstance(user_info, dict):
        data = user_info.get("data") if isinstance(user_info.get("data"), dict) else user_info
        username = data.get("username")

    if username in admin_usernames:
        return True

    return False


async def fetch_user_info_from_django_api(token: str, url: str) -> dict[str, Any] | None:
    """从Django API获取用户信息

    Args:
        token: JWT token字符串

    Returns:
        用户信息字典，如果获取失败返回None
    """

    try:
        # 构建请求头
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        # 调用Django API
        timeout = httpx.Timeout(DJANGO_API_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url=url, headers=headers)

        if response.status_code == 200:
            user_data = response.json()
            logger.info("【debug】 从Django API获取用户信息成功", extra={"path": "auth_utils.fetch_user_info_from_django_api"})
            return user_data
        else:
            logger.error(
                f"【debug】 从Django API获取用户信息失败，status_code: {response.status_code}",
                extra={"path": "auth_utils.fetch_user_info_from_django_api"},
            )
            return None
    except Exception as e:
        logger.error(f"【debug】 调用Django API时出错: {str(e)}", extra={"path": "auth_utils.fetch_user_info_from_django_api"})
        return None


async def get_user_info_from_redis(user_id: str, credentials: HTTPAuthorizationCredentials):
    """从Redis中获取用户信息

    Args:
        user_id: 用户ID
        credentials: HTTP认证凭据

    Returns:
        用户信息
    """
    redis_client = await connect_redis()
    key = f":1:user:{user_id}"

    try:
        # 从Redis中获取用户信息
        user_info = await redis_client.get(key)
        if user_info is None:
            # 降级调用django查询用户信息
            user_data = await fetch_user_info_from_django_api(credentials.credentials, os.getenv("DJANGO_API_URL") + "/user/detail/")
            if user_data:
                # 将用户信息存入Redis，设置过期时间为1小时
                await set_redis_cache(
                    key,
                    user_data,
                    expire=3600
                )
                user_info = user_data
        else:
            # 如果从Redis中获取到数据，尝试将其解析为字典
            try:

                user_info = json.loads(user_info)
            except json.JSONDecodeError:
                # 如果解析失败，删除旧数据并重新获取
                await redis_client.delete(key)
                user_data = await fetch_user_info_from_django_api(credentials.credentials, os.getenv("DJANGO_API_URL") + "/user/detail/")
                if user_data:
                    await set_redis_cache(
                        key,
                        user_data,
                        expire=3600
                    )
                    user_info = user_data
                else:
                    user_info = None
    except UnicodeDecodeError:
        # 处理解码错误，删除旧数据并重新获取
        await redis_client.delete(key)
        user_data = await fetch_user_info_from_django_api(credentials.credentials, os.getenv("DJANGO_API_URL") + "/user/detail/")
        if user_data:
            await set_redis_cache(
                key,
                user_data,
                expire=3600
            )
            user_info = user_data
        else:
            user_info = None

    return user_info
