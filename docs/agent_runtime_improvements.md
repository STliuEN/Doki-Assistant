# Agent 运行时

本文说明当前 Agent 请求如何从 HTTP 进入 LangChain AgentExecutor、如何产生 SSE、如何执行工具以及如何落库。尚未完成的改进统一维护在 [全量重构开发计划](./roadmap_next.md)。

## 当前模块

```text
backend/app/router/chat.py
backend/app/services/agent_run_service.py
backend/app/agent/
  factory.py
  context_builder.py
  streaming.py
  intent_router.py
  skill_registry.py
  tool_context.py
  tool_guard.py
  runtime/
    budget.py
    events.py
    event_pump.py
    sse_driver.py
backend/app/services/database_session_manager.py
backend/app/services/pending_action_store.py
```

旧版 `backend/app/agent/agent.py` 已删除。不要再向该路径添加兼容 shim 或新逻辑。

## 请求准备

聊天入口：

```text
POST /chat/agent/query/stream
POST /chat/session/{session_id}/messages/{message_id}/regenerate/stream
POST /chat/agent/confirm
```

普通查询和重新生成都会先调用 `prepare_agent_run`：

```text
request
  -> JWT -> user_id
  -> resolve UserModelConfig
  -> validate prompt_type
  -> determine candidate skills
  -> route_skills, unless explicit tool_ids are supplied
  -> MCP ensure_fresh
  -> resolve_skills
  -> build_chat_system_prompt
  -> AgentRunPlan(model_config, system_prompt, tools, notices)
```

Prompt 模式目前有：

- `main_prompt`：默认助手。
- `chat_creative_prompt`：创意伙伴。
- `chat_strict_prompt`：严谨助手。
- `chat_teacher_prompt`：教学助手。

`build_chat_system_prompt` 总是先加入全局 `main_prompt`，然后加入启用 Skill、可用 Tool、运行提示和可选回答风格。风格 Prompt 不能覆盖全局规则和工具边界。

## Skill 预路由

本节描述当前标准 Skill A 级和有限 B 级运行桥接。标准 package version、digest、Storage key、Registry revision 和 effective grants 进入持久 SkillRunBinding；A 级指令直接注入，B 级资源通过绑定到本轮 immutable version 的只读工具渐进读取，并与其他 Tool 共用调用预算。CapabilityGrant、private Skill/Tool 过滤、确认动作版本固定、多实例 revision/outbox reconcile 和 stale Registry `503` 已进入运行合同。当前仍缺 per-user scope、跨多次资源读取的累计 token 预算、durable import worker 和 C 级独立 runner/沙箱；在这些门禁完成前不得宣称通用可执行 Skill 支持。目标合同见[标准 Skill 接入需求规格](./standard_skill_integration_requirements.md)。

前端传入的 `skill_ids` 是本轮候选允许集：

- 未传时使用 registry 中的默认 Skill。
- 传入时只允许在这些 Skill 中路由。
- `always_on` 或不可路由 Skill 按 registry 规则保留。
- 显式传入 `tool_ids` 时可跳过意图收窄，但仍要经过可见性、CapabilityGrant 和 Tool policy 的授权交集。

`resolve_skills` 输出：

- 最终 Skill IDs。
- Tool IDs 和已包装的 LangChain tools。
- 注入 system prompt 的 `SKILL.md` 内容。
- 未找到或不可用 Tool 的 notices。

每轮计划会持久记录 Skill version、digest、Registry revision 和 effective grants；高风险确认继续绑定同一运行版本与授权快照。落后实例无法对账到目标 revision 时抛出统一 `SkillRegistryStaleError`，HTTP 层返回 `503`，不会静默继续使用陈旧 Registry。

MCP registry 处于错误态时，`ensure_fresh` 会在请求准备阶段尝试惰性刷新；健康状态不会每轮执行完整 discovery。

## 上下文构造

`context_builder.py` 负责把数据库消息转换成 LangChain messages。

支持的前端策略：

- `current_only`：只使用当前输入。
- `low/medium/high`：按对应 token 预算裁剪历史。
- `custom`：按自定义轮数和 token 限制。
- `auto`：短会话裁剪；长会话使用已保存摘要和近期窗口。

