from langchain_core.tools import tool

from app.auth.tokens import decode_access_token


@tool("get_user_info_tools")
async def user_info_tool(token: str) -> str:
    """获取用户信息工具"""
    payload = decode_access_token(token)
    if payload:
        user_id = payload.get("user_id", "未知")
        return f"用户信息：\n- 用户ID: {user_id}"
    return "无法解析JWT token，无法获取用户信息"


def get_tool():
    return user_info_tool
