from __future__ import annotations

import asyncio
import json

from app.services import pending_action_store


def _run(coroutine):
    return asyncio.run(coroutine)


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.set_calls = []
        self.deleted = []

    async def set(self, key, value, ex=None):
        self.values[key] = value
        self.set_calls.append((key, value, ex))

    async def get(self, key):
        return self.values.get(key)

    async def delete(self, key):
        self.deleted.append(key)
        self.values.pop(key, None)

    async def eval(self, _script, _numkeys, key, user_id):
        raw = self.values.get(key)
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            await self.delete(key)
            return None
        if payload.get("user_id") != user_id:
            return None
        await self.delete(key)
        return raw


def test_save_pending_action_uses_ttl_and_complete_identity(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(pending_action_store, "connect_redis", lambda: _async_value(redis))

    action_id = _run(pending_action_store.save_pending_action(
        user_id="u1",
        session_id="s1",
        tool_id="delete_memory",
        args={"memory_id": "m1"},
        run_id="run-1",
        registry_revision=7,
        tool_digest="a" * 64,
        ttl_seconds=42,
    ))

    key, raw, ttl = redis.set_calls[0]
    payload = json.loads(raw)
    assert key.endswith(action_id)
    assert ttl == 42
    assert payload["user_id"] == "u1"
    assert payload["session_id"] == "s1"
    assert payload["tool_id"] == "delete_memory"
    assert payload["run_id"] == "run-1"
    assert payload["registry_revision"] == 7
    assert payload["tool_digest"] == "a" * 64
    assert payload["provider_config_digest"] is None


def test_cross_user_take_is_rejected_without_consuming_action(monkeypatch):
    redis = FakeRedis()
    key = pending_action_store._key("a1")
    redis.values[key] = json.dumps({"id": "a1", "user_id": "owner"})
    monkeypatch.setattr(pending_action_store, "connect_redis", lambda: _async_value(redis))

    result = _run(pending_action_store.take_pending_action("a1", "attacker"))

    assert result is None
    assert key in redis.values
    assert redis.deleted == []


def test_owner_take_consumes_action_once(monkeypatch):
    redis = FakeRedis()
    key = pending_action_store._key("a1")
    redis.values[key] = json.dumps({"id": "a1", "user_id": "owner"})
    monkeypatch.setattr(pending_action_store, "connect_redis", lambda: _async_value(redis))

    first = _run(pending_action_store.take_pending_action("a1", "owner"))
    second = _run(pending_action_store.take_pending_action("a1", "owner"))

    assert first == {"id": "a1", "user_id": "owner"}
    assert second is None
    assert redis.deleted == [key]


def test_concurrent_owner_take_returns_action_once(monkeypatch):
    redis = FakeRedis()
    key = pending_action_store._key("a1")
    redis.values[key] = json.dumps({"id": "a1", "user_id": "owner"})
    monkeypatch.setattr(pending_action_store, "connect_redis", lambda: _async_value(redis))

    async def take_twice():
        return await asyncio.gather(
            pending_action_store.take_pending_action("a1", "owner"),
            pending_action_store.take_pending_action("a1", "owner"),
        )

    results = _run(take_twice())

    assert sum(result is not None for result in results) == 1
    assert key not in redis.values


def test_malformed_pending_action_is_deleted(monkeypatch):
    redis = FakeRedis()
    key = pending_action_store._key("broken")
    redis.values[key] = "not-json"
    monkeypatch.setattr(pending_action_store, "connect_redis", lambda: _async_value(redis))

    result = _run(pending_action_store.take_pending_action("broken", "owner"))

    assert result is None
    assert redis.deleted == [key]


async def _async_value(value):
    return value
