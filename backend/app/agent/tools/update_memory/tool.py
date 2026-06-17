from langchain_core.tools import tool

from app.agent.tool_context import get_current_user_id_from_context
from app.core.logger_handler import logger
from app.db.db_config import AsyncSessionLocal
from app.schemas.memory import MemoryUpdate
from app.services.memory_service import memory_service


@tool(
    "update_memory_tool",
    description=(
        "更新记忆事项。参数 memory_id 为记忆事项ID；title/content/type/status/priority/"
        "due_at/remind_at/metadata_json 均为可选。type 可为 review/todo/reminder/long_term/memo，"
        "status 可为 active/done/archived，priority 可为 low/medium/high。日期时间请使用 ISO 格式。"
    ),
)
async def update_memory_tool(
    memory_id: str,
    title: str | None = None,
    content: str | None = None,
    type: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    due_at: str | None = None,
    remind_at: str | None = None,
    metadata_json: str | None = None,
) -> str:
    user_id = get_current_user_id_from_context()
    if not user_id:
        return "错误: 无法确定用户身份"
    async with AsyncSessionLocal() as db:
        try:
            update_data = {
                key: value
                for key, value in {
                    "title": title,
                    "content": content,
                    "type": type,
                    "status": status,
                    "priority": priority,
                    "due_at": due_at,
                    "remind_at": remind_at,
                    "metadata_json": metadata_json,
                }.items()
                if value is not None
            }
            if not update_data:
                return "没有提供需要更新的字段"
            payload = MemoryUpdate(**update_data)
            updated = await memory_service.update_memory(db, user_id, memory_id, payload)
            if not updated:
                return "记忆事项不存在"
            return (
                "✅ 记忆事项已更新\n"
                f"- 标题: {updated['title']}\n"
                f"- ID: {updated['id']}\n"
                f"- 类型: {updated['type']} / 状态: {updated['status']} / 优先级: {updated['priority']}\n"
                f"- 到期时间: {updated.get('due_at') or '无'}\n"
                f"- 提醒时间: {updated.get('remind_at') or '无'}"
            )
        except Exception as exc:
            logger.error(f"更新记忆事项失败: {exc}")
            return f"更新记忆事项时出错: {str(exc)}"


def get_tool():
    return update_memory_tool
