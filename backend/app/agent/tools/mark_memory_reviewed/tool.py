from langchain_core.tools import tool

from app.agent.tool_context import get_current_user_id_from_context
from app.core.logger_handler import logger
from app.db.db_config import AsyncSessionLocal
from app.services.memory_service import memory_service


@tool("mark_memory_reviewed_tool")
async def mark_memory_reviewed_tool(memory_id: str) -> str:
    """标记复习类事项为已复习并推进间隔（描述见 TOOL.md）。"""
    user_id = get_current_user_id_from_context()
    if not user_id:
        return "错误: 无法确定用户身份"
    async with AsyncSessionLocal() as db:
        try:
            result = await memory_service.mark_reviewed(db, user_id, memory_id)
            memory = result.get("memory")
            if result.get("success") and memory:
                return (
                    f"✅ 已标记复习完成。\n"
                    f"- 标题: {memory['title']}\n"
                    f"- 第 {memory['review_count']} 次复习\n"
                    f"- 下次间隔: {memory['interval_days']} 天"
                )
            return result["message"]
        except Exception as exc:
            logger.error(f"标记复习完成失败: {exc}")
            return f"标记复习完成时出错: {str(exc)}"


def get_tool():
    return mark_memory_reviewed_tool
