from langchain_core.tools import tool

from app.agent.tool_context import get_current_user_id_from_context
from app.core.logger_handler import logger
from app.db.db_config import AsyncSessionLocal
from app.services.memory_service import memory_service


def _format_memory(item: dict) -> str:
    lines = [
        "记忆事项详情：",
        f"- 标题: {item['title']}",
        f"- ID: {item['id']}",
        f"- 类型: {item['type']}",
        f"- 状态: {item['status']}",
        f"- 优先级: {item['priority']}",
        f"- 到期时间: {item.get('due_at') or '无'}",
        f"- 提醒时间: {item.get('remind_at') or '无'}",
    ]
    if item.get("source_type"):
        lines.append(f"- 来源: {item['source_type']}")
    if item.get("source_id"):
        lines.append(f"- 来源ID: {item['source_id']}")
    if item.get("content"):
        lines.append(f"- 内容: {item['content']}")
    if item.get("type") == "review":
        lines.append(f"- 复习次数: {item.get('review_count', 0)}")
        lines.append(f"- 当前间隔天数: {item.get('interval_days', 1)}")
    return "\n".join(lines)


@tool("get_memory_tool")
async def get_memory_tool(memory_id: str) -> str:
    """按 ID 获取记忆事项详情（描述见 TOOL.md）。"""
    user_id = get_current_user_id_from_context()
    if not user_id:
        return "错误: 无法确定用户身份"
    async with AsyncSessionLocal() as db:
        try:
            item = await memory_service.get_memory_dict(db, user_id, memory_id)
            if not item:
                return "记忆事项不存在"
            return _format_memory(item)
        except Exception as exc:
            logger.error(f"获取记忆事项详情失败: {exc}")
            return f"获取记忆事项详情时出错: {str(exc)}"


def get_tool():
    return get_memory_tool
