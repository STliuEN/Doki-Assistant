# 下一阶段开发计划

本文记录当前 `master` 的真实状态，以及后续继续推进的优先级。项目已经从基础 RAG 服务演进为个人 Agent 平台：FastAPI 后端、React 前端、Django 用户服务、MySQL 会话与业务数据、Redis 缓存、Chroma 向量库、LangChain tool calling Agent、Skill/Tool 文件注册、知识库 RAG、笔记、记忆中心、实时翻译和用户模型配置已经接在一起。

下一阶段重点不是继续堆页面，而是把 Agent 运行时、权限边界、高风险操作确认和长期上下文闭环做稳。

## 当前已完成

### 平台底座

- **登录鉴权**：前端 HTTP 与 SSE 都会携带 JWT，后端主链路通过 `get_current_user_id` 获取当前用户。
- **用户数据隔离**：聊天、知识库、笔记、记忆中心、模型配置等主链路按 `user_id` 查询。
- **Agent 对话**：`/chat/agent/query/stream` 使用 SSE；后端基于 LangChain `create_tool_calling_agent` + `AgentExecutor`。
- **Prompt 拼接**：后端按 `main_prompt`、当前 AI 模式 prompt、已启用 Skill 指令、可用工具列表组合系统提示词。
- **Skill/Tool 注册**：扫描 `backend/app/agent/skills/*` 和 `backend/app/agent/tools/*`，前端可以管理和勾选。
- **Skill 预路由**：后端会在用户已选 Skill 范围内，用规则和 LLM 兜底挑出本轮相关 Skill。
- **RAG 检索策略**：前端提供 Auto/低/中/高/自定义；后端动态控制知识库召回数、笔记召回数和摘要文档数。
- **消息级操作**：同一条 assistant 回答支持刷新覆盖，消息删除会同步后端删除。
- **记忆中心**：已有 `review/todo/reminder/long_term/memo` 统一模型、页面、API 和 Agent tools。
- **知识库**：支持 TXT/PDF/MD/PPTX/DOCX，源文件保存、切片、Embedding 切换、Reranker 切换。
- **模型配置**：支持工程默认模型、用户 OpenAI-compatible 模型和 Ollama 本地模型。

### P0.1 后端权限边界

已完成：

- `skill_router.py`、`tool_router.py` 读取接口要求登录。
- Skill/Tool 创建、更新、删除要求管理员权限。
- 管理员名单维护在 `backend/app/config/security.yaml`。
- `ADMIN_USER_IDS` / `ADMIN_USERNAMES` 可追加部署环境管理员。
- `/chat/sessions` 只返回当前用户会话。
- `/chat/sessions/{user_id}` 继续校验当前用户，禁止越权枚举。
- `/chat/reorder` 增加登录鉴权并保留限流。
- README 已说明当前不是完整多租户 RBAC。

当前边界：

- 已有“登录用户 / 管理员”的基础分层。
- 尚未提供数据库角色、团队租户、细粒度操作权限和审计后台。

### P0.2 Tool 风险元数据与删除阻断

已完成：

- `ToolDefinition` 支持：
  - `risk_level`
  - `requires_confirmation`
  - `timeout_seconds`
  - `max_output_chars`
- Tool 管理接口和前端工具库页面支持查看、编辑这些字段。
- `delete_memory` 已标记为：
  - `risk_level: high`
  - `requires_confirmation: true`
- `delete_memory_tool` 当前不会直接删除，而是推送 `waiting_confirmation` 事件并返回未执行说明。

当前边界：

- 高风险删除已经被“刹住”，不会被 Agent 静默执行。
- 还没有实现“确认后继续执行”的完整续跑协议。

### P0.3 执行过程事件化

已完成：

- Agent SSE thinking 事件开始带结构化 `details`。
- 每轮运行生成 `run_id`。
- 事件包含 `elapsed_ms`。
- 普通工具调用通过 `intermediate_steps` 转成 `tool_end` 事件。
- 工具事件包含：
  - `tool`
  - `tool_call_index`
  - `input_preview`
  - `output_preview`
- 前端 AIChat thinking 区兼容 `waiting_confirmation` 和结构化 details。

当前边界：

- 目前普通工具还主要在 LangChain 返回 `intermediate_steps` 后产生 `tool_end`，不是严格的 tool_start/tool_end 包装。
- 部分工具内部主动上报的事件仍需逐步统一字段。

### P0.4 长任务预算、停止和收束

已完成：

- 新增 `backend/app/config/agent.yaml`：

```yaml
runtime:
  max_iterations: 64
  max_tool_calls: 32
  max_runtime_seconds: 180
  max_output_chars_per_tool: 8000
```

- `AgentExecutor.max_iterations` 读取配置。
- SSE 外层支持 wall-clock 超时取消。
- 工具调用次数超过预算时会发 `stopped` 事件并收束。
- 停止回答会附带 `stop_reason`。
- 前端已有 AbortController，可停止当前 SSE 请求。

当前边界：

