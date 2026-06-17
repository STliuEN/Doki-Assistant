# 下一阶段开发计划

本文按当前工程实际状态重写。当前 `master` 已经是个人 Agent 平台雏形：FastAPI 后端、React 前端、Django 用户服务、MySQL 会话与业务数据、Redis 缓存、Chroma 向量库、LangChain tool calling Agent、Skill/Tool 文件注册、知识库 RAG、笔记、记忆中心、实时翻译和用户模型配置已经接在一起。

下一阶段的重点不是继续堆页面，而是把 Agent 运行时、权限边界和已有功能闭环做稳。

## 当前状态

### 已具备

- **登录鉴权**：前端 HTTP 与 SSE 都会携带 JWT，后端多数业务路由通过 `get_current_user_id` 获取当前用户。
- **用户数据隔离**：聊天、知识库、笔记、记忆中心、模型配置等主链路基本按 `user_id` 查询。
- **Agent 对话**：`/chat/agent/query/stream` 使用 SSE；后端基于 LangChain `create_tool_calling_agent` + `AgentExecutor`。
- **Prompt 拼接**：后端按 `main_prompt`、当前 AI 模式 prompt、已启用 Skill 指令、可用工具列表组合系统提示词。
- **Skill/Tool 注册**：扫描 `backend/app/agent/skills/*` 和 `backend/app/agent/tools/*`，前端可以管理和勾选。
- **Skill 预路由**：后端会在用户已选 Skill 范围内，用规则和 LLM 兜底挑出本轮相关 Skill。
- **上下文策略**：前端提供 `策略` 菜单，支持 Auto/低/中/高/自定义/仅当前；后端按 token 粗估或轮数裁剪历史。
- **RAG 检索策略**：前端提供 Auto/低/中/高/自定义；后端动态控制知识库召回数、笔记召回数和摘要文档数。
- **消息级操作**：同一条 assistant 回答支持刷新覆盖，消息删除会同步后端删除。
- **记忆中心**：已有 `review/todo/reminder/long_term/memo` 统一模型、页面、API 和 Agent tools。
- **知识库**：支持 TXT/PDF/MD/PPTX/DOCX，源文件保存、切片、Embedding 切换、Reranker 切换。
- **模型配置**：支持工程默认模型、用户 OpenAI-compatible 模型和 Ollama 本地模型。

### 主要不足

- **权限不完整**：有登录鉴权和用户隔离，但没有角色、管理员、操作级权限。
- **管理接口风险**：`/skills`、`/tools` 管理接口目前缺少后端鉴权；`/chat/sessions`、`/chat/reorder` 也需要补齐访问控制。
- **高风险工具缺确认**：Agent 写入、删除类工具没有统一风险等级和二次确认。
- **运行时可观察性不足**：thinking 区能显示部分过程，但不是结构化事件列表；普通工具调用没有完整 `tool_start/tool_end/duration`。
- **最终回答不是真正 token 流**：当前是 Agent 执行结束后再按 chunk 推送最终回答。
- **上下文还只是裁剪**：已有 token 估算和轮数裁剪，但没有“长期摘要 + 最近窗口”的自动压缩。
- **长任务缺预算**：`max_iterations=64`，但缺少 wall-clock 超时、工具次数预算、停止原因和恢复机制。

## P0：安全边界和运行时稳定

P0 是所有外部工具、MCP、桌面端和长期自动任务的前置条件。

### P0.1 补齐后端权限

目标：

- 所有业务和管理接口都必须显式声明鉴权策略。
- 用户数据只能访问当前用户数据。
- Skill/Tool 管理接口至少要求登录；后续可升级为管理员或本地开发模式开关。

改动清单：

- 给 `skill_router.py`、`tool_router.py` 增加 `Depends(get_current_user_id)`。
- 给 `/chat/sessions` 增加鉴权，并改成只返回当前用户会话，或仅保留 `/chat/sessions/{user_id}`。
- 给 `/chat/reorder` 增加鉴权和限流。
- 梳理所有 router，形成“公开接口 / 登录接口 / 管理接口”清单。
- 在 README 明确当前不是多租户权限系统。

验收：

- 未登录无法创建、更新、删除 Skill/Tool。
- 未登录无法调用会消耗模型资源的接口。
- 用户不能枚举其他用户会话。

### P0.2 Tool 风险等级与确认

目标：

- Tool 元数据增加风险和权限字段。
- 删除、清空、外部写入、未来 Shell/文件系统/数据库工具必须先确认。

