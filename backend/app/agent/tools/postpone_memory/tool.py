from langchain_core.tools import tool

from app.agent.tool_context import get_current_user_id_from_context
from app.core.logger_handler import logger
from app.db.db_config import AsyncSessionLocal
from app.services.memory_service import memory_service


@tool("postpone_memory_tool")
async def postpone_memory_tool(memory_id: str, days: int = 1) -> str:
    """延期记忆事项（描述见 TOOL.md）。"""
    user_id = get_current_user_id_from_context()
    if not user_id:
        return "错误: 无法确定用户身份"
    async with AsyncSessionLocal() as db:
        try:
            result = await memory_service.postpone_memory(db, user_id, memory_id, days)
            return result["message"]
        except Exception as exc:
            logger.error(f"延期记忆事项失败: {exc}")
            return f"延期记忆事项时出错: {str(exc)}"


def get_tool():
    return postpone_memory_tool
