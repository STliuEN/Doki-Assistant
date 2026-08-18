import asyncio
import time
from collections.abc import AsyncGenerator

from langchain_core.tools import BaseTool

from app.agent.context_builder import build_query_context, build_regenerate_context
from app.agent.factory import AgentFactory, agent_factory
from app.agent.runtime.budget import get_runtime_budget
from app.agent.runtime.event_pump import stream_agent_events
from app.agent.runtime.events import runtime_event
from app.agent.runtime.sse_driver import drive_sse_stream, make_thinking_callback, new_run_id
from app.agent.tool_context import (
    set_confirmed_action,
    set_current_session_id,
    set_current_user_id,
    set_rag_retrieval_settings,
    set_runtime_state,
    set_thinking_callback,
)
from app.core.logger_handler import logger
from app.models.model_config import UserModelConfig
from app.schemas.sse import encode_sse
from app.services import session_manager as sm


def bind_run_context(
    user_id: str,
    session_id: str | None,
    thinking_callback,
    rag_retrieval_settings,
    budget: dict,
) -> None:
    """统一设置每轮运行的 6 个 contextvar。顺序与齐全度被 GuardedTool 依赖，禁止拆散。"""
    set_current_user_id(user_id)
    set_current_session_id(session_id)
    set_thinking_callback(thinking_callback)
    set_rag_retrieval_settings(rag_retrieval_settings)
    set_confirmed_action(False)
    set_runtime_state({"tool_calls": 0, "max_tool_calls": budget["max_tool_calls"]})


async def get_agent_stream_response(
        query: str,
        session_id: str,
        user_id: str,
        model_config: UserModelConfig | None = None,
        custom_tools: list[BaseTool] | None = None,
        context_settings=None,
        rag_retrieval_settings=None,
        *,
        factory: AgentFactory = agent_factory,
        **kwargs,
) -> AsyncGenerator[str, None]:
    """获取 Agent 流式响应（包含思考过程，实时推送）。"""
    thinking_queue = asyncio.Queue()
    run_id = new_run_id()
    budget = get_runtime_budget()
    start_time = time.monotonic()
    agent_result_holder = {"response": None, "error": None, "stop_reason": "completed", "run_id": run_id}
    full_response: list[str] = []
    thinking_callback = make_thinking_callback(thinking_queue, run_id, start_time, "【思考过程】")

    async def run_agent():
        try:
            bind_run_context(user_id, session_id, thinking_callback, rag_retrieval_settings, budget)

            await thinking_callback(runtime_event("start", "正在准备上下文、模型和可用工具...", {"budget": budget}))

            ctx = await build_query_context(session_id, user_id, context_settings, model_config, factory)
            history = ctx["history"]
            summary = ctx["summary"]
            await thinking_callback(runtime_event("context", f"已载入 {len(history)} 轮近期上下文。", {
                "history_turns": len(history),
                "total_turns": ctx["total_turns"],
                "used_summary": ctx["used_summary"],
                "summary_tokens": sm.session_manager.estimate_tokens(summary) if summary else 0,
            }))
            logger.info(f"【Agent流式响应】获取会话历史成功，历史记录数: {len(history)}")

            agent_executor = factory.create_agent_executor(custom_tools=custom_tools, model_config=model_config, **kwargs)
            tool_names = [tool.name for tool in (custom_tools or [])]
            await thinking_callback(runtime_event("tools", f"本轮可用工具：{', '.join(tool_names) if tool_names else '无'}。", {
                "tools": tool_names,
            }))

            system_prompt = kwargs.get("custom_system_prompt") or factory.default_system_prompt
            await thinking_callback(runtime_event("agent", "Agent 正在执行推理和工具调用..."))

            await stream_agent_events(
                agent_executor,
                {"input": query, "chat_history": ctx["chat_history"], "system_prompt": system_prompt},
                thinking_queue,
                thinking_callback,
                full_response,
                budget,
            )

            agent_result_holder["response"] = "".join(full_response) if full_response else "抱歉，我无法理解您的请求。"
            await thinking_callback(runtime_event("done", "Agent 执行完成。", {
                "duration_ms": int((time.monotonic() - start_time) * 1000),
                "stop_reason": agent_result_holder["stop_reason"],
            }))
        except Exception as e:
            logger.error(f"【Agent流式响应】Agent执行失败: {e}", exc_info=True)
            agent_result_holder["error"] = str(e)

    async def on_success(response: str):
        await sm.session_manager.add_message(session_id, user_id, query, response)
        logger.info("【Agent流式响应】添加到会话历史成功")

    logger.info(f"【Agent流式响应】开始处理请求，用户ID: {user_id}, 会话ID: {session_id}, 查询: {query}")
    async for sse in drive_sse_stream(
        session_id, run_agent, thinking_queue, agent_result_holder,
        full_response, budget, start_time, on_success=on_success,
    ):
        yield sse


