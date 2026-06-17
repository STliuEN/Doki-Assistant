from langchain_core.tools import tool

from app.agent.tool_context import get_current_user_id_from_context
from app.core.logger_handler import logger
from app.db.db_config import AsyncSessionLocal
from app.services.memory_service import memory_service


@tool("delete_memory_tool")
async def delete_memory_tool(memory_id: str) -> str:
    """永久删除记忆事项（描述见 TOOL.md）。

    高风险确认由 GuardedTool 统一拦截：未确认时本函数不会被调用，
    GuardedTool 会暂存待确认动作并推送 waiting_confirmation；用户确认后
    /chat/agent/confirm 才会真正执行到这里。
    """
    user_id = get_current_user_id_from_context()
    if not user_id:
        return "错误: 无法确定用户身份"
    async with AsyncSessionLocal() as db:
        try:
            deleted = await memory_service.delete_memory(db, user_id, memory_id)
        except Exception as exc:
            logger.error(f"删除记忆事项失败: {exc}")
            return f"删除记忆事项时出错: {str(exc)}"
    if not deleted:
        return f"未找到可删除的记忆事项（ID: {memory_id}），可能已被删除或不属于当前用户。"
    return f"✅ 已永久删除记忆事项（ID: {memory_id}）。"


def get_tool():
    return delete_memory_tool
