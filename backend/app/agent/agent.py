import asyncio
import json
import os
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import uuid4

import yaml
from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import BaseMessage
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool
from langchain_ollama import ChatOllama

from app.agent.agent_middleware import get_middleware
from app.agent.skill_registry import get_default_tools
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
from app.services import session_manager as sm
from app.utils.model_provider import create_chat_model_from_config, create_ollama_chat_model
from app.utils.prompt_loader import load_prompt


DEFAULT_RUNTIME_BUDGET = {
    "max_iterations": 160,
    "max_tool_calls": 120,
    "max_runtime_seconds": 1200,
    "max_output_chars_per_tool": 16000,
}


def get_runtime_budget() -> dict:
    config_path = Path(__file__).parents[1] / "config" / "agent.yaml"
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        data = {}
    runtime = data.get("runtime") if isinstance(data, dict) else {}
    if not isinstance(runtime, dict):
        runtime = {}
    budget = DEFAULT_RUNTIME_BUDGET.copy()
    for key, default in DEFAULT_RUNTIME_BUDGET.items():
        value = runtime.get(key)
        if isinstance(value, int) and value > 0:
            budget[key] = value
        else:
            budget[key] = default
    return budget


def preview(value, limit: int = 1000) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def runtime_event(stage: str, content: str, details: dict | None = None) -> dict:
    return {
        "type": "thinking",
        "stage": stage,
        "content": content,
        "details": details or {},
    }


def _chunk_text(chunk) -> str:
    """从 on_chat_model_stream 的 chunk 中提取纯文本增量。"""
    content = getattr(chunk, "content", "") or ""
    if isinstance(content, str):
        return content
    # 某些供应商返回分块列表（如 [{"type":"text","text":"..."}]）
    parts = []
    for item in content:
        if isinstance(item, dict):
            parts.append(item.get("text", "") or item.get("content", "") or "")
        else:
            parts.append(str(item))
    return "".join(parts)


async def stream_agent_events(
    agent_executor: AgentExecutor,
    inputs: dict,
    thinking_queue: asyncio.Queue,
    thinking_callback,
    full_response: list[str],
    budget: dict,
) -> None:
    """用 astream_events 驱动 Agent，实现 token 级流式 + 真正的 tool 事件。

    - on_chat_model_stream -> 仅在“工具区间之外”把文本增量作为 response 事件流式输出。
      工具内部（如 RAG 的 HyDE 假设文档、摘要生成）也会触发 on_chat_model_stream，
      这些是中间产物，必须屏蔽，否则会把假设文档当成回答流给用户。
    - on_tool_start/on_tool_end/on_tool_error -> 结构化 thinking 事件。
    只有工具区间之外的最终回答增量才累加进 full_response 供落库。
    """
    tool_index = 0
    tool_depth = 0  # >0 表示正处于某个工具执行期间，其内部 LLM 输出不应作为回答流出
    streamed_any = False
    last_final_text = ""  # 工具区间之外最后一次完整模型输出，作为回答兜底
    async for event in agent_executor.astream_events(inputs, version="v2"):
        kind = event.get("event")
        if kind == "on_chat_model_stream":
            if tool_depth > 0:
                continue  # 工具内部 LLM（HyDE/摘要等）的 token，不流式给用户
            text = _chunk_text(event["data"].get("chunk"))
            if text:
                streamed_any = True
                full_response.append(text)
                await thinking_queue.put({"type": "response", "content": text})
        elif kind == "on_chat_model_end":
            if tool_depth == 0:
                output = event["data"].get("output")
                content = getattr(output, "content", "") if output is not None else ""
                if content:
                    last_final_text = content if isinstance(content, str) else _chunk_text(output)
        elif kind == "on_tool_start":
            tool_index += 1
            tool_depth += 1
            await thinking_callback(runtime_event(
                "tool_start",
                f"开始调用 {event.get('name')}",
                {
                    "tool": event.get("name"),
                    "tool_call_index": tool_index,
                    "input_preview": preview(event["data"].get("input"), 1000),
                },
            ))
        elif kind == "on_tool_end":
            tool_depth = max(0, tool_depth - 1)
            await thinking_callback(runtime_event(
                "tool_end",
                f"{event.get('name')} 执行完成",
                {
                    "tool": event.get("name"),
                    "tool_call_index": tool_index,
                    "output_preview": preview(event["data"].get("output"), budget["max_output_chars_per_tool"]),
                },
            ))
        elif kind == "on_tool_error":
            tool_depth = max(0, tool_depth - 1)
            await thinking_callback(runtime_event(
                "tool_error",
                f"{event.get('name')} 执行出错",
                {
                    "tool": event.get("name"),
                    "error": preview(event["data"].get("error"), 500),
                },
            ))

    # 兜底：模型未产生流式增量（如非流式供应商）但有完整最终输出时补发。
    if not streamed_any and last_final_text:
        full_response.append(last_final_text)
        await thinking_queue.put({"type": "response", "content": last_final_text})


