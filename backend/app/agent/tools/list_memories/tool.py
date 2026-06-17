from langchain_core.tools import tool

from app.agent.tool_context import get_current_user_id_from_context
from app.core.logger_handler import logger
from app.db.db_config import AsyncSessionLocal
from app.services.memory_service import memory_service


@tool(
    "list_memories_tool",
    description=(
        "查询记忆中心事项。scope 为 today 或 all，type 可选 review/todo/reminder/long_term/memo，"
        "status 默认为 active。"
    ),
)
async def list_memories_tool(scope: str = "today", type: str | None = None, status: str = "active") -> str:
    user_id = get_current_user_id_from_context()
    if not user_id:
        return "错误: 无法确定用户身份"
    async with AsyncSessionLocal() as db:
        try:
            if scope == "today":
                memories = await memory_service.get_today_memories(db, user_id)
                if type:
                    memories = [item for item in memories if item["type"] == type]
            else:
                memories = await memory_service.list_memories(db, user_id, type=type, status=status)
            if not memories:
                return "没有找到符合条件的记忆事项"
            lines = [f"找到 {len(memories)} 条记忆事项：\n"]
            for i, item in enumerate(memories, 1):
                due = item.get("due_at") or "无到期时间"
                lines.append(f"{i}. **{item['title']}**")
                lines.append(f"   ID: {item['id']}")
                lines.append(f"   类型: {item['type']} / 状态: {item['status']} / 优先级: {item['priority']}")
                lines.append(f"   时间: {due}")
                if item.get("content"):
                    lines.append(f"   内容: {item['content'][:120]}...")
                lines.append("")
            return "\n".join(lines)
        except Exception as exc:
            logger.error(f"查询记忆事项失败: {exc}")
            return f"查询记忆事项时出错: {str(exc)}"


def get_tool():
    return list_memories_tool
