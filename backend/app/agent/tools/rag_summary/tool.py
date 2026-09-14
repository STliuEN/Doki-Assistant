import os

from langchain_core.tools import tool

from app.agent.tool_context import (
    get_current_user_id_from_context,
    get_rag_retrieval_settings_from_context,
    get_thinking_callback_from_context,
)
from app.rag.rag_service import RagService

E5_RAG_ENABLED = os.getenv("E5_RAG_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


@tool("rag_summary_tools")
async def rag_summary_tool(query: str, user_id: str = None) -> str:
    """RAG 摘要工具"""
    authenticated_user_id = get_current_user_id_from_context()
    if user_id and authenticated_user_id and user_id != authenticated_user_id:
        return "错误: user_id 与当前认证用户不匹配"
    effective_user_id = authenticated_user_id or user_id
    if not effective_user_id:
        return "错误: 无法确定用户身份，请提供有效的user_id"

    if E5_RAG_ENABLED:
        from app.db.db_config import AsyncSessionLocal
        from app.rag.projection.query import query_user

        async with AsyncSessionLocal() as db:
            result = await query_user(db, effective_user_id, query)
        return "\n\n".join(result.documents) if result.documents else "抱歉，我没有找到相关的信息。"

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