Query 使用 `build_query_context`，regenerate 使用 `build_regenerate_context`。后者必须排除被重新生成的旧 assistant 回答，避免模型把旧答案当作上下文继续扩写。

上下文结果至少包含：

- 原始 history。
- summary。
- 转换后的 `chat_history`。
- 总轮数与是否使用摘要等元数据。

当前摘要边界仍有改进空间，尤其是删除/重新生成消息后的覆盖范围。

## AgentFactory

`factory.py` 每轮创建新的 AgentExecutor：

1. 根据用户模型配置或系统 `.env` 创建 chat model。
2. 创建包含 system、history、human input 和 scratchpad 的 prompt。
3. 使用本轮已解析 Tool 创建 tool-calling agent。
4. 创建 `AgentExecutor`，并从运行预算读取 `max_iterations`。

模型选择顺序：

- 请求指定且属于当前用户的 `UserModelConfig`。
- 否则使用系统默认模型。
- 系统默认由 `LLM_TYPE` 选择 ALIYUN 或 OLLAMA。

AgentExecutor 不作为全局共享实例；全局 `agent_factory` 只保存工厂配置。

## 运行上下文

`streaming.bind_run_context` 在每轮执行前一次性设置 contextvars：

- 当前 `user_id`。
- 当前 `session_id`。
- thinking callback。
- RAG retrieval settings。
- 是否已经确认高风险动作。
- 本轮工具调用计数和上限。

工具依赖这些值进行用户隔离、RAG 参数读取、事件上报和高风险确认。新增运行入口时必须复用 `bind_run_context`，不能只设置部分字段。

## SSE 编排

`streaming.py` 负责 query、regenerate 和 confirm 的入口差异，`runtime/sse_driver.py` 负责 query 与 regenerate 共用的流生命周期。

```text
streaming.py
  -> create thinking_queue and run_id
  -> build context
  -> AgentFactory.create_agent_executor
  -> event_pump.stream_agent_events
  -> sse_driver.drive_sse_stream
  -> on_success stores or replaces message
```

`drive_sse_stream` 的行为：

1. 先发送一个空的 `response` 帧，建立前端消息容器。
2. 并行运行 Agent task，并转发 queue 中的事件。
3. 超过 `max_runtime_seconds` 时取消 Agent task。
4. 保留已产生的部分回答，并追加停止说明。
5. 成功时执行 `on_success` 落库。
6. 最后发送 `done`；错误路径发送 `error` 后仍发送 `done`。

Query 的 `on_success` 新增一组 user/assistant 消息；regenerate 的 `on_success` 覆盖指定 assistant 消息。

## LangChain 事件

`runtime/event_pump.py` 使用：

```python
agent_executor.astream_events(inputs, version="v2")
```

映射规则：

| LangChain event | Doki event |
|-----------------|------------|
| `on_chat_model_stream` | `response` 增量 |
| `on_tool_start` | `thinking` / `tool_start` |
| `on_tool_end` | `thinking` / `tool_end` |
| `on_tool_error` | `thinking` / `tool_error` |

工具执行期间也可能产生内部 LLM token，例如 RAG HyDE 或摘要。event pump 使用 tool depth 屏蔽这些中间 token，只有工具区间之外的模型输出才进入最终回答和落库文本。

非流式供应商如果只在 `on_chat_model_end` 返回完整内容，event pump 会补发一次最终回答。

## SSE 合同

所有 chat、knowledge、note 和 translate SSE 数据帧都包含
`schema_version: "1.0"`。为保持现有前端兼容，事件专有字段仍位于 JSON 顶层；
当前没有已落地的统一 `payload`、`sequence` 或 `timestamp` 包装层。

### response

```json
{
  "schema_version": "1.0",
  "type": "response",
  "content": "token or chunk",
  "session_id": "optional"
}
```

初始空 response 和确认动作的 response 带 `session_id`；普通 Agent token 事件当前可能省略该字段。客户端以最终 `done.session_id` 作为会话确认值。

### thinking

```json
{
  "schema_version": "1.0",
  "type": "thinking",
  "stage": "tool_start",
  "content": "开始调用 search_notes_tool",
  "details": {
    "run_id": "...",
    "elapsed_ms": 123,
    "tool": "search_notes_tool",
    "tool_call_index": 1
  }
}
```

