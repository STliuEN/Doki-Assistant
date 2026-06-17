from langchain_core.tools import tool

from app.agent.tool_context import (
    get_current_user_id_from_context,
    get_rag_retrieval_settings_from_context,
    get_thinking_callback_from_context,
)
from app.rag.rag_service import RagService


@tool("rag_summary_tools")
async def rag_summary_tool(query: str, user_id: str = None) -> str:
    """RAG 摘要工具"""
    effective_user_id = user_id or get_current_user_id_from_context()
    if not effective_user_id:
        return "错误: 无法确定用户身份，请提供有效的user_id"

    thinking_callback = get_thinking_callback_from_context()
    retrieval_settings = get_rag_retrieval_settings_from_context()
    result = await RagService(
        effective_user_id,
        thinking_callback=thinking_callback,
        retrieval_settings=retrieval_settings,
    ).get_documents_and_summary(query)
    documents = result.get("documents", [])
    summary = result.get("summary", "")

    formatted_result = f"摘要: {summary}\n\n"
    formatted_result += "检索到的文档列表（已重排序）:\n"
    for i, doc in enumerate(documents, 1):
        formatted_result += f"{i}. {doc}\n"

    return formatted_result


def get_tool():
    return rag_summary_tool
