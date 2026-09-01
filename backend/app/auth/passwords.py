from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import re
from dataclasses import dataclass

from argon2 import PasswordHasher, extract_parameters
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type

_PASSWORD_MAX_LENGTH = 1024
_PBKDF2_RE = re.compile(r"^(pbkdf2_(?P<algorithm>sha256|sha1))\$(?P<iterations>[0-9]+)\$(?P<salt>[^$]{1,128})\$(?P<digest>[A-Za-z0-9+/=_-]+)$")
_PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16)


@dataclass(frozen=True, slots=True)
class PasswordVerification:
    verified: bool
    needs_rehash: bool = False


def _password_bytes(password: str) -> bytes:
    if not isinstance(password, str) or not password or len(password) > _PASSWORD_MAX_LENGTH:
        raise ValueError("password must be a non-empty string of at most 1024 characters")
    return password.encode("utf-8")


def hash_password(password: str) -> str:
    return _PASSWORD_HASHER.hash(_password_bytes(password))


def _decode_django_digest(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    try:
        return base64.b64decode(padded.encode("ascii"), validate=True)
    except (ValueError, binascii.Error, UnicodeEncodeError) as exc:
        raise ValueError("password hash digest is malformed") from exc


def _verify_pbkdf2(stored_hash: str, password: str) -> PasswordVerification:
    match = _PBKDF2_RE.fullmatch(stored_hash)
    if match is None:
        return PasswordVerification(False)
    iterations = int(match.group("iterations"))
    if iterations < 1 or iterations > 10_000_000:
        return PasswordVerification(False)
    algorithm = match.group("algorithm")
    try:
        expected = _decode_django_digest(match.group("digest"))
    except ValueError:
        return PasswordVerification(False)
    if len(expected) not in {20, 32}:
        return PasswordVerification(False)
    actual = hashlib.pbkdf2_hmac(algorithm.removeprefix("sha"), _password_bytes(password), match.group("salt").encode("utf-8"), iterations)
    return PasswordVerification(hmac.compare_digest(actual, expected), True)


def validate_password_hash(stored_hash: str) -> bool:
    """Reject malformed or resource-amplifying hashes before verification/import."""

    if not isinstance(stored_hash, str) or not stored_hash or len(stored_hash) > 255:
        return False
    match = _PBKDF2_RE.fullmatch(stored_hash)
    if match is not None:
        iterations = int(match.group("iterations"))
        if not 1 <= iterations <= 10_000_000:
            return False
        try:
            digest = _decode_django_digest(match.group("digest"))
        except ValueError:
            return False
        expected_length = 32 if match.group("algorithm") == "sha256" else 20
        return len(digest) == expected_length
    if not stored_hash.startswith("$argon2id$"):
        return False
    try:
        parameters = extract_parameters(stored_hash)
    except InvalidHashError:
        return False
    return (
        parameters.type is Type.ID
        and 1 <= parameters.time_cost <= 10
        and 8 <= parameters.memory_cost <= 1_048_576
        and 1 <= parameters.parallelism <= 32
        and 16 <= parameters.hash_len <= 64
        and 8 <= parameters.salt_len <= 64
    )


def verify_password(stored_hash: str, password: str) -> PasswordVerification:
    """Verify Argon2id or the Django PBKDF2 formats without Django runtime."""

    if not validate_password_hash(stored_hash):
        return PasswordVerification(False)
    if stored_hash.startswith("$argon2id$"):
        try:
            verified = _PASSWORD_HASHER.verify(stored_hash, _password_bytes(password))
        except (VerifyMismatchError, VerificationError, InvalidHashError, ValueError):
            return PasswordVerification(False)
        return PasswordVerification(bool(verified), _PASSWORD_HASHER.check_needs_rehash(stored_hash))
    try:
        return _verify_pbkdf2(stored_hash, password)
    except ValueError:
        return PasswordVerification(False)
