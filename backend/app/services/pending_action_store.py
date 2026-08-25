"""高风险工具的待确认动作存储（Redis + TTL）。

GuardedTool 命中 requires_confirmation 时写入一条 pending action，
前端确认后由 /chat/agent/confirm 端点取出并执行原工具。

设计约束（见 docs/roadmap_next.md 高风险确认闭环）：
- 过期：默认 600s TTL。
- 用户隔离：take 时校验 user_id 归属。
- 防重复提交：取出即删除（GETDEL），确认一次即消费。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app.core.logger_handler import logger
from app.db.redis_config import connect_redis

PENDING_ACTION_PREFIX = "pending_action:"
DEFAULT_TTL_SECONDS = 600
_TAKE_IF_OWNER_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then
    return nil
end
local ok, payload = pcall(cjson.decode, raw)
if not ok then
    redis.call('DEL', KEYS[1])
    return nil
end
if payload['user_id'] ~= ARGV[1] then
    return nil
end
redis.call('DEL', KEYS[1])
return raw
"""


def _key(action_id: str) -> str:
    return f"{PENDING_ACTION_PREFIX}{action_id}"


async def save_pending_action(
    user_id: str,
    session_id: str | None,
    tool_id: str,
    args: dict,
    *,
    run_id: str,
    registry_revision: int,
    tool_digest: str,
    provider_config_digest: str | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    source: str = "local",
    provider_id: str | None = None,
    external_name: str | None = None,
) -> str:
    """存入一条待确认动作，返回 pending_action_id。"""
    action_id = str(uuid.uuid4())
    payload = {
        "id": action_id,
        "user_id": user_id,
        "session_id": session_id,
        "tool_id": tool_id,
        "args": args,
        "source": source,
        "provider_id": provider_id,
        "external_name": external_name,
        "run_id": run_id,
        "registry_revision": registry_revision,
        "tool_digest": tool_digest,
        "provider_config_digest": provider_config_digest,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    redis = await connect_redis()
    await redis.set(_key(action_id), json.dumps(payload, ensure_ascii=False), ex=ttl_seconds)
    return action_id


async def take_pending_action(action_id: str, user_id: str) -> dict | None:
    """取出并消费一条待确认动作。

    返回 None 的情况：不存在 / 已过期 / 已被消费 / 不属于该用户。
    属于该用户时在一个 Lua 命令中校验并删除，保证只能被消费一次。
    """
    redis = await connect_redis()
    raw = await redis.eval(_TAKE_IF_OWNER_SCRIPT, 1, _key(action_id), user_id)
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as exc:
        logger.warning(f"【待确认动作】解析失败 {action_id}: {exc}")
        return None

    if payload.get("id") != action_id or payload.get("user_id") != user_id:
        logger.warning(f"【待确认动作】动作身份校验失败 {action_id}")
        return None
    return payload
