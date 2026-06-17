from langchain_core.tools import tool

from app.agent.tool_context import get_current_user_id_from_context
from app.core.logger_handler import logger
from app.db.db_config import AsyncSessionLocal
from app.services.memory_service import memory_service


@tool("delete_memory_tool")
async def delete_memory_tool(memory_id: str) -> str:
    """永久删除记忆事项（描述见 TOOL.md）。"""
    user_id = get_current_user_id_from_context()
    if not user_id:
        return "错误: 无法确定用户身份"
    async with AsyncSessionLocal() as db:
        try:
            deleted = await memory_service.delete_memory(db, user_id, memory_id)
            if not deleted:
                return "记忆事项不存在"
            return f"✅ 记忆事项已删除\n- ID: {memory_id}"
        except Exception as exc:
            logger.error(f"删除记忆事项失败: {exc}")
            return f"删除记忆事项时出错: {str(exc)}"


def get_tool():
    return delete_memory_tool
