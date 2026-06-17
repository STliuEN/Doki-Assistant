from langchain_core.tools import tool

from app.agent.tool_context import get_current_user_id_from_context, get_thinking_callback_from_context


@tool("delete_memory_tool")
async def delete_memory_tool(memory_id: str) -> str:
    """永久删除记忆事项（描述见 TOOL.md）。"""
    user_id = get_current_user_id_from_context()
    if not user_id:
        return "错误: 无法确定用户身份"
    callback = get_thinking_callback_from_context()
    if callback:
        await callback({
            "type": "waiting_confirmation",
            "stage": "tool_confirmation",
            "content": "删除记忆事项需要用户确认，当前未执行删除操作。",
            "details": {
                "tool": "delete_memory_tool",
                "risk_level": "high",
                "action": "delete_memory",
                "input_preview": f"memory_id={memory_id}",
            },
        })
    return (
        "删除记忆事项属于高风险操作，当前没有执行删除。"
        "请在确认删除后重新发起明确请求，或改用归档操作。"
    )


def get_tool():
    return delete_memory_tool