async def summarize_history(
    agent_factory_instance: "AgentFactory",
    history: list[tuple[str, str]],
    previous_summary: str = "",
    model_config: UserModelConfig | None = None,
) -> str:
    if not history:
        return previous_summary

    transcript_parts = []
    for index, (user_msg, assistant_msg) in enumerate(history, start=1):
        transcript_parts.append(f"第 {index} 轮\n用户: {user_msg}\n助手: {assistant_msg}")
    transcript = "\n\n".join(transcript_parts)
    prompt = (
        "请把以下旧对话压缩成给后续 Agent 使用的长期上下文摘要。"
        "保留用户目标、偏好、重要约束、未完成事项、关键决策和需要继续跟进的事实。"
        "不要编造知识库、笔记或记忆中心里的事实；这些事实应由工具实时查询。"
        "用中文，控制在 800 字以内。\n\n"
        f"已有摘要:\n{previous_summary or '无'}\n\n"
        f"旧对话:\n{transcript}"
    )
    model = agent_factory_instance._create_chat_model(model_config=model_config)
    response = await model.ainvoke([
        SystemMessage(content="你是对话上下文压缩器，只输出摘要正文。"),
        HumanMessage(content=prompt),
    ])
    return str(response.content).strip()


def build_chat_history_messages(summary: str, history: list[tuple[str, str]]) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    if summary:
        messages.append(SystemMessage(content=f"以下是旧对话摘要，供延续上下文使用：\n{summary}"))
    for user_msg, assistant_msg in history:
        messages.append(HumanMessage(content=user_msg))
        from langchain_core.messages import AIMessage
        messages.append(AIMessage(content=assistant_msg))
    return messages


