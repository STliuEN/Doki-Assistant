from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core import rate_limit as rate_limit_module


def _run(coroutine):
    return asyncio.run(coroutine)


def test_fixed_window_counter_uses_one_atomic_script_with_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRedis:
        def __init__(self) -> None:
            self.current = 0
            self.calls: list[tuple[str, int, str, int]] = []

        async def eval(self, script: str, key_count: int, key: str, window: int) -> int:
            self.calls.append((script, key_count, key, window))
            self.current += 1
            return self.current

    redis = FakeRedis()

    async def connect():
        return redis

    monkeypatch.setattr(rate_limit_module, "connect_redis", connect)

    assert _run(rate_limit_module._consume_rate_limit("rate:test", 2, 60)) is True
    assert _run(rate_limit_module._consume_rate_limit("rate:test", 2, 60)) is True
    assert _run(rate_limit_module._consume_rate_limit("rate:test", 2, 60)) is False
    assert [(count, key, window) for _, count, key, window in redis.calls] == [
        (1, "rate:test", 60),
        (1, "rate:test", 60),
        (1, "rate:test", 60),
    ]
    script = redis.calls[0][0]
    assert 'redis.call("SET", KEYS[1], 1, "EX", ARGV[1])' in script
    assert 'redis.call("TTL", KEYS[1])' in script


def test_dependency_fails_closed_when_redis_is_unavailable(monkeypatch):
    async def unavailable(*_args):
        raise RedisConnectionError("unavailable")

    monkeypatch.setattr(rate_limit_module, "_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(rate_limit_module, "_consume_rate_limit", unavailable)
    request = Request({"type": "http", "client": ("127.0.0.1", 1234), "headers": []})
    with pytest.raises(HTTPException) as error:
        _run(rate_limit_module.rate_limit()(request))
    assert error.value.status_code == 503


def test_middleware_redis_outage_keeps_health_observable_and_recovers(monkeypatch):
    available = False
    calls = []

    async def consume(*args):
        calls.append(args)
        if not available:
            raise RedisConnectionError("unavailable")
        return True

    monkeypatch.setattr(rate_limit_module, "_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(rate_limit_module, "_consume_rate_limit", consume)
    app = FastAPI()
    writes = []

    @app.get("/health/{probe}")
    async def health(probe: str):
        return {"probe": probe}

    @app.post("/business")
    async def business():
        writes.append(True)
        return {"ok": True}

    app.add_middleware(rate_limit_module.RateLimitMiddleware)
    with TestClient(app) as client:
        for probe in ("live", "ready", "runner"):
            assert client.get("/health/" + probe).status_code == 200
        assert not calls
        response = client.post("/business")
        assert response.status_code == 503
        assert response.json()["code"] == 503
        assert not writes
        available = True
        assert client.post("/business").status_code == 200
        assert writes == [True]
