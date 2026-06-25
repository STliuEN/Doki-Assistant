# P0 架构解耦改动计划

日期：2026-06-25 ｜ 分支：ai_document_assistant ｜ 关联：docs/roadmap_next.md（P0.1–P0.4）

## 背景与原则

当前 `backend/app/agent/agent.py`（814 行）、`backend/app/router/chat.py`（332 行）、`front/src/pages/AIChat.tsx`（1031 行）职责混杂。本计划只做"降低耦合、稳定边界"，不改业务行为（一处有意的 bug 修正除外，见 P0.1 步骤 1）。

贯穿原则：

1. **先去重，再分文件**：两份 SSE 编排约 80% 重复，先收敛成单一驱动器再拆模块。
2. **每步可独立合入、可回滚**：每个子步骤结束后端能起、前端能跑、`route_skills` 等对外签名不变。
3. **保留兼容入口（shim）**：被外部 import 的符号在原位置留薄 re-export，调用方迁移完再删。
4. **删除死代码不迁移**：`get_agent_response`、`get_agent_executor`、`ChatService.handle_agent_query` 已确认零业务调用方，直接删。

已确认事实（实读代码）：

- 业务侧仅 `chat.py` 与 `chat_service.py` 依赖 `app.agent.agent`。
- `agent_factory` / `get_runtime_budget` 无业务外部调用方。
- contextvar 共 6 个：user_id / session_id / thinking_callback / rag_retrieval_settings / confirmed_action / runtime_state（`tool_context.py`），GuardedTool 依赖其在每轮运行起始被齐全设置。
- 服务层架构决策：采用 **A 方案**——现有 `ChatService` 改名为 `SessionQueryService`，新建 `agent_run_service`，二者职责不重叠。

---

## P0.1 Agent 运行时拆分

### 目标文件与归属

```text
backend/app/agent/
  runtime/
    __init__.py
    budget.py        # DEFAULT_RUNTIME_BUDGET, get_runtime_budget
    events.py        # runtime_event, preview, _chunk_text
    event_pump.py    # stream_agent_events（astream_events→queue）
    sse_driver.py    # 【新】统一 SSE 编排（去重核心）
  factory.py         # AgentFactory, agent_factory, _create_chat_model/_create_prompt
  context_builder.py # summarize_history, build_chat_history_messages, build_query_context, build_regenerate_context
  streaming.py       # get_agent_stream_response / regenerate / confirm（瘦身后）
  agent.py           # 仅保留 re-export shim
```

### 步骤 0：删死代码 + 抽常量（无行为变化）

- 删 `get_agent_response`（agent.py L354）、`get_agent_executor`（L346）、`ChatService.handle_agent_query`（chat_service.py L16）及其 import。
- 移动（纯搬运 + 调 import）：
  - `budget.py` ← agent.py L35–L59
  - `events.py` ← preview / runtime_event / _chunk_text（L62–L90）
  - `event_pump.py` ← stream_agent_events（L93–L166）

### 步骤 1：抽 `sse_driver.py`（去重核心）

把两份函数逐字重复的编排（agent.py L536–L612 与 L755–L814）抽成单一驱动器：

```python
async def drive_sse_stream(
    session_id, run_agent, thinking_queue, agent_result_holder,
    full_response, budget, start_time, *, on_success,
) -> AsyncGenerator[str, None]:
    ...
```

差异点参数化：

- **落库方式**：query 用 `add_message(session_id,user_id,query,resp)`；regenerate 用 `update_message_content(...,message_id,resp)` → 收敛进 `on_success` 回调。
- **取消补发文本是否带 session_id**：现两份不一致（query 无 / regenerate 有）。**统一为带 session_id**——这是有意的 bug 修正，PR 须注明。
- `thinking_callback` 工厂抽出，`log_prefix` 参数区分日志前缀。

### 步骤 2：`factory.py` 注入化（为可测性）

- 移 `AgentFactory` 与模型 / prompt 创建；保留模块级 `agent_factory` 单例。
- `streaming.py` 不直接引用全局单例，改参数默认值注入：
  `async def get_agent_stream_response(..., *, factory: AgentFactory = agent_factory, ...)`，便于单测传 mock factory。

### 步骤 3：`context_builder.py`

- 移 `summarize_history`、`build_chat_history_messages`。
- 抽 `build_query_context(...)`（agent.py L473–L505：取上下文+摘要+回退裁剪）与 `build_regenerate_context(...)`（L694–L701），统一返回 `ContextResult(history, summary, chat_history, meta)`。

### 步骤 4：`streaming.py` 瘦身 + `agent.py` shim

