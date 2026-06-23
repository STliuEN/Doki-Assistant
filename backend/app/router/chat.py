import uuid

from fastapi import Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.agent import (
    get_agent_regenerate_stream_response,
    get_agent_stream_response,
    get_confirm_action_stream_response,
)
from app.agent.intent_router import route_skills
from app.agent.mcp.registry import mcp_tool_registry
from app.agent.skill_registry import get_skill_catalog, resolve_skills, skill_registry
from app.core.rate_limit import rate_limit
from app.core.success_response import success_response
from app.db.db_config import get_db
from app.router.chat_service import ChatService, get_router_service
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
from app.services.pending_action_store import take_pending_action
from app.services import session_manager as sm
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


def build_chat_system_prompt(
    prompt_type: str,
    skill_prompts: list[str] | None = None,
    tool_names: list[str] | None = None,
    notices: list[str] | None = None,
) -> str:
    parts = [load_prompt("main_prompt")]

    if skill_prompts:
        parts.extend([
            "## 当前启用 Skills",
            "\n\n".join(skill_prompts),
            "请只依赖当前已启用 skill 的说明和已绑定工具执行任务；未启用的能力不要假装可用。",
        ])

    if tool_names:
        parts.extend([
            "## 本次可用工具",
            f"你当前只能调用以下工具：{', '.join(tool_names)}。未列出的能力一律视为不可用，不要假装拥有或提及。",
        ])

    if notices:
        parts.extend([
            "## 运行提示",
            "\n".join(f"- {item}" for item in notices),
        ])

    if prompt_type != "main_prompt":
        parts.extend([
            f"## 回答风格（当前模式：{CHAT_PROMPT_MODES[prompt_type]}）",
            load_prompt(prompt_type),
            "风格优先级：在不违反全局规则、工具调用纪律与事实准确的前提下体现以上回答风格；冲突时以全局规则为准。",
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

    # 已选 skill 作为允许集（上界）；预路由只在其中挑出与本次 query 相关的子集。
    # 显式指定 tool_ids 时视为精确控制，跳过路由。
    candidate_skill_ids = request.skill_ids if request.skill_ids is not None else skill_registry.default_skill_ids()
    if request.tool_ids:
        routed_skill_ids = candidate_skill_ids
    else:
        routed_skill_ids = await route_skills(request.query, candidate_skill_ids)

    # MCP 处于错误态时在此惰性自愈（健康态零开销）；刷新后需 reload 让工具对 agent 可见。
    if await mcp_tool_registry.ensure_fresh():
        skill_registry.reload()

    try:
        skill_resolution = resolve_skills(routed_skill_ids, request.tool_ids)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    tool_names = [tool.name for tool in skill_resolution.tools]
    system_prompt = build_chat_system_prompt(
        prompt_type, skill_resolution.skill_prompts, tool_names, skill_resolution.notices
    )

    return StreamingResponse(
        get_agent_stream_response(
            request.query,
            session_id,
            user_id,
            model_config=model_config,
            custom_tools=skill_resolution.tools,
            context_settings=request.context,
            rag_retrieval_settings=request.rag_retrieval,
            custom_system_prompt=system_prompt,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@chat_router.post("/agent/confirm")
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


@chat_router.get("/session/{session_id}/messages", response_model=SessionMessagesResponse)
async def get_session_messages(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """获取会话原始消息列表（带消息 ID）。"""
    messages = await sm.session_manager.get_messages(session_id, user_id)
    return success_response(data=SessionMessagesResponse(session_id=session_id, messages=messages))


@chat_router.delete("/session/{session_id}/messages/{message_id}", response_model=DeleteMessageResponse)
async def delete_session_message(
    session_id: str,
    message_id: int,
    mode: str = "single",
    user_id: str = Depends(get_current_user_id),
):
    """删除会话中的单条消息或相关消息。mode: single / pair / after。"""
    result = await sm.session_manager.delete_message(session_id, user_id, message_id, mode)
    return success_response(data=DeleteMessageResponse(**result))


@chat_router.post("/session/{session_id}/messages/{message_id}/regenerate/stream")
async def regenerate_session_message_stream(
    session_id: str,
    message_id: int,
    request: RegenerateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit(limit=10, window=60)),
):
    """重新生成已有 assistant 消息，流式返回并覆盖原消息。"""
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

    payload = await sm.session_manager.get_regenerate_payload(session_id, user_id, message_id)
    candidate_skill_ids = request.skill_ids if request.skill_ids is not None else skill_registry.default_skill_ids()
    if request.tool_ids:
        routed_skill_ids = candidate_skill_ids
    else:
        routed_skill_ids = await route_skills(payload["query"], candidate_skill_ids)

    if await mcp_tool_registry.ensure_fresh():
        skill_registry.reload()

    try:
        skill_resolution = resolve_skills(routed_skill_ids, request.tool_ids)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    tool_names = [tool.name for tool in skill_resolution.tools]
    system_prompt = build_chat_system_prompt(
        prompt_type, skill_resolution.skill_prompts, tool_names, skill_resolution.notices
    )

    return StreamingResponse(
        get_agent_regenerate_stream_response(
            session_id,
            user_id,
            message_id,
            model_config=model_config,
            custom_tools=skill_resolution.tools,
            context_settings=request.context,
            rag_retrieval_settings=request.rag_retrieval,
            custom_system_prompt=system_prompt,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


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
async def get_all_sessions(
    user_id: str = Depends(get_current_user_id),
    router_service: ChatService = Depends(get_router_service),
):
    """获取当前用户所有会话。"""
    sessions = await router_service.handle_get_all_sessions(user_id)
    return success_response(data={"sessions": sessions})


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
    user_id: str = Depends(get_current_user_id),
    router_service: ChatService = Depends(get_router_service),
    _: None = Depends(rate_limit(limit=20, window=60)),
):
    """对文档进行重排序。"""
    sorted_docs = await router_service.handle_reorder(request.query, request.documents)
    return success_response(data=ReorderResponse(documents=sorted_docs))