class AgentFactory:
    """
    生产 Agent 工厂类
    支持：
    - 每次调用创建全新的 AgentExecutor 实例
    - 动态注入工具、提示词、模型配置
    - 支持异步流式调用
    """

    def __init__(
            self,
            model: str = "qwen3-max",
            api_key: str | None = None,
            default_tools: list[BaseTool] | None = None,
            default_middleware: list | None = None,
            default_system_prompt: str | None = None,
    ):
        """
        初始化工厂配置（仅配置，不创建实例）
        :param model: 默认模型名称
        :param api_key: 默认 API Key（不传则从env读取）
        :param default_tools: 默认工具列表
        :param default_system_prompt: 默认系统提示词
        """
        self.model = model
        self.api_key = api_key or os.getenv("CHAT_API_KEY")
        self.default_tools = default_tools or self._get_default_tools()
        self.default_middleware = default_middleware or self._get_default_middleware()
        self.default_system_prompt = default_system_prompt or self._get_default_system_prompt()

    @staticmethod
    def _get_default_tools() -> list[BaseTool]:
        """获取默认工具列表"""
        return get_default_tools()

    def _get_default_middleware(self) -> list:
        """获取默认中间件列表"""
        return get_middleware()

    @staticmethod
    def _get_default_system_prompt() -> str:
        """获取默认系统提示词"""
        return load_prompt('main_prompt')

    def _create_chat_model(self, custom_model: str | None = None, model_config: UserModelConfig | None = None):
        """内部方法：根据LLM_TYPE创建聊天模型实例"""
        if model_config is not None:
            logger.info(f"Agent using user model config: {model_config.provider} / {model_config.model_name}")
            return create_chat_model_from_config(model_config, streaming=True)

        llm_type = os.getenv("LLM_TYPE", "ALIYUN").upper()

        if llm_type == "OLLAMA":
            model_name = custom_model or os.getenv("OLLAMA_MODEL_NAME", self.model)
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

            logger.info(f"🤖 Agent使用Ollama模型: {model_name}")

            return create_ollama_chat_model(
                model_name=model_name,
                base_url=base_url,
                streaming=True,
            )

        elif llm_type == "ALIYUN":
            api_key = os.getenv("ALIYUN_ACCESS_KEY_SECRET")
            base_url = os.getenv("ALIYUN_BASE_URL")
            model_name = custom_model or os.getenv("ALIYUN_MODEL_NAME", os.getenv("CHAT_MODEL_NAME", self.model))

            logger.info(f"🤖 Agent使用阿里云百炼模型: {model_name}")

            return ChatTongyi(
                model=model_name,
                api_key=api_key,
                base_url=base_url,
                streaming=True,
                top_p=0.7,
            )

        else:
            raise ValueError(f"不支持的LLM_TYPE: {llm_type}，可选值: ALIYUN, OLLAMA")

    def _create_prompt(self, custom_system_prompt: str | None = None) -> ChatPromptTemplate:
        """内部方法：创建提示词模板"""
        return ChatPromptTemplate.from_messages([
            ("system", "{system_prompt}"),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])

    def create_agent_executor(
            self,
            custom_tools: list[BaseTool] | None = None,
            custom_model: str | None = None,
            model_config: UserModelConfig | None = None,
            custom_system_prompt: str | None = None,
            verbose: bool = True,
            return_intermediate_steps: bool = True,
            **kwargs
    ) -> AgentExecutor:
        """
        核心工厂方法：创建全新的 AgentExecutor 实例
        每次调用都会生成新的实例，彻底避免全局状态污染

        :param custom_tools: 自定义工具列表（覆盖默认）
        :param custom_model: 自定义模型（覆盖默认）
        :param custom_system_prompt: 自定义系统提示词（覆盖默认）
        :param verbose: 是否打印详细日志
        :param return_intermediate_steps: 是否返回中间步骤
        :param kwargs: 其他 AgentExecutor 参数
        :return: 全新的 AgentExecutor 实例
        """
        # 1. 创建组件（每次都重新创建，避免全局状态污染）
        chat_model = self._create_chat_model(custom_model, model_config)
        prompt = self._create_prompt()
        tools = self.default_tools if custom_tools is None else custom_tools

        # 2. 创建 Agent
        agent = create_tool_calling_agent(chat_model, tools, prompt)

        # 3. 创建 Executor
        return AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=verbose,
            return_intermediate_steps=return_intermediate_steps,
            handle_parsing_errors=True,
            max_iterations=get_runtime_budget()["max_iterations"],
            **kwargs
        )


# 初始化全局工厂配置
agent_factory = AgentFactory()


def get_agent_executor():
    """
    获取AgentExecutor实例，用于LangGraph
    :return: AgentExecutor实例
    """
    return agent_factory.create_agent_executor()


async def get_agent_response(
        query: str,
        history: list[tuple] | None = None,
        user_id: str | None = None,
        custom_tools: list[BaseTool] | None = None,
        **kwargs
):
    """
    获取 Agent 响应（使用工厂创建实例）
    :param query: 用户查询
    :param history: 会话历史 [(user_msg, assistant_msg), ...]
    :param user_id: 用户ID
    :param custom_tools: 自定义工具（可选，用于动态切换工具）
    :param kwargs: 其他工厂参数
    :return: 响应结果
    """
    if user_id:
        set_current_user_id(user_id)

    try:
        # 1. 从工厂获取全新的 Executor 实例
        agent_executor = agent_factory.create_agent_executor(custom_tools=custom_tools, **kwargs)

        # 2. 构建聊天历史
        chat_history: list[BaseMessage] = []
        if history:
            from langchain_core.messages import AIMessage, HumanMessage
            for user_msg, assistant_msg in history:
                chat_history.append(HumanMessage(content=user_msg))
                chat_history.append(AIMessage(content=assistant_msg))

        # 3. 流式执行
        full_response = []
        steps = []
        async for chunk in agent_executor.astream({
            "input": query,
            "chat_history": chat_history,
            "system_prompt": agent_factory.default_system_prompt
        }):
            if "output" in chunk:
                full_response.append(chunk["output"])
            elif "intermediate_steps" in chunk:
                for action, observation in chunk["intermediate_steps"]:
                    # 记录日志
                    logger.info(f"\n\n🧠 [Agent 思考] {action.log}")
                    logger.info(f"🛠️ [调用工具] {action.tool}")
                    logger.info(f"📥 [工具输入] {action.tool_input}")
                    logger.info(f"📤 [工具结果] {observation}\n")
                    # 收集步骤
                    steps.append({
                        "thought": action.log,
                        "tool": action.tool,
                        "tool_input": action.tool_input,
                        "tool_output": observation
                    })

        return {
            "response": "".join(full_response) if full_response else "抱歉，我无法理解您的请求。",
            "steps": steps
        }

    except Exception as e:
        logger.error(f"Agent 执行错误: {str(e)}", exc_info=True)
        return {
            "response": f"抱歉，处理您的请求时出现了错误: {str(e)}",
            "steps": []
        }

