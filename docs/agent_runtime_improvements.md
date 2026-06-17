# Agent 运行时改进评估

本文是 [下一阶段开发路线图](./roadmap_next.md) 中“方向一：Agent 运行时体验升级”的详细拆解，记录当前项目在 Agent 长上下文、执行过程流式反馈、长任务循环调用三个方向上的现状与下一步实现方案。

## 当前结论

项目已经具备多 Skill / Tool 编排、SSE 通道、数据库会话历史和 LangChain tool calling Agent 基础，但运行时仍偏“一次请求完整执行完，再把最终答案切块返回”。如果要接近 Codex / Claude 这类可观察、可长时间运行、可反复调用工具的体验，需要补齐三层能力：

1. 会话上下文自动压缩，避免长会话无限堆历史。
2. Agent 执行过程事件化，让前端能实时看到模型调用、工具调用、工具结果和耗时。
3. 长任务循环控制，让 Agent 可以多轮调用工具，同时保留预算、超时、取消和可恢复状态。

## 1. 上下文自动压缩

### 当前条件

- 会话历史保存在 MySQL 的 `chat_sessions` 和 `chat_messages`。
- `DatabaseSessionManager.get_history()` 会按完整历史返回 `(user_message, assistant_message)` 列表。
- `agent.py` 每次请求都会把全部历史转为 `HumanMessage` / `AIMessage`，直接塞进 `chat_history`。
- `ChatSession.metadata_` 和 `ChatMessage.metadata_` 已经存在 JSON 字段，可用于保存摘要、压缩版本、token 估算等元信息。

### 当前缺口

- 没有 token 预算估算。
- 没有历史摘要表或摘要字段的读写策略。
- 没有“保留最近 N 轮 + 压缩更早历史”的拼接逻辑。
- 长对话会持续增加 prompt 长度，导致成本、延迟和上下文溢出风险上升。

### 推荐方案

采用“滚动摘要 + 最近窗口”的结构：

```text
system prompt
  -> conversation_summary（早期对话压缩）
  -> recent_messages（最近 N 轮原文）
  -> current_user_input
  -> agent_scratchpad
```

建议实现：

- 在 `ChatSession.metadata_` 中保存：
  - `summary`: 压缩后的长期对话摘要
  - `summary_updated_at`: 更新时间
  - `summary_message_id`: 摘要覆盖到的最后一条消息 ID
- `get_history()` 或新增 `get_context()` 返回：
  - summary
  - recent history
  - 原始消息统计
- 每次保存新消息后检查是否超过阈值，例如：
  - 消息轮数超过 12 轮
  - 或估算 token 超过 6000
- 超过阈值时异步压缩较早消息，只保留最近 6 轮原文。

### 风险点

- 摘要不能替代工具结果来源。涉及知识库/笔记/记忆事项时，仍应重新调用工具获取事实。
- 摘要 prompt 要保留用户偏好、未完成事项、重要约束，但不要保存敏感 token。
- 压缩失败时必须回退原历史，不能阻断聊天。

## 2. 执行过程流式输出与计时

### 当前条件

- 后端 `/chat/agent/query/stream` 已经使用 SSE。
- `useSSE.ts` 支持 `thinking`、`response`、`done`、`error` 四类聊天事件。
- 前端 `AIChat.tsx` 已有“思考步骤”折叠区域。
- RAG 内部已通过 `thinking_callback` 推送部分检索/重排序过程。
- `AgentExecutor.astream()` 能拿到 `intermediate_steps`，但当前只写日志，没有推给前端。

### 当前缺口

- 最终回答不是模型 token 级实时输出，而是 Agent 完整结束后再按 15 字符切块发送。
- 普通工具调用没有统一发 SSE 事件；只有 RAG 这类工具内部主动调用 callback 时才有 thinking。
- 前端只保存 `currentThinking` 单条文本，没有完整事件列表。
- 没有执行计时字段，如开始时间、结束时间、耗时。
- `agent_middleware.py` 中定义了 LangChain / LangGraph middleware，但当前 `create_tool_calling_agent` / `AgentExecutor` 路径没有实际接入这些 middleware。

### 推荐事件模型

建议扩展 SSE 事件，不再只把 thinking 当作一段文本，而是当作事件流：

```json
{
  "type": "thinking",
  "stage": "tool_start",
  "content": "调用工具 search_notes_tool",
  "details": {
    "run_id": "uuid",
    "tool": "search_notes_tool",
    "input": {"query": "RAG"},
    "started_at": "2026-06-17T12:00:00"
  }
}
```

建议阶段：

- `agent_start`
- `model_start`
- `model_end`
- `tool_start`
- `tool_end`
- `tool_error`
- `agent_end`

每个事件建议包含：

- `run_id`
- `stage`
- `label`
- `content`
- `started_at`
- `ended_at`
- `duration_ms`
- `tool`
- `input`
- `output_preview`
- `error`

### 后端实现建议