建议字段：

```yaml
risk_level: low | medium | high
requires_confirmation: true | false
timeout_seconds: 30
max_output_chars: 4000
```

第一批高风险工具：

- `delete_memory`
- 未来的批量删除、清空知识库、MCP 文件系统、Shell、数据库写入工具

验收：

- Agent 请求高风险操作时进入 `waiting_confirmation`。
- 前端展示操作摘要，用户确认后才继续。
- 用户拒绝后 Agent 可以继续解释或给替代方案。

### P0.3 执行过程事件化

目标：

- 将 thinking 从“文本列表”升级为结构化事件。
- 每次工具调用都有开始、结束、耗时、输入摘要、输出摘要、错误。

事件建议：

```json
{
  "type": "thinking",
  "stage": "tool_end",
  "content": "search_notes_tool 执行完成",
  "details": {
    "run_id": "uuid",
    "tool": "search_notes_tool",
    "duration_ms": 820,
    "input_preview": "...",
    "output_preview": "..."
  }
}
```

验收：

- 前端 thinking 折叠区能看到工具列表、状态和耗时。
- 工具失败时能看到失败步骤。
- RAG、笔记检索、记忆查询、复习题生成都有一致显示。

### P0.4 长任务预算、停止和收束

目标：

- 防止 Agent 长时间失控。
- 用户能看到运行时长和停止原因。

建议预算：

```text
max_iterations: 64
max_tool_calls: 32
max_runtime_seconds: 180
max_output_chars_per_tool: 8000
```

验收：

- 达到预算时生成收束回答。
- 前端可停止当前 SSE 请求。
- 停止后展示已完成步骤和未完成部分。

## P1：上下文自动压缩

当前已有上下文裁剪，但还没有自动摘要。下一步改成：

```text
system prompt
  -> conversation_summary
  -> recent_messages
  -> current_user_input
  -> agent_scratchpad
```

改动清单：

- 在 `ChatSession.metadata_` 保存 `summary`、`summary_message_id`、`summary_updated_at`、`estimated_tokens`。
- 超过阈值后压缩早期消息，保留最近 6 轮原文。
- 前端 `策略` 菜单保留当前裁剪选项，后端在 Auto 下优先使用摘要策略。
- 摘要失败时回退当前裁剪逻辑。

验收：

- 长会话不会无限增长 prompt。
- 摘要保留目标、偏好、未完成事项和重要约束。
- 知识库、笔记、记忆事实仍通过工具实时查询，不靠摘要硬答。

## P2：记忆中心闭环

当前记忆中心已经能增删改查，但还缺“主动性”。

目标：

- 从对话、笔记、翻译结果中提炼待办/提醒/长期事项。
- 提炼结果先让用户确认，不自动写入。
- 增加到期提醒扫描，先做页面内提醒，再预留桌面通知。
- 增加 memory 语义搜索和来源关联。

验收：

- 用户完成一次对话后，可以看到可保存的事项建议。
- 今日到期事项能主动显示。
- 事项完成、延期、归档后状态正确。

## P3：Skill/Tool 体系收敛

目标：

- Skill 预路由结果可解释。
- Tool 元数据可测试、可诊断、可限流。
- 管理页不只编辑文本，还能看到风险、默认启用、绑定关系和测试结果。

验收：

- 前端能显示“本轮为什么启用了这些 Skill”。
- 新增 Tool 前可运行 smoke test。
- Tool 返回结构化错误：参数错误、权限错误、外部服务错误、内部异常。

## P4：MCP 外部工具接入

MCP 必须排在 P0 之后。当前项目已有本地 Skill/Tool 注册层，MCP 应作为外部工具来源接入，而不是替代 Skill。

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

## P5：实时翻译升级

目标：

- 从手动输入翻译升级到连续文本流/字幕流。
- 翻译结束后生成笔记、摘要、术语表和待办建议。

优先顺序：

1. 剪贴板或文本流输入。
2. OCR/字幕文本源调研。
3. 系统字幕或会议字幕接入。
4. 保存为笔记并提炼 memory。

## P6：桌面端验证

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

1. 补齐权限和高风险确认。
2. 执行过程事件化和计时。
3. 长任务预算与停止。
4. 上下文自动压缩。
5. 记忆中心主动提醒和事项提炼。
6. Tool 元数据、测试和诊断。
7. MCP 接入。
8. 字幕/会议翻译。
9. 桌面端验证。