### waiting_confirmation

```json
{
  "schema_version": "1.0",
  "type": "waiting_confirmation",
  "stage": "tool_confirmation",
  "content": "操作需要确认",
  "details": {
    "tool": "delete_memory",
    "risk_level": "high",
    "pending_action_id": "..."
  }
}
```

### error 和 done

```json
{"schema_version": "1.0", "type": "error", "content": "错误信息", "session_id": "..."}
{"schema_version": "1.0", "type": "done", "session_id": "..."}
```

前端必须在处理 `thinking`、`waiting_confirmation`、`error` 和 `done` 前 flush 尚未提交的 response buffer。

## 运行预算

配置位于 `backend/app/config/agent.yaml`：

```yaml
runtime:
  max_iterations: 160
  max_tool_calls: 120
  max_runtime_seconds: 1200
  max_output_chars_per_tool: 16000
```

语义：

- `max_iterations`：AgentExecutor 最大迭代数。
- `max_tool_calls`：GuardedTool 每轮最多开始执行的工具数量。
- `max_runtime_seconds`：SSE driver 的整轮墙钟时间上限。
- `max_output_chars_per_tool`：SSE tool event 中 output preview 的上限。

每个 Tool 自己的 `max_output_chars` 决定返回给 Agent 的实际输出截断长度，两者不是同一个限制。

## GuardedTool

所有解析后的本地 Tool 和 MCP Tool 都应通过 `GuardedTool.wrap`：

1. 检查本轮工具调用次数。
2. 如需确认，保存 pending action 并返回阻断说明。
3. 使用 Tool 自己的 `timeout_seconds` 执行。
4. 使用 Tool 自己的 `max_output_chars` 截断结果。

风险元数据来源：

```yaml
risk_level: low | medium | high
requires_confirmation: true | false
timeout_seconds: 30
max_output_chars: 10000
```

`risk_level=high` 本身只用于描述风险；是否阻断由 `requires_confirmation` 决定。高风险写操作应同时设置 `requires_confirmation: true`。

## 高风险确认

首次调用：

```text
GuardedTool
  -> save_pending_action in Redis
  -> emit waiting_confirmation
  -> do not execute inner tool
```

pending action：

- 默认 TTL 600 秒。
- 包含 user、session、tool、args 和 MCP 来源信息。
- 取出时校验 `user_id`。
- 确认或取消时一次性消费，不能重复提交。

确认入口：

```text
POST /chat/agent/confirm
  -> take_pending_action
  -> confirmed=false: append cancellation message
  -> confirmed=true: lookup ToolDefinition
                     wrap with GuardedTool
                     set confirmed context
                     execute with one-tool budget
  -> append assistant result
  -> response chunks + done
```

确认执行仍经过 GuardedTool 的超时和输出截断，不重新运行整个 Agent。

## 前端消费

当前聊天流逻辑位于：

```text
front/src/features/chat/hooks/useChatStream.ts
front/src/features/chat/types.ts
front/src/features/chat/storage.ts
front/src/features/chat/__tests__/useChatStream.test.ts
```

`AIChat.tsx` 负责页面组合和设置，但 SSE parsing、buffer 和回调已经进入 `useChatStream`。后续拆分应继续把 Skill catalog、聊天设置和消息渲染移入 feature，而不是把流逻辑搬回页面。

## 验证

```powershell
cd backend
uv run pytest tests\test_agent_run_service.py tests\test_agent_runtime.py tests\test_chat_stream_contract.py

cd ..\front
npm run test
```

离线整链路验证：

```powershell
cd backend
uv run python ..\benchmarks\runners\run_benchmarks.py --suite smoke --offline --fail-under 0.9
```

## 已知边界

- 没有持久化的 Agent run 表，运行状态主要存在于 SSE、日志和最终消息中。
- 摘要覆盖边界在消息删除和重新生成后仍需加强。
- 工具错误分类尚未形成跨本地 Tool、MCP 和 RAG 的统一枚举。
- 客户端断开后的取消与资源清理缺少专门的集成测试。
- 运行预算当前是全局 YAML 配置，不支持用户或任务级策略。
