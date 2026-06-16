import uuid

from fastapi import Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.agent import get_agent_stream_response
from app.agent.skill_registry import get_skill_catalog, resolve_skills
from app.core.rate_limit import rate_limit
from app.core.success_response import success_response
from app.db.db_config import get_db
from app.router.chat_service import ChatService, get_router_service
from app.schemas.models import QueryRequest, RAGRequest, RAGResponse, ReorderRequest, ReorderResponse, SessionResponse
from app.services.model_config_service import get_model_config_service
from app.utils.auth_utils import get_current_user_id
from app.utils.prompt_loader import load_prompt

chat_router = APIRouter(prefix="/chat", tags=["chat"])

CHAT_PROMPT_MODES = {
    "main_prompt": "默认助手",
    "chat_creative_prompt": "创意伙伴",
    "chat_strict_prompt": "严谨助手",
    "chat_teacher_prompt": "教学助手",
}


def build_chat_system_prompt(prompt_type: str, skill_prompts: list[str] | None = None) -> str:
    parts = [load_prompt("main_prompt")]

    if skill_prompts:
        parts.extend([
            "## 当前启用 Skills",
            "\n\n".join(skill_prompts),
            "请只依赖当前已启用 skill 的说明和已绑定工具执行任务；未启用的能力不要假装可用。",
        ])

    if prompt_type != "main_prompt":
        parts.extend([
            "## 当前 AI 模式补充规则",
            load_prompt(prompt_type),
            "请同时遵守基础 Agent 规则、已启用 skill 规则和当前 AI 模式规则；如果冲突，优先保证工具、RAG、笔记管理等基础能力正常工作，再体现当前模式的回答风格。",
        ])

    return "\n\n".join(parts)


@chat_router.get("/prompt-modes")
async def get_prompt_modes():
    return success_response(data=[
        {"value": value, "label": label}
        for value, label in CHAT_PROMPT_MODES.items()
    ])


@chat_router.get("/skills")
async def get_chat_skills():
    return success_response(data=get_skill_catalog())


@chat_router.post("/agent/query/stream")
async def query_stream(
    request: QueryRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit(limit=10, window=60)),
):
    """查询 Agent 流式响应。"""
    session_id = request.session_id or str(uuid.uuid4())
    svc = get_model_config_service()
    if request.model_config_id:
        model_config = await svc.get_config(db, user_id, request.model_config_id)
        if model_config is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model config not found")
    else:
        model_config = None

    prompt_type = request.prompt_type or "main_prompt"
    if prompt_type not in CHAT_PROMPT_MODES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported prompt_type")

    try:
        skill_resolution = resolve_skills(request.skill_ids, request.tool_ids)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    system_prompt = build_chat_system_prompt(prompt_type, skill_resolution.skill_prompts)

    return StreamingResponse(
        get_agent_stream_response(
            request.query,
            session_id,
            user_id,
            model_config=model_config,
            custom_tools=skill_resolution.tools,
            custom_system_prompt=system_prompt,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@chat_router.post("/rag/query", response_model=RAGResponse)
async def query_rag(
    request: RAGRequest,
    user_id: str = Depends(get_current_user_id),
    router_service: ChatService = Depends(get_router_service),
    _: None = Depends(rate_limit(limit=15, window=60)),
):
    """RAG 检索。"""
    response = await router_service.handle_rag_query(request.query, user_id)
    return success_response(data=RAGResponse(response=response))


@chat_router.get("/session/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    router_service: ChatService = Depends(get_router_service),
):
    """获取会话信息。"""
    history = await router_service.handle_get_session(session_id, user_id)
    return success_response(data=SessionResponse(session_id=session_id, history=history))


@chat_router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    router_service: ChatService = Depends(get_router_service),
):
    """删除会话。"""
    await router_service.handle_delete_session(session_id, user_id)
    return success_response(message=f"Session {session_id} deleted successfully")


@chat_router.get("/sessions")
async def get_all_sessions(router_service: ChatService = Depends(get_router_service)):
    """获取所有会话 ID。"""
    session_ids = await router_service.handle_get_all_sessions()
    return success_response(data={"sessions": session_ids})


@chat_router.get("/sessions/{user_id}")
async def get_user_sessions(
    user_id: str,
    current_user_id: str = Depends(get_current_user_id),
    router_service: ChatService = Depends(get_router_service),
):
    """获取用户所有会话 ID。"""
    session_ids = await router_service.handle_get_user_sessions(user_id, current_user_id)
    return success_response(data={"sessions": session_ids})


@chat_router.post("/reorder", response_model=ReorderResponse)
async def reorder_documents(
    request: ReorderRequest,
    router_service: ChatService = Depends(get_router_service),
    _: None = Depends(rate_limit(limit=20, window=60)),
):
    """对文档进行重排序。"""
    sorted_docs = await router_service.handle_reorder(request.query, request.documents)
    return success_response(data=ReorderResponse(documents=sorted_docs))
