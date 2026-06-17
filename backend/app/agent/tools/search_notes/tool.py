from langchain_core.tools import tool

from app.agent.tool_context import get_current_user_id_from_context
from app.core.background_init import init_manager
from app.core.logger_handler import logger
from app.db.db_config import AsyncSessionLocal


@tool("search_notes_tool")
async def search_notes_tool(query: str, top_k: int = 5) -> str:
    """搜索笔记工具"""
    user_id = get_current_user_id_from_context()
    if not user_id:
        return "错误: 无法确定用户身份"
    async with AsyncSessionLocal() as db:
        try:
            results = await init_manager.note_service.search_notes(db, user_id, query, top_k=top_k)
            if not results:
                return "未找到相关笔记"
            lines = [f"找到 {len(results)} 篇相关笔记：\n"]
            for i, note in enumerate(results, 1):
                lines.append(f"{i}. **{note.title}**")
                if note.category:
                    lines.append(f"   分类: {note.category}")
                if note.tags:
                    lines.append(f"   标签: {', '.join(note.tags)}")
                lines.append(f"   内容预览: {note.content[:200]}...\n")
            return "\n".join(lines)
        except Exception as exc:
            logger.error(f"搜索笔记失败: {exc}")
            return f"搜索笔记时出错: {str(exc)}"


def get_tool():
    return search_notes_tool

