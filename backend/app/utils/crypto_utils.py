import base64
import hashlib
import os
import warnings

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

load_dotenv()


def _resolve_secret(secret: str | None = None) -> str:
    if secret:
        return secret

    configured = os.getenv("MODEL_CONFIG_ENCRYPTION_KEY")
    if configured:
        return configured

    legacy = os.getenv("SECRET_KEY")
    if legacy:
        warnings.warn(
            "MODEL_CONFIG_ENCRYPTION_KEY is not set; using SECRET_KEY for backward compatibility",
            FutureWarning,
            stacklevel=3,
        )
        return legacy

    raise RuntimeError("MODEL_CONFIG_ENCRYPTION_KEY is required to encrypt model API keys")


def _get_fernet(secret: str | None = None) -> Fernet:
    secret = _resolve_secret(secret)
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_text(value: str | None, *, secret: str | None = None) -> str | None:
    if not value:
        return None
    return _get_fernet(secret).encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_text(
    value: str | None,
    *,
    secret: str | None = None,
    strict: bool = False,
) -> str:
    if not value:
        return ""
    try:
        return _get_fernet(secret).decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        if strict:
            raise ValueError("Unable to decrypt model API key with the configured key") from exc
        return ""


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}****{value[-4:]}"
