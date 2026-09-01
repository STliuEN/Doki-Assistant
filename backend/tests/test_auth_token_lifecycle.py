from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from jose import jwt

from app.auth.tokens import decode_access_token, issue_access_token

TEST_SECRET = "test-jwt-secret-with-at-least-32-characters"


@pytest.fixture(autouse=True)
def _jwt_config(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", TEST_SECRET)
    monkeypatch.setenv("AUTH_JWT_ISSUER", "doki-e3-auth")
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", "doki-api")


def _claims(**changes):
    now = int(datetime.now(UTC).timestamp())
    user_id = str(uuid4())
    values = {
        "sub": user_id,
        "user_id": user_id,
        "iss": "doki-e3-auth",
        "aud": "doki-api",
        "jti": str(uuid4()),
        "sid": str(uuid4()),
        "ver": 1,
        "token_type": "access",
        "iat": now,
        "nbf": now,
        "exp": now + 300,
    }
    values.update(changes)
    return values


def _token(**changes) -> str:
    return jwt.encode(_claims(**changes), TEST_SECRET, algorithm="HS256")


def test_e3_access_token_round_trip_uses_canonical_subjects() -> None:
    user_id = str(uuid4())
    session_id = str(uuid4())

    token, expires_at, jti = issue_access_token(
        user_id=user_id,
        session_id=session_id,
        token_version=3,
    )
    claims = decode_access_token(token)

    assert claims is not None
    assert claims["sub"] == claims["user_id"] == user_id
    assert claims["sid"] == session_id
    assert claims["jti"] == jti
    assert claims["ver"] == 3
    assert expires_at > datetime.now(UTC)


@pytest.mark.parametrize(
    "changes",
    [
        {"token_type": "refresh"},
        {"sub": "not-a-uuid", "user_id": "not-a-uuid"},
        {"sid": "not-a-uuid"},
        {"jti": "not-a-uuid"},
        {"ver": 0},
        {"ver": True},
    ],
)
def test_decode_rejects_invalid_e3_claims(changes: dict[str, object]) -> None:
    assert decode_access_token(_token(**changes)) is None


def test_decode_rejects_subject_mismatch_and_missing_claims() -> None:
    assert decode_access_token(_token(user_id=str(uuid4()))) is None
    claims = _claims()
    claims.pop("sid")
    token = jwt.encode(claims, TEST_SECRET, algorithm="HS256")
    assert decode_access_token(token) is None


def test_e3_secret_is_explicit_and_never_falls_back_to_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTH_JWT_SECRET", raising=False)
    monkeypatch.setenv("SECRET_KEY", "legacy-django-secret-that-must-not-authorize-e3")

    with pytest.raises(RuntimeError, match="AUTH_JWT_SECRET"):
        issue_access_token(user_id=str(uuid4()), session_id=str(uuid4()), token_version=1)


def test_issue_rejects_noncanonical_identifiers() -> None:
    with pytest.raises(ValueError, match="canonical lowercase UUIDs"):
        issue_access_token(user_id="user-1", session_id=str(uuid4()), token_version=1)