- `run_agent` 闭包仅剩：`bind_run_context()`（封装 6 个 set_*，杜绝两处漂移）→ `build_*_context` → `factory.create_agent_executor` → `event_pump.stream_agent_events`。
- `agent.py` 仅留 re-export：`get_agent_stream_response` / `get_agent_regenerate_stream_response` / `get_confirm_action_stream_response`。

### 风险点

- **contextvar 顺序与齐全度不可动**：封成单一 `bind_run_context(...)`，GuardedTool 硬拦截依赖它。

### 验收与测试足场

新增 `backend/tests/test_agent_runtime.py`：

- `test_get_runtime_budget_*`：yaml 缺失 / 非法值回退默认。
- `test_stream_agent_events_tool_depth`：喂 `on_chat_model_stream`（tool_depth>0 屏蔽）、`on_tool_start/end/error` 序列，断言 response 只含工具区间外增量、thinking 事件含 `run_id`。
- `test_sse_driver_timeout_cancel`：max_runtime_seconds 设极小，断言发 `stopped` 事件且 partial 文本落库。
- 用 fake factory（stub executor）跑通 query / regenerate 两条流，断言各自 `on_success` 落库路径。
- fixture 用 `contextvars.copy_context()` 隔离，避免污染。
- 运行：`.venv/Scripts/python.exe -m pytest backend/tests/`（**勿用 `uv run`**，会误用 conda 缺 yaml）。

验收对齐 roadmap：agent.py 不再是主运行时大文件；普通聊天 / 工具调用 / RAG / 刷新 / 高风险确认 / 停止行为兼容；运行预算、工具事件、上下文摘要有独立单测。

---

## P0.2 Chat 路由瘦身（A 方案）

### 目标文件

```text
backend/app/router/chat.py                     # 薄路由
backend/app/services/agent_run_service.py      # 新建：prepare_agent_run + build_chat_system_prompt + CHAT_PROMPT_MODES
backend/app/services/session_query_service.py  # 现 ChatService 改名而来：RAG / session / reorder
backend/app/router/chat_service.py             # 留 re-export shim
```

职责边界：

- `agent_run_service`：一轮 Agent 跑之前的准备，供 `/agent/query/stream`、`/regenerate` 用。
- `session_query_service`：非 Agent 查询类，供 `/rag/query`、`/session/*`、`/reorder` 用。
- 二者互不 import，职责不重叠。

### 步骤 1：ChatService 改名

- `chat_service.py` 的 `ChatService` → `app/services/session_query_service.py` 的 `SessionQueryService`，`get_router_service` 一并迁移。
- `chat_service.py` 留 shim：`from app.services.session_query_service import SessionQueryService as ChatService, get_router_service`。
- 删 `handle_agent_query`（已在 P0.1 步骤 0 处理）与对 `get_agent_response` 的 import。

### 步骤 2：抽 `prepare_agent_run`

`query_stream`（chat.py L106–L139）与 `regenerate`（L240–L270）逐段重复，收敛成单一方法：

```python
@dataclass
class AgentRunPlan:
    model_config: UserModelConfig | None
    system_prompt: str
    tools: list[BaseTool]
    notices: list[str]

async def prepare_agent_run(
    db, user_id, *, query, model_config_id, prompt_type, skill_ids, tool_ids,
) -> AgentRunPlan:
    # 1 model_config 解析（404）
    # 2 prompt_type 校验（400）
    # 3 候选 skill = skill_ids or default_skill_ids()
    # 4 tool_ids 显式→跳过路由；否则 route_skills(query, 候选)
    # 5 mcp ensure_fresh → reload
    # 6 resolve_skills（400）
    # 7 build_chat_system_prompt(...)
```

- `build_chat_system_prompt` + `CHAT_PROMPT_MODES`（chat.py L40–L82）移入 `agent_run_service`。
- regenerate 的 query 来自 `get_regenerate_payload`，由路由层先取好再传入，保持方法单一。
- `SSE_HEADERS` 常量去重（现 3 处重复字典）。

### 步骤 3：路由瘦身

路由只保留参数接收、依赖注入、异常透传、响应返回；编排移入 service。

### 验收与测试

- 新增 `backend/tests/test_agent_run_service.py`：mock `route_skills` / `resolve_skills` / `mcp_tool_registry`，断言 tool_ids 显式时跳过路由、prompt_type 非法抛 400、model_config 不存在抛 404、notices 透传。
- 回归：query 与 regenerate 复用同一 `prepare_agent_run`，断言两者 plan 一致。
- 对齐 roadmap：chat.py 仅留参数 / DI / 异常 / 响应；模型选择 / Skill 路由 / 工具解析 / prompt 构建在服务层；regenerate 与 confirm 不再复制主查询流程。