- 工具次数预算基于 `intermediate_steps` 统计，不能在工具真正执行前硬拦截所有工具。
- 后续若要强控制，应给 Tool 做统一 wrapper 或迁移到更细粒度的运行图。

### P1 上下文自动压缩

已完成：

- 复用 `ChatSession.metadata_` 保存摘要相关字段：
  - `summary`
  - `summary_message_id`
  - `summary_updated_at`
  - `estimated_tokens`
- Auto 模式下，长会话会尝试压缩早期消息。
- 保留最近 6 轮原文。
- Prompt 结构变为：

```text
system prompt
  -> conversation_summary
  -> recent_messages
  -> current_user_input
  -> agent_scratchpad
```

- 摘要失败会回退到原有裁剪逻辑。
- regenerate 流程会读取已有摘要并保留最近 6 轮。

当前边界：

- 摘要触发阈值仍是简单 token 粗估。
- `summary_message_id` 目前预留，尚未精确记录摘要覆盖到哪条消息。
- 摘要生成复用当前聊天模型，后续可拆成专门的轻量模型配置。

## 当前主要剩余缺口

### 高风险确认闭环

需要继续完成：

- SSE 发出 `waiting_confirmation` 后，前端展示确认/拒绝控件。
- 后端保存 pending action。
- 用户确认后执行原工具。
- 用户拒绝后 Agent 可以继续解释或给替代方案。
- pending action 需要过期、用户隔离和重复提交保护。

### 工具执行 wrapper

需要继续完成：

- 在 Tool Registry 层统一包装工具执行。
- 产生真正的 `tool_start/tool_end/tool_error`。
- 按工具元数据执行：
  - timeout
  - max output chars
  - risk confirmation
  - structured error
- 将 RAG、笔记、记忆、复习题生成等内部事件字段统一。

### 权限模型升级

需要继续完成：

- 将当前配置文件管理员升级为数据库角色或权限表。
- 支持用户状态、管理员、未来团队/租户角色。
- 管理操作写审计日志。

### 上下文摘要增强

需要继续完成：

- 精确维护 `summary_message_id`。
- 避免重复摘要同一段历史。
- 摘要质量评估和回滚。
- 为摘要使用独立模型或配置。

## 后续路线

### P2：记忆中心闭环

目标：

- 从对话、笔记、翻译结果中提炼待办/提醒/长期事项。
- 提炼结果先让用户确认，不自动写入。
- 增加到期提醒扫描，先做页面内提醒，再预留桌面通知。
- 增加 memory 语义搜索和来源关联。

验收：

- 用户完成一次对话后，可以看到可保存的事项建议。
- 今日到期事项能主动显示。
- 事项完成、延期、归档后状态正确。

### P3：Skill/Tool 体系收敛

目标：

- Skill 预路由结果可解释。
- Tool 元数据可测试、可诊断、可限流。
- 管理页不只编辑文本，还能看到风险、默认启用、绑定关系和测试结果。

验收：

- 前端能显示“本轮为什么启用了这些 Skill”。
- 新增 Tool 前可运行 smoke test。
- Tool 返回结构化错误：参数错误、权限错误、外部服务错误、内部异常。

### P4：MCP 外部工具接入

MCP 必须排在高风险确认闭环之后。当前项目已有本地 Skill/Tool 注册层，MCP 应作为外部工具来源接入，而不是替代 Skill。

阶段：

1. 配置 MCP server，发现 tools。
2. MCP tool 适配为内部 `ToolDefinition`。
3. Skill 可以绑定 MCP tool。
4. Agent 可以调用 MCP tool。
5. 启用工具权限、超时、最大输出和高风险确认。

验收：

- 本地工具链路不受影响。
- MCP 工具可选择、可禁用、可观察。
- 文件系统、Shell、数据库类工具默认关闭。

### P5：实时翻译升级

目标：

- 从手动输入翻译升级到连续文本流/字幕流。
- 翻译结束后生成笔记、摘要、术语表和待办建议。

优先顺序：

1. 剪贴板或文本流输入。
2. OCR/字幕文本源调研。
3. 系统字幕或会议字幕接入。
4. 保存为笔记并提炼 memory。

### P6：桌面端验证

短期继续 Web 架构。桌面端只做可行性验证：

- 一键启动后端、前端、用户服务和依赖。
- 本地 Ollama、Chroma、MySQL/Redis 是否能简化。
- 系统通知、本地文件、字幕文本源是否可行。

## 暂不优先

- 团队协作和复杂多租户后台。
- 完整迁移 LangGraph。
- 复杂工作流编排器。
- 默认开放 Shell、浏览器、文件系统等高风险外部工具。

## 推荐实施顺序

1. 高风险确认续跑闭环。
2. Tool 统一 wrapper、真正 tool_start/tool_end/tool_error。
3. 权限模型从配置文件升级到数据库角色。
4. 上下文摘要 message 边界和重复摘要控制。
5. 记忆中心主动提醒和事项提炼。
6. Tool 元数据、测试和诊断。
7. MCP 接入。
8. 字幕/会议翻译。
9. 桌面端验证。
