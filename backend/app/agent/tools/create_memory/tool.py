from langchain_core.tools import tool

from app.agent.tool_context import get_current_user_id_from_context
from app.core.logger_handler import logger
from app.db.db_config import AsyncSessionLocal
from app.schemas.memory import MemoryCreate
from app.services.memory_service import memory_service


@tool("create_memory_tool")
async def create_memory_tool(
    title: str,
    content: str = "",
    type: str = "memo",
    priority: str = "medium",
    due_at: str | None = None,
) -> str:
    """创建记忆中心事项（描述见 TOOL.md）。"""
    user_id = get_current_user_id_from_context()
    if not user_id:
        return "错误: 无法确定用户身份"
    async with AsyncSessionLocal() as db:
        try:
            payload = MemoryCreate(
                title=title,
                content=content,
                type=type,
                priority=priority,
                due_at=due_at,
                source_type="chat",
            )
            memory = await memory_service.create_memory(db, user_id, payload)
            return f"✅ 已创建记忆事项\n- 标题: {memory['title']}\n- 类型: {memory['type']}\n- ID: {memory['id']}"
        except Exception as exc:
            logger.error(f"创建记忆事项失败: {exc}")
            return f"创建记忆事项时出错: {str(exc)}"


def get_tool():
    return create_memory_tool
