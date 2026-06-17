import datetime

from langchain_core.tools import tool


@tool("what_time_is_now")
async def current_time_tool() -> str:
    """获取当前年月日时分的工具"""
    return f"当前时间是：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"


def get_tool():
    return current_time_tool