async def get_agent_regenerate_stream_response(
        session_id: str,
        user_id: str,
        assistant_message_id: int,
        model_config: UserModelConfig | None = None,
        custom_tools: list[BaseTool] | None = None,
        context_settings=None,
        rag_retrieval_settings=None,
        *,
        factory: AgentFactory = agent_factory,
        **kwargs,
) -> AsyncGenerator[str, None]:
    """重新生成已有 assistant 消息，并用新内容覆盖原消息。"""
    thinking_queue = asyncio.Queue()
    run_id = new_run_id()
    budget = get_runtime_budget()
    start_time = time.monotonic()
    agent_result_holder = {"response": None, "error": None, "stop_reason": "completed", "run_id": run_id}
    full_response: list[str] = []
    thinking_callback = make_thinking_callback(thinking_queue, run_id, start_time, "【重新生成思考过程】")

    payload = await sm.session_manager.get_regenerate_payload(session_id, user_id, assistant_message_id)
    query = payload["query"]
    ctx = await build_regenerate_context(session_id, user_id, payload, context_settings)

    async def run_agent():
        try:
            bind_run_context(user_id, session_id, thinking_callback, rag_retrieval_settings, budget)

            await thinking_callback(runtime_event("start", "正在重新生成回答...", {"budget": budget}))

            agent_executor = factory.create_agent_executor(custom_tools=custom_tools, model_config=model_config, **kwargs)
            tool_names = [tool.name for tool in (custom_tools or [])]
            history = ctx["history"]
            await thinking_callback(runtime_event(
                "context",
                f"已载入 {len(history)} 轮历史上下文；本轮可用工具：{', '.join(tool_names) if tool_names else '无'}。",
                {"history_turns": len(history), "tools": tool_names},
            ))
            system_prompt = kwargs.get("custom_system_prompt") or factory.default_system_prompt

            await stream_agent_events(
                agent_executor,
                {"input": query, "chat_history": ctx["chat_history"], "system_prompt": system_prompt},
                thinking_queue,
                thinking_callback,
                full_response,
                budget,
            )

            agent_result_holder["response"] = "".join(full_response) if full_response else "抱歉，我无法理解您的请求。"
            await thinking_callback(runtime_event("done", "Agent 执行完成。", {
                "duration_ms": int((time.monotonic() - start_time) * 1000),
                "stop_reason": agent_result_holder["stop_reason"],
            }))
        except Exception as e:
            logger.error(f"【Agent重新生成】Agent执行失败: {e}", exc_info=True)
            agent_result_holder["error"] = str(e)

    async def on_success(response: str):
        await sm.session_manager.update_message_content(session_id, user_id, assistant_message_id, response)
        logger.info(f"【Agent重新生成】已覆盖会话 {session_id} 消息 {assistant_message_id}")

    async for sse in drive_sse_stream(
        session_id, run_agent, thinking_queue, agent_result_holder,
        full_response, budget, start_time, on_success=on_success,
    ):
        yield sse


async def _stream_text_message(session_id: str | None, message: str) -> AsyncGenerator[str, None]:
    """把一段定长文本作为 SSE response 事件分块发出。"""
    for i in range(0, len(message), 15):
        chunk = message[i:i + 15]
        yield encode_sse({'type': 'response', 'content': chunk, 'session_id': session_id})
        await asyncio.sleep(0.02)


async def get_confirm_action_stream_response(
    action: dict,
    confirmed: bool,
    user_id: str,
) -> AsyncGenerator[str, None]:
    """执行或取消一条待确认高风险动作，并以 SSE 流式返回结果。

    - confirmed=True：直接调用原工具协程（已设 confirmed 上下文），不再跑整个 Agent。
    - confirmed=False：放弃执行，回一条取消说明。
    两种情况都把结果作为独立 assistant 消息追加到会话。
    """
    session_id = action.get("session_id")
    tool_id = action.get("tool_id")
    args = action.get("args") or {}

    yield encode_sse({'type': 'response', 'content': '', 'session_id': session_id})

    if not confirmed:
        message = f"已取消高风险操作（{tool_id}），未执行。"
    else:
        from app.agent.skill_registry import tool_registry
        from app.agent.tool_guard import wrap_tool
        try:
            tool_def = tool_registry.get(tool_id)
        except KeyError:
            message = f"未找到工具「{tool_id}」，无法执行确认操作。"
            tool_def = None

        if tool_def is not None:
            set_current_user_id(user_id)
            set_current_session_id(session_id)
            set_confirmed_action(True)
            set_thinking_callback(None)
            set_runtime_state({"tool_calls": 0, "max_tool_calls": 1})
            try:
                result = await wrap_tool(tool_def).ainvoke(args)
                message = str(result)
            except Exception as exc:
                logger.error(f"【确认执行】工具 {tool_id} 执行失败: {exc}", exc_info=True)
                message = f"执行确认操作时出错: {exc}"

    if session_id:
        try:
            await sm.session_manager.append_assistant_message(session_id, user_id, message)
        except Exception as exc:
            logger.warning(f"【确认执行】追加结果消息失败: {exc}")

    async for sse in _stream_text_message(session_id, message):
        yield sse
    yield encode_sse({'type': 'done', 'session_id': session_id})