---

## P0.3 前端 Chat 功能域拆分

`AIChat.tsx`（1031 行，≈21 个 useState，SSE 解析散落在 `handleSend` / `handleConfirmAction` / `handleRegenerateMessage`）。

### 目标结构与迁移映射

```text
front/src/features/chat/
  types.ts                       # Message / ContextSettings / RagRetrievalSettings / PendingConfirmation 等
  storage.ts                     # CHAT_*_STORAGE_KEY + 读写封装（现 L24–L127）
  hooks/useChatStream.ts         # 【最高价值】统一 SSE 消费：fetch+ReadableStream 解析、事件分发、rafRef flush
  hooks/useChatSettings.ts       # model/prompt/skill/context/rag 选择 + localStorage（现 L197–L295 多个 useEffect）
  hooks/useSkillCatalog.ts       # skills/tools/toolsById 加载 + skillCatalogLoaded/Error
  components/ChatMessageList.tsx
  components/ChatComposer.tsx     # 输入框 + quickQuestions
  components/ChatToolPanel.tsx
  components/PendingConfirmationBar.tsx
  components/ThinkingPanel.tsx    # currentThinking/Steps/StepDetails + showThinking
```

### 关键：`useChatStream` 抽象

三处共用的 SSE 解析（`data:` 分包、JSON parse、按 `type` 分发、`contentRef`+`rafRef` 节流、regenerate 用 `regeneratingMessageIdRef` 覆盖）收敛为：

```ts
const { send, stop, streaming } = useChatStream({
  onResponseDelta, onThinking, onPending, onDone, onError,
})
// send({ url, body, targetMessageId? })  // regenerate 传 targetMessageId 走覆盖逻辑
```

`handleSend` / `handleRegenerateMessage` / `handleConfirmAction` 退化为构造 body + 提供回调。`formatThinkingDetail`（L60）移入 hook 或 ThinkingPanel。

### 迁移顺序（独立于后端）

1. 抽 `types.ts` + `storage.ts`（纯移动）。
2. 抽 `useChatStream`，先只接管 `handleSend`，跑通后再接管 regenerate / confirm（逐个切，最易回归点）。
3. 抽 `useChatSettings` / `useSkillCatalog`。
4. 拆 presentational 组件，`AIChat.tsx` 只做组合。

### 验收与测试

- `useChatStream` 用 mock `ReadableStream` 单测：分包跨 chunk、各事件分发、regenerate 覆盖目标消息。
- 本环境无 node，**typecheck/test 由用户在 `front/` 跑 `npm run build` / `npm test`**，每步留可回滚。
- 对齐 roadmap：AIChat.tsx 只做页面级组合；SSE 消费 / 设置持久化 / Skill catalog / 消息渲染可分别测；工具面板与上下文策略不再直接耦合消息流。

---

## P0.4 RAG 与知识库边界整理

结合度低于 P0.1/0.2，放最后；本阶段只明确边界，不重写算法。

- `knowledge_service`：仅文档导入 / 源文件 / 任务状态。
- `vector_store`：仅 Chroma 索引读写 + retriever 构造。
- `rag_service`：仅查询期召回 / 重排 / 上下文生成。
- 解析 / 多模态 PDF / 图片抽取留独立工具模块。
- 验收：上传与对话 RAG 可分别测；换 embedding/reranker 不触 Chat/Agent 主链路；任务失败返回结构化错误（与 P1.3 事件字段对齐，预留接口位）。

---

## 总执行顺序与里程碑

| 序 | 范围 | 可独立合入 | 风险 |
|---|---|---|---|
| 1 | P0.1 步 0：删死代码 + 抽常量 | ✅ | 低 |
| 2 | P0.1 步 1：sse_driver 去重（含统一 session_id 修正） | ✅ | 中（行为收敛，回归 stop/timeout） |
| 3 | P0.1 步 2–4：factory 注入 + context_builder + streaming + shim + 单测 | ✅ | 中 |
| 4 | P0.2：ChatService 改名 + prepare_agent_run + 路由瘦身 + 单测 | ✅ | 中 |
| 5 | P0.3 前端：types/storage → useChatStream → 其余 hooks → 组件 | 分步 ✅ | 中（SSE 回归） |
| 6 | P0.4 RAG 边界 | ✅ | 低 |

建议从里程碑 1 起按序推进；每个里程碑独立提交，便于回滚与 review。
