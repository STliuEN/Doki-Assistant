from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from jose import jwt

from app.utils import auth_utils

TEST_SECRET = "test-jwt-secret-with-at-least-32-characters"
AUTH_CONTRACT_PATH = Path(__file__).resolve().parents[2] / "contracts" / "auth_access_token.json"


def _run(coroutine):
    return asyncio.run(coroutine)


def _token(
    token_type: str | None = "access",
    *,
    jti: str | None = "token-1",
    sid: str | None = "session-1",
    version: int | None = 1,
    omitted_claim: str | None = None,
) -> str:
    now = int(time.time())
    payload = {
        "user_id": "user-1",
        "iss": "doki-user-service",
        "aud": "doki-api",
        "iat": now,
        "nbf": now,
        "exp": now + 300,
    }
    if token_type is not None:
        payload["token_type"] = token_type
    if jti is not None:
        payload["jti"] = jti
    if sid is not None:
        payload["sid"] = sid
    if version is not None:
        payload["ver"] = version
    if omitted_claim is not None:
        payload.pop(omitted_claim, None)
    return jwt.encode(
        payload,
        TEST_SECRET,
        algorithm="HS256",
    )


@pytest.fixture(autouse=True)
def _jwt_config(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auth_utils, "SECRET_KEY", TEST_SECRET)
    monkeypatch.setattr(auth_utils, "ALGORITHM", "HS256")
    monkeypatch.setattr(auth_utils, "JWT_ISSUER", "doki-user-service")
    monkeypatch.setattr(auth_utils, "JWT_AUDIENCE", "doki-api")
    monkeypatch.setattr(auth_utils, "AUTH_STATE_VALIDATION_ENABLED", False)


def test_decode_accepts_access_and_rejects_refresh() -> None:
    assert auth_utils.decode_django_jwt(_token("access"))["user_id"] == "user-1"
    assert auth_utils.decode_django_jwt(_token("refresh")) is None


def test_fastapi_accepts_the_django_signed_contract_fixture() -> None:
    contract = json.loads(AUTH_CONTRACT_PATH.read_text(encoding="utf-8"))

    payload = auth_utils.decode_django_jwt(contract["token"])

    assert payload is not None
    assert {key: payload[key] for key in contract["claims"]} == contract["claims"]


def test_decode_rejects_access_tokens_without_required_revocation_claims() -> None:
    assert auth_utils.decode_django_jwt(_token(None)) is None
    assert auth_utils.decode_django_jwt(_token(jti=None)) is None
    assert auth_utils.decode_django_jwt(_token(sid=None)) is None
    assert auth_utils.decode_django_jwt(_token(version=None)) is None
    for claim in ("exp", "iat", "nbf"):
        assert auth_utils.decode_django_jwt(_token(omitted_claim=claim)) is None


def test_blacklist_lookup_uses_fixed_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[tuple[str, ...]] = []

    class FakeRedis:
        async def mget(self, *keys):
            captured.append(keys)
            return [None, None]

    async def connect():
        return FakeRedis()

    monkeypatch.setattr(auth_utils, "connect_auth_redis", connect)
    credentials = SimpleNamespace(credentials=_token(jti="fixed-jti"))

    assert _run(auth_utils.get_current_user_id(credentials)) == "user-1"
    assert captured == [("blacklist:fixed-jti", ":1:blacklist:fixed-jti")]


def test_revoked_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRedis:
        async def mget(self, *keys):
            return [None, "1"]

    async def connect():
        return FakeRedis()

    monkeypatch.setattr(auth_utils, "connect_auth_redis", connect)

    with pytest.raises(HTTPException) as exc_info:
        _run(auth_utils.get_current_user_id(SimpleNamespace(credentials=_token())))
    assert exc_info.value.status_code == 401


def test_blacklist_outage_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def connect():
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(auth_utils, "connect_auth_redis", connect)

    with pytest.raises(HTTPException) as exc_info:
        _run(auth_utils.get_current_user_id(SimpleNamespace(credentials=_token())))
    assert exc_info.value.status_code == 503