async def get_agent_stream_response(
        query: str,
        session_id: str,
        user_id: str,
        model_config: UserModelConfig | None = None,
        custom_tools: list[BaseTool] | None = None,
        context_settings=None,
        rag_retrieval_settings=None,
        **kwargs
) -> AsyncGenerator[str, None]:
    """
    获取 Agent 流式响应（包含思考过程，实时推送）
    :param query: 用户查询
    :param session_id: 会话 ID
    :param user_id: 用户 ID
    :param custom_tools: 自定义工具（可选）
    :param kwargs: 其他参数
    :return: 流式响应生成器
    """

    thinking_queue = asyncio.Queue()
    run_id = str(uuid4())
    budget = get_runtime_budget()
    start_time = time.monotonic()
    agent_result_holder = {"response": None, "error": None, "stop_reason": "completed"}
    agent_done = asyncio.Event()
    full_response: list[str] = []

    async def thinking_callback(data: dict):
        """思考过程回调函数，将事件放入队列"""
        data.setdefault("type", "thinking")
        data.setdefault("details", {})
        data["details"].setdefault("run_id", run_id)
        data["details"].setdefault("elapsed_ms", int((time.monotonic() - start_time) * 1000))
        logger.info(f"【思考过程】{data.get('stage', 'unknown')}: {data.get('content', '')}")
        await thinking_queue.put(data)

    async def run_agent():
        """在独立任务中执行 Agent"""
        try:
            set_current_user_id(user_id)
            set_current_session_id(session_id)
            set_thinking_callback(thinking_callback)
            set_rag_retrieval_settings(rag_retrieval_settings)
            set_confirmed_action(False)
            set_runtime_state({"tool_calls": 0, "max_tool_calls": budget["max_tool_calls"]})

            await thinking_callback(runtime_event("start", "正在准备上下文、模型和可用工具...", {
                "budget": budget,
            }))

            context = await sm.session_manager.get_context_with_summary(session_id, user_id, context_settings)
            history = context["history"]
            summary = context.get("summary", "")
            if context.get("history_for_summary"):
                try:
                    summary = await summarize_history(
                        agent_factory,
                        context["history_for_summary"],
                        previous_summary=summary,
                        model_config=model_config,
                    )
                    await sm.session_manager.update_session_summary(
                        session_id,
                        user_id,
                        summary,
                        context.get("summary_boundary_id"),
                        sm.session_manager.estimate_tokens(summary),
                    )
                    context["used_summary"] = True
                except Exception as exc:
                    logger.warning(f"【上下文摘要】生成失败，回退裁剪: {exc}")
                    history = await sm.session_manager.get_context(session_id, user_id, context_settings)
                    summary = ""

            await thinking_callback(runtime_event("context", f"已载入 {len(history)} 轮近期上下文。", {
                "history_turns": len(history),
                "total_turns": context.get("total_turns", len(history)),
                "used_summary": bool(summary),
                "summary_tokens": sm.session_manager.estimate_tokens(summary) if summary else 0,
            }))
            logger.info(f"【Agent流式响应】获取会话历史成功，历史记录数: {len(history)}")

            chat_history = build_chat_history_messages(summary, history)

            agent_executor = agent_factory.create_agent_executor(custom_tools=custom_tools, model_config=model_config, **kwargs)
            tool_names = [tool.name for tool in (custom_tools or [])]
            await thinking_callback(runtime_event("tools", f"本轮可用工具：{', '.join(tool_names) if tool_names else '无'}。", {
                "tools": tool_names,
            }))

            system_prompt = kwargs.get("custom_system_prompt") or agent_factory.default_system_prompt
            await thinking_callback(runtime_event("agent", "Agent 正在执行推理和工具调用..."))

            await stream_agent_events(
                agent_executor,
                {"input": query, "chat_history": chat_history, "system_prompt": system_prompt},
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
        finally:
            agent_done.set()

    # 启动 Agent 执行任务
    agent_task = asyncio.create_task(run_agent())

    try:
        logger.info(f"【Agent流式响应】开始处理请求，用户ID: {user_id}, 会话ID: {session_id}, 查询: {query}")

        # 先发送初始响应
        yield f"data: {json.dumps({'type': 'response', 'content': '', 'session_id': session_id}, ensure_ascii=False)}\n\n"

        # 持续监听队列并实时推送思考事件，同时等待 Agent 完成
        while not agent_done.is_set():
            if time.monotonic() - start_time > budget["max_runtime_seconds"]:
                agent_result_holder["stop_reason"] = "timeout"
                agent_task.cancel()
                await thinking_callback(runtime_event("stopped", "已达到最长运行时间，正在停止任务。", {
                    "max_runtime_seconds": budget["max_runtime_seconds"],
                    "duration_ms": int((time.monotonic() - start_time) * 1000),
                }))
                break
            try:
                # 使用短超时轮询队列，实现实时推送
                event = await asyncio.wait_for(thinking_queue.get(), timeout=0.1)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                thinking_queue.task_done()
            except TimeoutError:
                # 超时是正常的，继续等待
                continue

        # Agent 已完成，推送队列中剩余的所有思考事件
        while not thinking_queue.empty():
            try:
                event = thinking_queue.get_nowait()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                thinking_queue.task_done()
            except asyncio.QueueEmpty:
                break

        # 等待 agent_task 完全结束
        try:
            await agent_task
        except asyncio.CancelledError:
            # 已流式发出的 token 保留，仅补发停止说明并落库完整文本。
            partial = "".join(full_response)
            note = "\n\n[本次任务已停止：达到运行时间预算，可缩小范围后继续。]"
            yield f"data: {json.dumps({'type': 'response', 'content': note}, ensure_ascii=False)}\n\n"
            agent_result_holder["response"] = (partial + note) if partial else note.strip()

        if agent_result_holder["error"]:
            error_message = f"错误: {agent_result_holder['error']}"
            yield f"data: {json.dumps({'type': 'error', 'content': error_message, 'session_id': session_id}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
            return

        # 回答内容已在执行过程中按 token 流式发出，这里只负责落库与收尾。
        response = agent_result_holder["response"] or "".join(full_response)

        # 添加到会话历史
        await sm.session_manager.add_message(session_id, user_id, query, response)
        logger.info("【Agent流式响应】添加到会话历史成功")

        # 发送结束标记
        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id}, ensure_ascii=False)}\n\n"
        logger.info(f"【Agent流式响应】处理完成，会话ID: {session_id}")

    except Exception as e:
        logger.error(f"【Agent流式响应】处理请求失败: {e}", exc_info=True)

        # 取消 agent 任务
        agent_task.cancel()
        try:
            await agent_task
        except asyncio.CancelledError:
            pass

        error_message = f"错误: {str(e)}"
        yield f"data: {json.dumps({'type': 'error', 'content': error_message, 'session_id': session_id}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"


