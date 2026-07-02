import asyncio
import json
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from uuid import uuid4

from app.agent.runtime.events import runtime_event
from app.core.logger_handler import logger


def make_thinking_callback(
    thinking_queue: asyncio.Queue,
    run_id: str,
    start_time: float,
    log_prefix: str,
) -> Callable[[dict], Awaitable[None]]:
    """构造把事件补全元数据后放入队列的思考回调。"""

    async def thinking_callback(data: dict) -> None:
        data.setdefault("type", "thinking")
        data.setdefault("details", {})
        data["details"].setdefault("run_id", run_id)
        data["details"].setdefault("elapsed_ms", int((time.monotonic() - start_time) * 1000))
        logger.info(f"{log_prefix}{data.get('stage', 'unknown')}: {data.get('content', '')}")
        await thinking_queue.put(data)

    return thinking_callback


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def drive_sse_stream(
    session_id: str | None,
    run_agent: Callable[[], Awaitable[None]],
    thinking_queue: asyncio.Queue,
    agent_result_holder: dict,
    full_response: list[str],
    budget: dict,
    start_time: float,
    *,
    on_success: Callable[[str], Awaitable[None]],
) -> AsyncGenerator[str, None]:
    """统一的 SSE 编排：启动 run_agent 任务，实时转发 thinking/response 事件，
    处理超时取消、错误、收尾落库。query 与 regenerate 仅 on_success 落库方式不同。
    """
    agent_done = asyncio.Event()

    async def _runner():
        try:
            await run_agent()
        finally:
            agent_done.set()

    agent_task = asyncio.create_task(_runner())

    try:
        yield _sse({"type": "response", "content": "", "session_id": session_id})

        while not agent_done.is_set():
            if time.monotonic() - start_time > budget["max_runtime_seconds"]:
                agent_result_holder["stop_reason"] = "timeout"
                agent_task.cancel()
                await thinking_queue.put(runtime_event("stopped", "已达到最长运行时间，正在停止任务。", {
                    "run_id": agent_result_holder.get("run_id"),
                    "max_runtime_seconds": budget["max_runtime_seconds"],
                    "duration_ms": int((time.monotonic() - start_time) * 1000),
                }))
                break
            try:
                event = await asyncio.wait_for(thinking_queue.get(), timeout=0.1)
                yield _sse(event)
                thinking_queue.task_done()
            except TimeoutError:
                continue

        # 推送队列中剩余事件
        while not thinking_queue.empty():
            try:
                event = thinking_queue.get_nowait()
                yield _sse(event)
                thinking_queue.task_done()
            except asyncio.QueueEmpty:
                break

        try:
            await agent_task
        except asyncio.CancelledError:
            # 已流式发出的 token 保留，仅补发停止说明并落库完整文本。
            partial = "".join(full_response)
            note = "\n\n[本次任务已停止：达到运行时间预算，可缩小范围后继续。]"
            yield _sse({"type": "response", "content": note, "session_id": session_id})
            agent_result_holder["response"] = (partial + note) if partial else note.strip()

        if agent_result_holder["error"]:
            error_message = f"错误: {agent_result_holder['error']}"
            yield _sse({"type": "error", "content": error_message, "session_id": session_id})
            yield _sse({"type": "done", "session_id": session_id})
            return

        # 回答内容已按 token 流式发出，这里只负责落库与收尾。
        response = agent_result_holder["response"] or "".join(full_response)
        await on_success(response)

        yield _sse({"type": "done", "session_id": session_id})

    except Exception as e:
        logger.error(f"【SSE 编排】处理请求失败: {e}", exc_info=True)
        agent_task.cancel()
        try:
            await agent_task
        except asyncio.CancelledError:
            pass
        error_message = f"错误: {str(e)}"
        yield _sse({"type": "error", "content": error_message, "session_id": session_id})
        yield _sse({"type": "done", "session_id": session_id})


def new_run_id() -> str:
    return str(uuid4())
