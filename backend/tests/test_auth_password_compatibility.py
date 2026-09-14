"""Known PBKDF2 vectors encoded in Django's persisted password format."""

import base64

import pytest

from app.auth.passwords import hash_password, validate_password_hash, verify_password


@pytest.mark.parametrize(
    ("algorithm", "derived_hex"),
    [
        ("sha1", "0c60c80f961f0e71f3a9b524af6012062fe037a6"),
        ("sha256", "120fb6cffcf8b32c43e7225256c4f837a86548c92ccc35480805987cb70be17b"),
    ],
)
def test_django_pbkdf2_known_vectors(algorithm, derived_hex):
    encoded = base64.b64encode(bytes.fromhex(derived_hex)).decode()
    stored = f"pbkdf2_{algorithm}$1$salt${encoded}"
    assert validate_password_hash(stored)
    assert verify_password(stored, "password").verified
    assert verify_password(stored, "password").needs_rehash
    assert not verify_password(stored, "wrong-password").verified


def test_rehashed_argon2_password_remains_verifiable():
    stored = hash_password("local-test-password")
    result = verify_password(stored, "local-test-password")
    assert result.verified and not result.needs_rehash
    assert not verify_password(stored, "wrong-password").verified


@pytest.mark.parametrize("stored", ["pbkdf2_sha256$0$salt$YWJj", "pbkdf2_sha1$99999999$salt$YWJj", "invalid"])
def test_invalid_legacy_hashes_fail_closed(stored):
    assert not verify_password(stored, "password").verified