- 在 `get_agent_stream_response()` 中处理 `intermediate_steps` 时，把工具调用事件放入 `thinking_queue`。
- 给工具执行包一层统一 wrapper，记录开始、结束、耗时和异常。
- 如果继续用 `AgentExecutor.astream()`，先实现工具级事件；模型 token 级实时输出可后置。
- 若要更细粒度的模型流式 token，需要评估 LangChain `astream_events()` 或迁移到 LangGraph event stream。

### 前端实现建议

- 将 `currentThinking: string` 改成 `thinkingEvents: ThinkingEvent[]`。
- 折叠菜单里按事件列表展示：
  - 步骤名称
  - 状态：运行中 / 成功 / 失败
  - 耗时
  - 工具输入摘要
  - 工具输出摘要
- 顶部显示总耗时，并支持展开单步详情。

## 3. 反复运行调用与长任务控制

### 当前条件

- `AgentExecutor.max_iterations` 已经设置为 `64`，具备比默认更长的工具调用空间。
- 每次请求都会创建新的 `AgentExecutor`，避免全局状态污染。
- skill 预路由会缩小工具集合，降低工具选择噪音。
- 前端 `useSSE` 内部已有 `AbortController`，具备取消请求的基础。

### 当前缺口

- 没有全局 wall-clock 超时，例如单次 Agent 最多运行多少秒。
- 没有工具调用次数预算、模型调用次数预算、token 预算。
- 没有把“已运行多少轮 / 剩余多少预算”展示给用户。
- 没有用户确认机制，高风险工具只能依赖 prompt 约束。
- 没有跨请求继续执行的任务状态；请求断开后 Agent 任务会取消或丢失。
- 达到上限后的处理仍可能返回不友好的停止信息，需要统一收束策略。

### 推荐控制模型

建议引入 `RunBudget`：

```text
max_iterations: 64
max_tool_calls: 32
max_runtime_seconds: 180
max_output_chars_per_tool: 8000
allow_destructive_tools: false
```

执行时维护 `RunState`：

```text
run_id
session_id
user_id
started_at
status: running / waiting_confirmation / completed / failed / cancelled
iteration_count
tool_call_count
last_event_at
```

### 实施建议

- 第一阶段保留 `AgentExecutor`，增加预算检查和 SSE 事件。
- 第二阶段把高风险工具分级：
  - 普通工具：查询、检索、生成
  - 写入工具：创建、更新、完成、延期
  - 高风险工具：删除、清空、外部系统写入
- 第三阶段引入“等待用户确认”状态，让 Agent 可以暂停在某一步，用户确认后继续。
- 第四阶段如果要接近 Codex / Claude 的多步任务体验，建议评估 LangGraph，把 Agent run 变成可持久化状态机。

## 推荐实施顺序

### 阶段一：可观察执行过程

优先级最高。先让用户看见 Agent 正在做什么。

- 后端推送 `agent_start`、`tool_start`、`tool_end`、`tool_error`、`agent_end`
- 事件包含耗时
- 前端 thinking 折叠区改为事件列表

验收标准：

- 用户能看到每次工具调用名称、输入摘要、输出摘要和耗时。
- RAG、笔记搜索、记忆事项查询都能显示清楚过程。

### 阶段二：上下文自动压缩

- 增加会话摘要字段读写
- 拼接 `summary + recent_messages`
- 超阈值自动压缩早期历史

验收标准：

- 长会话不会无限增加 prompt。
- 历史语境仍能保留用户目标、偏好和未完成任务。

### 阶段三：长任务预算与可取消

- 增加运行预算
- SSE 展示轮次和耗时
- 前端暴露停止按钮
- 达到预算时生成收束回答

验收标准：

- Agent 可以多次调用工具完成复杂任务。
- 超时或达到上限时，用户能看到停止原因和已完成步骤。

### 阶段四：可暂停/确认/恢复

- 高风险工具二次确认
- run 状态持久化
- 支持用户确认后继续执行

验收标准：

- 删除、外部写入等动作不会被 Agent 直接误执行。
- 长任务中断后可以继续，而不是从头开始。

## 与现有代码的对应关系

- 后端 SSE 入口：`backend/app/agent/agent.py#get_agent_stream_response`
- Agent 创建：`backend/app/agent/agent.py#AgentFactory.create_agent_executor`
- 会话历史：`backend/app/services/database_session_manager.py`
- 会话模型：`backend/app/models/chat_history.py`
- 工具上下文：`backend/app/agent/tool_context.py`
- 前端 SSE：`front/src/hooks/useSSE.ts`
- 前端折叠面板：`front/src/pages/AIChat.tsx`
- SSE 类型：`front/src/types/api.ts`

## 当前不建议立刻做的事

- 不建议一开始就完全迁移 LangGraph。当前 `AgentExecutor` 还能支撑第一阶段事件化和预算控制。
- 不建议把完整工具输出全部推给前端，应该做摘要和长度限制。
- 不建议让上下文摘要替代 RAG 或笔记检索，事实型用户数据仍应实时检索。
