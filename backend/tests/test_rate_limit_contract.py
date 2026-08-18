from __future__ import annotations

import asyncio

import pytest

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
