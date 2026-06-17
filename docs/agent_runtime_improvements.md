# Agent 运行时现状与改进清单

本文细化 Agent 运行时相关工作，并同步当前已经完成的 P0/P1 改动。路线图见 [下一阶段开发计划](./roadmap_next.md)。

## 当前后端链路

核心文件：

```text
backend/app/router/chat.py
backend/app/agent/agent.py
backend/app/agent/skill_registry.py
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
  -> resolve_skills 得到工具实例
  -> 获取上下文：Auto 模式优先 summary + 最近 6 轮，否则裁剪
  -> 创建 AgentExecutor
  -> AgentExecutor.astream
  -> thinking_queue 推送结构化事件
  -> Agent 完成后按 chunk 推送最终回答
  -> 保存或覆盖数据库消息
```

当前最终回答仍是 Agent 完成后再按 chunk 推送，不是模型 token 级实时流。

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

已完成：

- `start`
- `context`
- `tools`
- `agent`
- `tool_end`
- `stopped`
- `done`
- `waiting_confirmation`

待完善：

- 真正的 `tool_start`
- 真正的 `tool_error`
- 每个工具的独立 `duration_ms`
- 各工具内部事件字段完全统一

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
- 工具调用次数超过 `max_tool_calls` 后发 `stopped` 并收束回答。
- 工具输出 preview 按 `max_output_chars_per_tool` 截断。
- 回答会附带 `stop_reason`。

限制：

- `max_tool_calls` 基于 LangChain 返回的 `intermediate_steps` 统计，不能在所有工具真正执行前拦截。
- 要实现更强控制，需要 Tool wrapper 或运行图级别的执行器。

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
- `delete_memory_tool` 当前不会执行删除，而是推送 `waiting_confirmation` 事件。

待完善：

- 确认后继续执行。
- 拒绝后由 Agent 解释或给替代方案。
- pending action 的持久化、过期和用户隔离。

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

待完善：

- 精确维护 `summary_message_id`。
- 避免重复摘要同一段消息。
- 摘要质量检查。
- 使用独立摘要模型配置。

## 当前限制

### 最终回答不是 token 级流式

当前模型虽然以 streaming 创建，但 LangChain Agent 路径中最终输出是 Agent 完成后汇总，再由后端按 15 字符切块发送。用户能看到流式文字，但不是模型实时 token。

短期可以接受。真正 token 级流式可后置评估：

- LangChain `astream_events()`
- LangGraph
- 自定义 tool calling loop

### 工具事件还不是执行器级别

当前 `tool_end` 来自 `intermediate_steps`，意味着工具已经执行完才知道。后续需要统一 wrapper，才能实现：

- tool_start
- tool_error
- 工具级 timeout
- 工具级 max output
- 高风险确认前置拦截

## 下一步建议

### 阶段 1：高风险确认闭环

目标：

- SSE 发 `waiting_confirmation`。
- 前端显示确认/拒绝按钮。
- 后端保存 pending action。
- 确认后执行原工具。
- 拒绝后收束并提示替代方案。

### 阶段 2：Tool wrapper

目标：

- 在 registry 返回给 Agent 前包装工具。
- wrapper 统一处理风险、超时、输出截断和事件上报。
- 所有工具都有一致 `tool_start/tool_end/tool_error`。

### 阶段 3：运行状态持久化

目标：

- 保存 run 状态、开始时间、停止原因、工具调用列表。
- 便于调试和未来恢复。

### 阶段 4：token 级流式评估

目标：

- 评估是否值得引入 `astream_events()` 或 LangGraph。
- 在不牺牲工具确认和权限控制的前提下提升实时性。

## 不建议立即做

- 立即全面迁移 LangGraph。
- 把完整工具输出无上限推给前端。
- 让摘要替代知识库、笔记或记忆检索。
- 在没有确认闭环前接 Shell、文件系统、数据库写入类 MCP 工具。
