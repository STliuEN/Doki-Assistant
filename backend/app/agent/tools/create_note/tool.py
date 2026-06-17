from langchain_core.tools import tool

from app.agent.tool_context import get_current_user_id_from_context
from app.core.background_init import init_manager
from app.core.logger_handler import logger
from app.db.db_config import AsyncSessionLocal
from app.schemas.models import NoteCreate


@tool("create_note_tool")
async def create_note_tool(title: str, content: str = "") -> str:
    """创建笔记工具"""
    user_id = get_current_user_id_from_context()
    if not user_id:
        return "错误: 无法确定用户身份"
    async with AsyncSessionLocal() as db:
        try:
            payload = NoteCreate(title=title, content=content)
            note = await init_manager.note_service.create_note(db, user_id, payload)
            return f"✅ 笔记创建成功！\n- 标题: {note.title}\n- ID: {note.id}\n- 标签和分类正在后台生成中..."
        except Exception as exc:
            logger.error(f"创建笔记失败: {exc}")
            return f"创建笔记时出错: {str(exc)}"


def get_tool():
    return create_note_tool