async def _stream_text_message(session_id: str | None, message: str) -> AsyncGenerator[str, None]:
    """把一段定长文本作为 SSE response 事件分块发出。"""
    for i in range(0, len(message), 15):
        chunk = message[i:i + 15]
        yield f"data: {json.dumps({'type': 'response', 'content': chunk, 'session_id': session_id}, ensure_ascii=False)}\n\n"
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

    yield f"data: {json.dumps({'type': 'response', 'content': '', 'session_id': session_id}, ensure_ascii=False)}\n\n"

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
    yield f"data: {json.dumps({'type': 'done', 'session_id': session_id}, ensure_ascii=False)}\n\n"


async def get_agent_regenerate_stream_response(
        session_id: str,
        user_id: str,
        assistant_message_id: int,
        model_config: UserModelConfig | None = None,
        custom_tools: list[BaseTool] | None = None,
        context_settings=None,
        rag_retrieval_settings=None,
        **kwargs
) -> AsyncGenerator[str, None]:
    """重新生成已有 assistant 消息，并用新内容覆盖原消息。"""
    thinking_queue = asyncio.Queue()
    run_id = str(uuid4())
    budget = get_runtime_budget()
    start_time = time.monotonic()
    agent_result_holder = {"response": None, "error": None, "stop_reason": "completed"}
    agent_done = asyncio.Event()
    full_response: list[str] = []

    payload = await sm.session_manager.get_regenerate_payload(session_id, user_id, assistant_message_id)
    query = payload["query"]
    history = sm.session_manager.trim_history(payload["history"], context_settings)
    summary = ""
    if sm.session_manager.should_use_summary(payload["history"], context_settings):
        metadata = await sm.session_manager.get_session_metadata(session_id, user_id)
        summary = metadata.get("summary", "")
        history = payload["history"][-6:]

    async def thinking_callback(data: dict):
        data.setdefault("type", "thinking")
        data.setdefault("details", {})
        data["details"].setdefault("run_id", run_id)
        data["details"].setdefault("elapsed_ms", int((time.monotonic() - start_time) * 1000))
        logger.info(f"【重新生成思考过程】{data.get('stage', 'unknown')}: {data.get('content', '')}")
        await thinking_queue.put(data)

    async def run_agent():
        try:
            set_current_user_id(user_id)
            set_current_session_id(session_id)
            set_thinking_callback(thinking_callback)
            set_rag_retrieval_settings(rag_retrieval_settings)
            set_confirmed_action(False)
            set_runtime_state({"tool_calls": 0, "max_tool_calls": budget["max_tool_calls"]})

            await thinking_callback(runtime_event("start", "正在重新生成回答...", {
                "budget": budget,
            }))

            chat_history = build_chat_history_messages(summary, history)

            agent_executor = agent_factory.create_agent_executor(custom_tools=custom_tools, model_config=model_config, **kwargs)
            tool_names = [tool.name for tool in (custom_tools or [])]
            await thinking_callback(runtime_event(
                "context",
                f"已载入 {len(history)} 轮历史上下文；本轮可用工具：{', '.join(tool_names) if tool_names else '无'}。",
                {"history_turns": len(history), "tools": tool_names},
            ))
            system_prompt = kwargs.get("custom_system_prompt") or agent_factory.default_system_prompt

            await stream_agent_events(
                agent_executor,
                {"input": query, "chat_history": chat_history, "system_prompt": system_prompt},
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
        finally:
            agent_done.set()

    agent_task = asyncio.create_task(run_agent())

    try:
        yield f"data: {json.dumps({'type': 'response', 'content': '', 'session_id': session_id}, ensure_ascii=False)}\n\n"

        while not agent_done.is_set():
            if time.monotonic() - start_time > budget["max_runtime_seconds"]:
                agent_result_holder["stop_reason"] = "timeout"
                agent_task.cancel()
                await thinking_callback(runtime_event("stopped", "已达到最长运行时间，正在停止任务。", {
                    "max_runtime_seconds": budget["max_runtime_seconds"],
                    "duration_ms": int((time.monotonic() - start_time) * 1000),
                }))
                break
            try:
                event = await asyncio.wait_for(thinking_queue.get(), timeout=0.1)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                thinking_queue.task_done()
            except TimeoutError:
                continue

        while not thinking_queue.empty():
            try:
                event = thinking_queue.get_nowait()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                thinking_queue.task_done()
            except asyncio.QueueEmpty:
                break

        try:
            await agent_task
        except asyncio.CancelledError:
            partial = "".join(full_response)
            note = "\n\n[本次任务已停止：达到运行时间预算，可缩小范围后继续。]"
            yield f"data: {json.dumps({'type': 'response', 'content': note, 'session_id': session_id}, ensure_ascii=False)}\n\n"
            agent_result_holder["response"] = (partial + note) if partial else note.strip()

        if agent_result_holder["error"]:
            error_message = f"错误: {agent_result_holder['error']}"
            yield f"data: {json.dumps({'type': 'error', 'content': error_message, 'session_id': session_id}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
            return

        # 回答内容已按 token 流式发出，这里覆盖原 assistant 消息并收尾。
        response = agent_result_holder["response"] or "".join(full_response)
        await sm.session_manager.update_message_content(session_id, user_id, assistant_message_id, response)
        logger.info(f"【Agent重新生成】已覆盖会话 {session_id} 消息 {assistant_message_id}")

        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id}, ensure_ascii=False)}\n\n"
    except Exception as e:
        logger.error(f"【Agent重新生成】处理请求失败: {e}", exc_info=True)
        agent_task.cancel()
        try:
            await agent_task
        except asyncio.CancelledError:
            pass

        error_message = f"错误: {str(e)}"
        yield f"data: {json.dumps({'type': 'error', 'content': error_message, 'session_id': session_id}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
