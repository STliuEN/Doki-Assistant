from langchain_core.tools import tool

from app.agent.tool_context import get_current_user_id_from_context
from app.core.logger_handler import logger
from app.db.db_config import AsyncSessionLocal
from app.services.memory_service import memory_service


@tool("generate_review_question_tool", description="为复习类型记忆事项生成一道复习题。参数 memory_id 为记忆事项ID。")
async def generate_review_question_tool(memory_id: str) -> str:
    user_id = get_current_user_id_from_context()
    if not user_id:
        return "错误: 无法确定用户身份"
    async with AsyncSessionLocal() as db:
        try:
            data = await memory_service.generate_review_question(db, user_id, memory_id)
            choices = data.get("choices") or []
            lines = [f"复习题: {data.get('question', '')}"]
            if choices:
                lines.append("选项:")
                for index, choice in enumerate(choices, 1):
                    lines.append(f"{index}. {choice}")
            if data.get("answer"):
                lines.append(f"参考答案: {data['answer']}")
            return "\n".join(lines)
        except Exception as exc:
            logger.error(f"生成复习题失败: {exc}")
            return f"生成复习题时出错: {str(exc)}"


def get_tool():
    return generate_review_question_tool
