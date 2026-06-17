from langchain_core.tools import tool

from app.agent.tool_context import get_current_user_id_from_context
from app.core.logger_handler import logger
from app.db.db_config import AsyncSessionLocal
from app.services.memory_service import memory_service


@tool("today_reviews_tool", description="查询今天到期或需要提醒的复习事项。无参数。")
async def today_reviews_tool() -> str:
    user_id = get_current_user_id_from_context()
    if not user_id:
        return "错误: 无法确定用户身份"
    async with AsyncSessionLocal() as db:
        try:
            memories = await memory_service.get_today_memories(db, user_id)
            reviews = [item for item in memories if item["type"] == "review"]
            if not reviews:
                return "今天没有到期的复习事项"
            lines = [f"今天有 {len(reviews)} 条复习事项：\n"]
            for index, item in enumerate(reviews, 1):
                lines.append(f"{index}. **{item['title']}**")
                lines.append(f"   ID: {item['id']}")
                lines.append(f"   复习次数: {item.get('review_count', 0)} / 当前间隔: {item.get('interval_days', 1)} 天")
                lines.append(f"   到期时间: {item.get('due_at') or '无'}")
                if item.get("content"):
                    lines.append(f"   内容: {item['content'][:120]}...")
                lines.append("")
            return "\n".join(lines)
        except Exception as exc:
            logger.error(f"查询今日复习失败: {exc}")
            return f"查询今日复习时出错: {str(exc)}"


def get_tool():
    return today_reviews_tool
