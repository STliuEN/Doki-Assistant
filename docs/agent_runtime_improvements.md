# Agent 运行时改进评估

本文细化 [下一阶段开发计划](./roadmap_next.md) 中运行时相关工作。当前 Agent 已经能用，但还不是可长期运行、可观察、可控风险的 Agent 运行时。

## 当前实现

### 后端链路

- SSE 入口：`backend/app/router/chat.py#/chat/agent/query/stream`
- Agent 执行：`backend/app/agent/agent.py#get_agent_stream_response`
- 重新生成：`backend/app/agent/agent.py#get_agent_regenerate_stream_response`
- 会话上下文：`backend/app/services/database_session_manager.py`
- Skill/Tool：`backend/app/agent/skill_registry.py`
- Skill 预路由：`backend/app/agent/intent_router.py`
- Tool 上下文：`backend/app/agent/tool_context.py`

当前执行流程：

```text
SSE 请求
  -> 鉴权 user_id
  -> prompt / skill / tool 解析
  -> 获取裁剪后的历史
  -> 创建 AgentExecutor
  -> AgentExecutor.astream
  -> thinking_queue 推送 thinking
  -> Agent 完成后按 chunk 推送最终回答
  -> 保存或覆盖数据库消息
```

### 前端链路

- SSE hook：`front/src/hooks/useSSE.ts`
- 对话页：`front/src/pages/AIChat.tsx`
- 支持事件：`thinking / response / done / error`
- thinking 当前以文本列表展示在折叠区。
- 消息刷新会覆盖原 assistant 消息。
- 消息删除会调用后端删除。

## 当前限制

### 1. thinking 事件还不够结构化

已有：

- `start`
- `context`
- `tools`
- `agent`
- `tool:<tool_name>`
- RAG 内部检索事件

缺少：

- 统一 `run_id`
- `tool_start/tool_end/tool_error`
- 耗时
- 状态
- 输入摘要/输出摘要分离
- 前端事件列表和计时

### 2. 最终回答不是 token 级流式

当前模型虽然以 streaming 创建，但 LangChain Agent 路径中最终输出是 Agent 完成后汇总，再由后端按 15 字符切块发送。用户能看到流式文字，但不是模型实时 token。

短期可以接受，优先先做工具过程可观察；真正 token 级流式可后置评估 `astream_events()` 或 LangGraph。

### 3. 上下文只有裁剪，没有摘要

当前 `trim_history` 已支持：

- current_only
- custom 最近 N 轮
- low/medium/high/auto token 粗估

但没有：

- conversation summary
- summary 覆盖到的 message id
- 摘要失败回退策略
- 摘要 prompt

### 4. 长任务没有预算

当前：

- `max_iterations=64`
- 前端 `AbortController` 可以取消请求

缺少：

- wall-clock 超时
- 最大工具调用次数
- 最大工具输出长度
- 停止原因
- 高风险操作暂停确认
- run 状态持久化

## 推荐事件模型

统一 thinking 事件：

```json
{
  "type": "thinking",
  "stage": "tool_end",
  "content": "工具 search_notes_tool 执行完成",
  "details": {
    "run_id": "uuid",
    "status": "success",
    "tool": "search_notes_tool",
    "started_at": "2026-06-17T12:00:00",
    "ended_at": "2026-06-17T12:00:01",
    "duration_ms": 1000,
    "input_preview": "...",
    "output_preview": "...",
    "error": null
  }
}
```

建议阶段：

- `agent_start`
- `skill_route`
- `context_loaded`
- `model_start`
- `tool_start`
- `tool_end`
- `tool_error`
- `agent_end`
- `budget_stop`
- `waiting_confirmation`

## P0 实施顺序

### 阶段 1：工具调用事件化

目标：

- 不改变 Agent 架构，先把现有 `intermediate_steps` 转成结构化事件。
- RAG 内部 thinking 保持兼容，但 `details` 补齐耗时和检索计划。

改动点：

- `agent.py` 中为每次请求生成 `run_id`。
- 捕获 `intermediate_steps` 时发 `tool_end` 事件。
- 如果能包装 Tool 执行，再补 `tool_start`。
- 前端 `currentStepDetails` 替换为 `ThinkingEvent[]`。

验收：

- 用户能看到工具名、输入摘要、输出摘要。
- 工具失败时能看到失败工具。

### 阶段 2：计时与运行状态

目标：

- thinking 区显示总耗时和每步耗时。
- SSE done 事件带停止原因。

改动点：

- 后端记录 `started_at`。
- 每个事件带 `duration_ms`。
- 前端运行中显示计时。

验收：

- 用户能知道 Agent 已运行多久。
- 每个工具调用都有耗时。

### 阶段 3：运行预算

目标：

- 限制长任务失控。

建议：

```text
max_runtime_seconds = 180
max_tool_calls = 32
max_output_chars_per_tool = 8000
```

改动点：

- 增加 `RunBudget`。
- 每次工具结果截断 preview。
- 达到预算时发 `budget_stop` 并生成收束回答。

验收：

- 不会无限执行。
- 达到限制时前端可见原因。

### 阶段 4：高风险确认

目标：

- 删除、清空、外部写入、MCP 高风险工具必须等待用户确认。

改动点：

- `tool.yaml` 增加风险字段。
- Agent 调用前检查工具风险。
- SSE 发 `waiting_confirmation`。
- 前端显示确认/拒绝。
- 后端支持确认后继续或拒绝后收束。

验收：

- 删除类工具不能被 Agent 静默执行。

## P1：上下文自动压缩

推荐结构：

```text
system prompt
  -> conversation_summary
  -> recent_messages
  -> current_user_input
  -> agent_scratchpad
```

实现建议：

- `ChatSession.metadata_` 保存：
  - `summary`
  - `summary_message_id`
  - `summary_updated_at`
  - `estimated_tokens`
- 超过阈值后压缩早期消息。
- 保留最近 6 轮原文。
- 事实型信息仍通过 RAG/Note/Memory 工具查询。

风险：

- 摘要可能丢细节。
- 摘要不能保存敏感 token。
- 摘要失败不能阻断聊天。

## 不建议立即做

- 立即全面迁移 LangGraph。
- 把完整工具输出无上限推给前端。
- 让摘要替代知识库、笔记或记忆检索。
- 在没有权限与确认机制前接 Shell、文件系统、数据库写入类 MCP 工具。

