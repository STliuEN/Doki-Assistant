import asyncio

from langchain_classic.agents import AgentExecutor

from app.agent.runtime.events import chunk_text, preview, runtime_event


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
            text = chunk_text(event["data"].get("chunk"))
            if text:
                streamed_any = True
                full_response.append(text)
                await thinking_queue.put({"type": "response", "content": text})
        elif kind == "on_chat_model_end":
            if tool_depth == 0:
                output = event["data"].get("output")
                content = getattr(output, "content", "") if output is not None else ""
                if content:
                    last_final_text = content if isinstance(content, str) else chunk_text(output)
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
