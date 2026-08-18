import uuid
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.skill_registry import get_skill_catalog
from app.agent.streaming import (
    get_agent_regenerate_stream_response,
    get_agent_stream_response,
    get_confirm_action_stream_response,
)
from app.core.rate_limit import rate_limit
from app.core.success_response import success_response
from app.db.db_config import get_db
from app.schemas.api import ApiResponse
from app.schemas.models import (
    ConfirmActionRequest,
    DeleteMessageResponse,
    QueryRequest,
    RAGRequest,
    RAGResponse,
    RegenerateRequest,
    ReorderRequest,
    ReorderResponse,
    SessionMessagesResponse,
    SessionResponse,
)
from app.schemas.sse import SSE_OPENAPI_RESPONSE
from app.services import session_manager as sm
from app.services.agent_run_service import CHAT_PROMPT_MODES, prepare_agent_run
from app.services.pending_action_store import take_pending_action
from app.services.session_query_service import SessionQueryService, get_session_query_service
from app.utils.auth_utils import get_current_user_id

chat_router = APIRouter(prefix="/chat", tags=["chat"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
}


@chat_router.get("/prompt-modes", response_model=ApiResponse[Any])
async def get_prompt_modes():
    return success_response(data=[
        {"value": value, "label": label}
        for value, label in CHAT_PROMPT_MODES.items()
    ])


@chat_router.get("/skills", response_model=ApiResponse[Any])
async def get_chat_skills():
    return success_response(data=get_skill_catalog())


@chat_router.post(
    "/agent/query/stream",
    response_class=StreamingResponse,
    responses=SSE_OPENAPI_RESPONSE,
)
async def query_stream(
    request: QueryRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit(limit=10, window=60)),
):
    """查询 Agent 流式响应。"""
    session_id = request.session_id or str(uuid.uuid4())
    plan = await prepare_agent_run(
        db, user_id,
        query=request.query,
        model_config_id=request.model_config_id,
        prompt_type=request.prompt_type,
        skill_ids=request.skill_ids,
        tool_ids=request.tool_ids,
    )

    return StreamingResponse(
        get_agent_stream_response(
            request.query,
            session_id,
            user_id,
            model_config=plan.model_config,
            custom_tools=plan.tools,
            context_settings=request.context,
            rag_retrieval_settings=request.rag_retrieval,
            custom_system_prompt=plan.system_prompt,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@chat_router.post(
    "/agent/confirm",
    response_class=StreamingResponse,
    responses=SSE_OPENAPI_RESPONSE,
)
async def confirm_agent_action(
    request: ConfirmActionRequest,
    user_id: str = Depends(get_current_user_id),
    _: None = Depends(rate_limit(limit=20, window=60)),
):
    """确认或取消一条高风险待确认动作，并以 SSE 流式返回执行结果。"""
    action = await take_pending_action(request.pending_action_id, user_id)
    if action is None:
        # 不存在 / 已过期 / 已消费 / 越权，统一按 410 处理（前端提示重新发起）。
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="待确认操作不存在或已失效，请重新发起。",
        )

    return StreamingResponse(
        get_confirm_action_stream_response(action, request.confirmed, user_id),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@chat_router.post("/rag/query", response_model=ApiResponse[RAGResponse])
async def query_rag(
    request: RAGRequest,
    user_id: str = Depends(get_current_user_id),
    router_service: SessionQueryService = Depends(get_session_query_service),
    _: None = Depends(rate_limit(limit=15, window=60)),
):
    """RAG 检索。"""
    response = await router_service.handle_rag_query(request.query, user_id)
    return success_response(data=RAGResponse(response=response))


@chat_router.get("/session/{session_id}", response_model=ApiResponse[SessionResponse])
async def get_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    router_service: SessionQueryService = Depends(get_session_query_service),
):
    """获取会话信息。"""
    history = await router_service.handle_get_session(session_id, user_id)
    return success_response(data=SessionResponse(session_id=session_id, history=history))


@chat_router.get("/session/{session_id}/messages", response_model=ApiResponse[SessionMessagesResponse])
async def get_session_messages(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """获取会话原始消息列表（带消息 ID）。"""
    messages = await sm.session_manager.get_messages(session_id, user_id)
    return success_response(data=SessionMessagesResponse(session_id=session_id, messages=messages))


@chat_router.delete("/session/{session_id}/messages/{message_id}", response_model=ApiResponse[DeleteMessageResponse])
async def delete_session_message(
    session_id: str,
    message_id: int,
    mode: str = "single",
    user_id: str = Depends(get_current_user_id),
):
    """删除会话中的单条消息或相关消息。mode: single / pair / after。"""
    result = await sm.session_manager.delete_message(session_id, user_id, message_id, mode)
    return success_response(data=DeleteMessageResponse(**result))


@chat_router.post(
    "/session/{session_id}/messages/{message_id}/regenerate/stream",
    response_class=StreamingResponse,
    responses=SSE_OPENAPI_RESPONSE,
)
async def regenerate_session_message_stream(
    session_id: str,
    message_id: int,
    request: RegenerateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit(limit=10, window=60)),
):
    """重新生成已有 assistant 消息，流式返回并覆盖原消息。"""
    payload = await sm.session_manager.get_regenerate_payload(session_id, user_id, message_id)
    plan = await prepare_agent_run(
        db, user_id,
        query=payload["query"],
        model_config_id=request.model_config_id,
        prompt_type=request.prompt_type,
        skill_ids=request.skill_ids,
        tool_ids=request.tool_ids,
    )

    return StreamingResponse(
        get_agent_regenerate_stream_response(
            session_id,
            user_id,
            message_id,
            model_config=plan.model_config,
            custom_tools=plan.tools,
            context_settings=request.context,
            rag_retrieval_settings=request.rag_retrieval,
            custom_system_prompt=plan.system_prompt,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@chat_router.delete("/session/{session_id}", response_model=ApiResponse[None])
async def delete_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    router_service: SessionQueryService = Depends(get_session_query_service),
):
    """删除会话。"""
    await router_service.handle_delete_session(session_id, user_id)
    return success_response(message=f"Session {session_id} deleted successfully")


@chat_router.get("/sessions", response_model=ApiResponse[Any])
async def get_all_sessions(
    user_id: str = Depends(get_current_user_id),
    router_service: SessionQueryService = Depends(get_session_query_service),
):
    """获取当前用户所有会话。"""
    sessions = await router_service.handle_get_all_sessions(user_id)
    return success_response(data={"sessions": sessions})


@chat_router.get("/sessions/{user_id}", response_model=ApiResponse[Any])
async def get_user_sessions(
    user_id: str,
    current_user_id: str = Depends(get_current_user_id),
    router_service: SessionQueryService = Depends(get_session_query_service),
):
    """获取用户所有会话 ID。"""
    session_ids = await router_service.handle_get_user_sessions(user_id, current_user_id)
    return success_response(data={"sessions": session_ids})


@chat_router.post("/reorder", response_model=ApiResponse[ReorderResponse])
async def reorder_documents(
    request: ReorderRequest,
    user_id: str = Depends(get_current_user_id),
    router_service: SessionQueryService = Depends(get_session_query_service),
    _: None = Depends(rate_limit(limit=20, window=60)),
):
    """对文档进行重排序。"""
    sorted_docs = await router_service.handle_reorder(request.query, request.documents)
    return success_response(data=ReorderResponse(documents=sorted_docs))
