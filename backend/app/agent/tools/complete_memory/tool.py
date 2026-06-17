from langchain_core.tools import tool

from app.agent.tool_context import get_current_user_id_from_context
from app.core.logger_handler import logger
from app.db.db_config import AsyncSessionLocal
from app.services.memory_service import memory_service


@tool("complete_memory_tool", description="将非复习类型的记忆事项标记为完成。参数 memory_id 为记忆事项ID。")
async def complete_memory_tool(memory_id: str) -> str:
    user_id = get_current_user_id_from_context()
    if not user_id:
        return "错误: 无法确定用户身份"
    async with AsyncSessionLocal() as db:
        try:
            result = await memory_service.complete_memory(db, user_id, memory_id)
            return result["message"]
        except Exception as exc:
            logger.error(f"完成记忆事项失败: {exc}")
            return f"完成记忆事项时出错: {str(exc)}"


def get_tool():
    return complete_memory_tool
