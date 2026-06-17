from langchain_core.tools import tool

from app.utils.auth_utils import decode_django_jwt


@tool("get_user_info_tools")
async def user_info_tool(token: str) -> str:
    """获取用户信息工具"""
    payload = decode_django_jwt(token)
    if payload:
        user_id = payload.get("user_id", "未知")
        user_name = payload.get("user_name", "未知")
        return f"用户信息：\n- 用户ID: {user_id}\n- 用户名: {user_name}"
    return "无法解析JWT token，无法获取用户信息"


def get_tool():
    return user_info_tool

