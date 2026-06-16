from langchain_core.tools import tool

from app.agent.tool_context import get_current_user_id_from_context
from app.core.background_init import init_manager
from app.core.logger_handler import logger
from app.db.db_config import AsyncSessionLocal


@tool("get_note_stats_tool", description="获取用户的笔记统计信息，包括笔记总数、各分类（工作/学习/生活/项目）的笔记数量。")
async def note_stats_tool() -> str:
    """笔记统计工具"""
    user_id = get_current_user_id_from_context()
    if not user_id:
        return "错误: 无法确定用户身份"
    async with AsyncSessionLocal() as db:
        try:
            stats = await init_manager.note_service.get_category_stats(db, user_id)
            lines = ["📊 笔记统计\n"]
            lines.append(f"总笔记数: {stats['total']}\n")
            lines.append("各分类:")
            for cat in stats["categories"]:
                emoji = {"work": "💼", "study": "📖", "life": "🏠", "project": "🚀"}.get(cat["category"], "📄")
                lines.append(f"  {emoji} {cat['category']}: {cat['count']} 篇")
            if stats["uncategorized"] > 0:
                lines.append(f"  📄 未分类: {stats['uncategorized']} 篇")
            return "\n".join(lines)
        except Exception as exc:
            logger.error(f"获取笔记统计失败: {exc}")
            return f"获取笔记统计时出错: {str(exc)}"


def get_tool():
    return note_stats_tool

