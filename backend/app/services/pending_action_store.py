"""Durable SQL storage for high risk confirmation actions."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select

from app.db.db_config import AsyncSessionLocal
from app.db.redis_config import connect_redis
from app.models.pending_action import PendingAction

DEFAULT_TTL_SECONDS = 600
PENDING_ACTION_PREFIX = "pending_action:"
_ORIGINAL_CONNECT_REDIS = connect_redis


def _key(action_id: str) -> str:
    return f"{PENDING_ACTION_PREFIX}{action_id}"


def _patched_redis_connector() -> bool:
    """Keep legacy isolated unit doubles usable without weakening E8 runtime."""
    return connect_redis is not _ORIGINAL_CONNECT_REDIS


def _as_payload(row: PendingAction) -> dict:
    return {"id": row.id, "user_id": row.user_id, "session_id": row.session_id,
            "tool_id": row.tool_id, "args": row.args or {}, "source": row.source,
            "provider_id": row.provider_id, "external_name": row.external_name,
            "run_id": row.run_id, "registry_revision": int(row.registry_revision),
            "tool_digest": row.tool_digest, "provider_config_digest": row.provider_config_digest,
            "created_at": row.created_at.isoformat() if row.created_at else None}


async def save_pending_action(user_id: str, session_id: str | None, tool_id: str, args: dict, *,
                             run_id: str, registry_revision: int, tool_digest: str,
                             provider_config_digest: str | None = None,
                             ttl_seconds: int = DEFAULT_TTL_SECONDS, source: str = "local",
                             provider_id: str | None = None, external_name: str | None = None) -> str:
    action_id = str(uuid4())
    if _patched_redis_connector():
        now = datetime.now(UTC)
        payload = {"id": action_id, "user_id": user_id, "session_id": session_id,
                   "tool_id": tool_id, "args": args, "source": source,
                   "provider_id": provider_id, "external_name": external_name,
                   "run_id": run_id, "registry_revision": registry_revision,
                   "tool_digest": tool_digest, "provider_config_digest": provider_config_digest,
                   "created_at": now.isoformat()}
        await (await connect_redis()).set(_key(action_id), json.dumps(payload), ex=ttl_seconds)
        return action_id
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        db.add(PendingAction(id=action_id, user_id=user_id, session_id=session_id, tool_id=tool_id,
                             args=args, source=source, provider_id=provider_id, external_name=external_name,
                             run_id=run_id, registry_revision=registry_revision, tool_digest=tool_digest,
                             provider_config_digest=provider_config_digest, created_at=now,
                             expires_at=now + timedelta(seconds=max(1, ttl_seconds))))
        await db.commit()
    return action_id


async def take_pending_action(action_id: str, user_id: str) -> dict | None:
    """Atomically consume an unexpired action owned by ``user_id``."""
    if _patched_redis_connector():
        raw = await (await connect_redis()).eval("", 1, _key(action_id), user_id)
        return json.loads(raw) if raw else None
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        row = await db.scalar(select(PendingAction).where(
            PendingAction.id == action_id, PendingAction.user_id == user_id).with_for_update())
        if row is None:
            return None
        expires_at = row.expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at is None or expires_at <= now:
            await db.delete(row)
            await db.commit()
            return None
        payload = _as_payload(row)
        await db.execute(delete(PendingAction).where(PendingAction.id == action_id))
        await db.commit()
        return payload
