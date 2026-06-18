# Agent 运行时现状与改进清单

本文细化 Agent 运行时相关工作，并同步当前已经完成的 P0/P1 改动。路线图见 [下一阶段开发计划](./roadmap_next.md)。

## 当前后端链路

核心文件：

```text
backend/app/router/chat.py
backend/app/agent/agent.py
backend/app/agent/skill_registry.py
backend/app/agent/mcp/
backend/app/agent/tool_context.py
backend/app/services/database_session_manager.py
backend/app/config/agent.yaml
backend/app/config/security.yaml
```

当前执行流程：

```text
SSE 请求
  -> JWT 鉴权 user_id
  -> prompt / skill / tool 解析
  -> Skill 预路由
  -> resolve_skills 得到本地 Tool 与 MCP Tool 实例
  -> 获取上下文：Auto 模式优先 summary + 最近 6 轮，否则裁剪
  -> 创建 AgentExecutor
  -> AgentExecutor.astream_events(version="v2")
  -> thinking_queue 推送结构化事件
  -> on_chat_model_stream 增量按 token 推送最终回答
  -> 保存或覆盖数据库消息
```

最终回答通过 `astream_events` 的 `on_chat_model_stream` 事件按模型 token 实时流式推送（`stream_agent_events`，`agent.py`）。

## 当前前端链路

核心文件：

```text
front/src/hooks/useSSE.ts
front/src/pages/AIChat.tsx
front/src/pages/ToolManager.tsx
front/src/api/chat.ts
front/src/types/api.ts
```

支持事件：

```text
thinking
waiting_confirmation
response
done
error
```

thinking 当前仍以文本列表展示，但已能显示结构化 details 中的工具、耗时、风险和停止原因。

## 已完成能力

### 1. 运行 ID 与结构化 details

每轮 Agent 运行会生成 `run_id`，并把它写入 thinking 事件：

```json
{
  "type": "thinking",
  "stage": "tool_end",
  "content": "search_notes_tool 执行完成",
  "details": {
    "run_id": "uuid",
    "elapsed_ms": 1200,
    "tool": "search_notes_tool",
    "tool_call_index": 1,
    "input_preview": "...",
    "output_preview": "..."
  }
}
```

已完成（事件来自 `astream_events`，工具事件为执行器级别真实事件）：

- `start`
- `context`
- `tools`
- `agent`
- `tool_start`
- `tool_end`
- `tool_error`
- `stopped`
- `done`
- `waiting_confirmation`

待完善：

- 各工具内部事件字段进一步统一。

### 2. 运行预算

预算配置位于：

```text
backend/app/config/agent.yaml
```

当前默认值：

```yaml
runtime:
  max_iterations: 160
  max_tool_calls: 120
  max_runtime_seconds: 1200
  max_output_chars_per_tool: 16000
```

已完成：

- `AgentExecutor.max_iterations` 读取配置。
- SSE 外层按 `max_runtime_seconds` 取消任务。
- `GuardedTool` 在工具执行前统计调用次数，超过 `max_tool_calls` 直接硬拦截并发 `stopped`。
- 工具输出按 `max_output_chars_per_tool` 截断。
- 回答会附带 `stop_reason`。

说明：调用次数、超时和确认均由 `GuardedTool`（`tool_guard.py`）在执行前拦截，已不再依赖 `intermediate_steps` 事后统计。

### 3. Tool 风险元数据

Tool 配置支持：

```yaml
risk_level: low | medium | high
requires_confirmation: true | false
timeout_seconds: 30
max_output_chars: 4000
```

已完成：

- `ToolDefinition` 读取风险字段。
- `/tools/catalog` 返回风险字段。
- Tool 管理页可编辑风险字段。
- `delete_memory` 标记为 high。
- 高风险工具执行前由 `GuardedTool` 拦截，保存 pending action 并推送 `waiting_confirmation`。
- 用户确认后经 `POST /chat/agent/confirm` 执行原工具，拒绝则放弃。
- pending action 持久化在 Redis，带 TTL（默认 600s）与 `user_id` 隔离、单次取用（`pending_action_store.py`）。
- MCP tools 进入统一 `ToolDefinition` 后，同样会被 `GuardedTool` 包装。

待完善：

- 拒绝后由 Agent 给出更细的替代方案说明。
- 按工具/风险等级细化确认文案。

### 4. 上下文自动压缩

会话摘要保存在 `ChatSession.metadata_`：

```json
{
  "summary": "...",
  "summary_message_id": null,
  "summary_updated_at": "...",
  "estimated_tokens": 123
}
```

Auto 模式长会话结构：

```text
system prompt
  -> conversation_summary
  -> recent_messages
  -> current_user_input
  -> agent_scratchpad
```

已完成：

- 长会话压缩早期消息。
- 保留最近 6 轮原文。
- 摘要失败回退原裁剪逻辑。
- regenerate 读取已有摘要并保留最近 6 轮。

已完成：

- 通过 `summary_message_id` / `summary_boundary_id` 记录摘要边界，避免重复摘要同一段消息（`database_session_manager.py`）。

待完善：

- 更精确的摘要覆盖边界与质量检查。
- 使用独立摘要模型配置。

## 已落地的运行时基建

以下能力已经实现，作为后续工作的基础：

- **token 级流式**：基于 `astream_events(version="v2")`，最终回答按模型 token 实时推送。
- **执行器级工具事件**：`tool_start / tool_end / tool_error` 来自 `astream_events`，不再依赖 `intermediate_steps`。
- **统一 Tool wrapper**：`GuardedTool`（`tool_guard.py`）在 registry 包装每个工具（`skill_registry.py`），执行前统一处理调用次数、超时、输出截断和高风险确认。
- **高风险确认闭环**：`waiting_confirmation` + pending action 持久化 + `POST /chat/agent/confirm` 续跑/取消。
- **MCP 外部工具来源**：`backend/app/agent/mcp/*` 将 MCP tools/list 发现到的外部工具适配为 LangChain tool，并合并到统一 registry。

## 下一步建议

### 运行状态持久化

目标：

- 保存 run 状态、开始时间、停止原因、工具调用列表。
- 便于调试和未来恢复。

### 摘要与上下文边界优化

目标：

- 更精确地维护摘要覆盖边界，避免遗漏或重复。
- 评估独立摘要模型配置。

### MCP 外部工具治理

目标：

- 完善 MCP 工具管理页、测试调用、错误诊断和审计。
- 高风险 MCP 工具确认后继续统一超时、截断和调用记录。
- 对 Shell、文件系统、数据库写入、外部发送类 MCP server 做默认关闭和 allowlist。

## 不建议立即做

- 立即全面迁移 LangGraph。
- 把完整工具输出无上限推给前端。
- 让摘要替代知识库、笔记或记忆检索。
- 接入 Shell、文件系统、数据库写入类 MCP 工具时，务必标记为高风险并走确认闭环，不要绕过 `GuardedTool` 或等价控制。
