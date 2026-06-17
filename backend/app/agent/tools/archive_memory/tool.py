from langchain_core.tools import tool

from app.agent.tool_context import get_current_user_id_from_context
from app.core.logger_handler import logger
from app.db.db_config import AsyncSessionLocal
from app.services.memory_service import memory_service


@tool("archive_memory_tool", description="将记忆事项归档。参数 memory_id 为记忆事项ID。")
async def archive_memory_tool(memory_id: str) -> str:
    user_id = get_current_user_id_from_context()
    if not user_id:
        return "错误: 无法确定用户身份"
    async with AsyncSessionLocal() as db:
        try:
            result = await memory_service.archive_memory(db, user_id, memory_id)
            memory = result.get("memory")
            if result.get("success") and memory:
                return f"✅ 已归档记忆事项\n- 标题: {memory['title']}\n- ID: {memory['id']}"
            return result["message"]
        except Exception as exc:
            logger.error(f"归档记忆事项失败: {exc}")
            return f"归档记忆事项时出错: {str(exc)}"


def get_tool():
    return archive_memory_tool
