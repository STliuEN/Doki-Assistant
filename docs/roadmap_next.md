# 下一阶段开发计划

本文只记录接下来要做的工作，不维护历史状态清单。当前代码具备个人 Agent 工作台的主要功能：React 前端、Django 用户服务、FastAPI 业务后端、Agent 对话、Skill/Tool、MCP 接入、RAG、笔记、记忆中心、实时翻译和用户模型配置。后续重点从“继续加能力”转向“降低耦合、稳定边界、补齐治理和测试”。

## 路线原则

- 优先减少核心编排文件的职责混杂，再继续扩功能。
- 保持现有 API 和用户工作流兼容，重构必须可渐进落地。
- 后端先稳住 Agent/Chat/RAG/Tool 边界，前端再按功能域拆分页面。
- 所有涉及删除、外部工具、文件系统、Shell、数据库写入的能力默认保守。
- 新增平台级能力必须有最小测试或可诊断入口。

## P0 架构解耦与可维护性

### P0.1 Agent 运行时拆分

当前 `backend/app/agent/agent.py` 同时承担 Agent 工厂、模型创建、上下文组装、摘要、SSE 编排、工具事件、消息落库和 regenerate。下一步要把它拆成职责清晰的模块。

目标结构：

```text
backend/app/agent/
  factory.py          # AgentFactory、模型创建、默认工具装配
  prompt_builder.py   # system prompt、Skill prompt、可用工具提示
  context_builder.py  # 历史、摘要、上下文窗口、regenerate 上下文
  runtime.py          # 运行预算、run state、thinking/tool event
  streaming.py        # query/regenerate/confirm 的 SSE 编排
```

验收：

- `agent.py` 不再是主运行时大文件；保留兼容导出或迁移到小入口。
- 普通聊天、工具调用、RAG 工具、消息刷新、高风险确认和停止请求行为保持兼容。
- 运行预算、工具事件和上下文摘要有独立单元测试。

### P0.2 Chat 路由瘦身

当前 `backend/app/router/chat.py` 同时处理 HTTP 入参、模型配置、Skill 预路由、MCP refresh、prompt 拼接、Agent 调用和 SSE 返回。需要把业务编排移到服务层。

目标结构：

```text
backend/app/router/chat.py              # 薄路由
backend/app/services/agent_chat_service.py
backend/app/services/chat_settings_service.py
```

验收：

- `chat.py` 只保留参数接收、依赖注入、异常转换和响应返回。
- 模型选择、Skill 路由、工具解析、prompt 构建由服务层完成。
- regenerate 和 confirm 复用同一套编排逻辑，不再复制主查询流程。

### P0.3 前端 Chat 功能域拆分

当前 `front/src/pages/AIChat.tsx` 集中承担 SSE 消费、消息状态、模型和 prompt 设置、Skill catalog、上下文策略、工具面板、确认动作和渲染。需要拆成 feature 结构。

目标结构：

```text
front/src/features/chat/
  hooks/useChatStream.ts
  hooks/useChatSettings.ts
  hooks/useSkillCatalog.ts
  components/ChatMessageList.tsx
  components/ChatComposer.tsx
  components/ChatToolPanel.tsx
  components/PendingConfirmationBar.tsx
  types.ts
```

验收：

- `AIChat.tsx` 只做页面级组合。
- SSE 消费、设置持久化、Skill catalog 加载和消息渲染可以分别测试。
- 工具面板和上下文策略 UI 不再直接耦合消息流逻辑。

### P0.4 RAG 与知识库边界整理

当前知识库相关逻辑分布在 `knowledge_router.py`、`knowledge_service.py`、`vector_store.py`、`rag_service.py` 和文档处理模块中，文件体量偏大。需要明确上传入库、向量索引、检索、重排、RAG 生成的边界。

目标：

- `knowledge_service` 聚焦文档导入、源文件和任务状态。
- `vector_store` 聚焦 Chroma 索引读写和 retriever 构造。
- `rag_service` 聚焦查询时召回、重排和上下文生成。
- 文档解析、多模态 PDF、图片抽取继续留在独立工具模块。

验收：

- 文档上传和对话 RAG 查询可以分别测试。
- 更换 embedding/reranker 不需要改 Chat 或 Agent 主链路。
- 知识库任务失败时能返回结构化错误和可诊断日志。

## P1 权限、治理和安全边界

### P1.1 数据库角色权限

当前管理员主要来自配置文件和环境变量。下一步要升级到数据库角色或权限表。

目标：

- 用户具有 `user/admin` 基础角色。
- 管理操作通过数据库角色判断。
- 保留配置文件管理员作为本地开发和紧急兜底。
- Skill/Tool/MCP 管理操作写审计日志。

验收：

- 前端可以区分普通用户和管理员能力。
- 管理员变更不需要重启服务。
- 审计日志能记录操作者、操作对象、动作、时间和结果。

### P1.2 Tool 和 MCP 风险治理

当前本地 Tool 已有风险元数据，MCP 工具也能进入统一工具库。后续重点是管理、测试、持久化和审计。

目标：

- MCP server 和 MCP tool 的启用状态、风险等级、确认要求、超时、输出限制可持久化。
- ToolManager 支持 refresh、test、last_error、只读标签和高风险标签。
- 文件系统、Shell、数据库写入、外部发送类 MCP server 默认关闭。
- 高风险确认后的直接执行路径仍走统一超时、截断和审计。

验收：

- 管理员能在页面或 API 侧刷新、测试、禁用 MCP 工具。
- MCP server 离线不影响普通聊天。
- 高风险 MCP 工具不会被静默执行。

### P1.3 结构化错误和事件字段统一

当前 SSE thinking 已经有结构化 `details`，但工具内部事件和错误分类仍不统一。

目标：

- 定义统一事件字段：`run_id`、`stage`、`tool`、`duration_ms`、`input_preview`、`output_preview`、`error_type`。
- 工具错误至少区分：参数错误、权限错误、外部服务错误、内部异常、超时、用户取消。
- RAG、笔记、记忆、MCP 工具统一使用同一套事件协议。

验收：

- 前端 thinking 区可以稳定展示不同工具的事件。
- 日志和 SSE 中的错误分类一致。
- 关键工具有错误分类测试。

## P2 上下文和记忆闭环

### P2.1 上下文摘要增强

当前 Auto 上下文已经支持摘要加最近窗口，但摘要边界和质量控制还需要加强。

目标：

- 精确记录摘要覆盖的消息边界，避免重复摘要或遗漏。
- 摘要失败、摘要质量过低时可回滚到裁剪上下文。
- 摘要模型可以独立配置，避免占用主聊天模型。
- regenerate 使用相同的上下文策略，不产生边界偏移。

验收：

- 长会话连续多轮后不会重复摘要同一段历史。
- 删除或刷新消息后摘要边界仍可解释。
- 摘要策略有单元测试覆盖。

### P2.2 主动记忆提炼

记忆中心已经支持事项管理，下一步要从对话、笔记和翻译结果中提炼候选事项，但必须由用户确认。

目标：

- 对话结束后生成待办、提醒、长期事项或复习建议。
- 候选事项先展示给用户确认，不自动写入。
- 保存事项时记录来源会话、消息或笔记。
- 今日到期事项在页面内主动提示。

验收：

- 用户完成一次对话后能看到可保存的事项建议。
- 保存、忽略、延期、完成后的状态正确。
- Agent 查询记忆时能看到来源和状态。

### P2.3 Memory 语义搜索

目标：

- 记忆中心支持关键词和语义混合搜索。
- Agent 工具可按类型、状态、到期时间和语义 query 查询。
- 与笔记、知识库的召回结果保持来源区分。

验收：

- `review/todo/reminder/long_term/memo` 都可被准确过滤。
- 语义搜索不会跨用户泄露。
- 搜索结果包含来源、状态和更新时间。

## P3 Skill/Tool 开发体验

### P3.1 Skill 预路由可解释

目标：

- 前端展示本轮启用 Skill 的原因：用户选择、always_on、关键词、语义命中或 LLM 仲裁。
- 后端返回可诊断的路由摘要。
- 路由失败时明确降级原因。

验收：

- 用户能看到“为什么这轮用了这些 Skill”。
- 新增 Skill 后可以用样例验证路由效果。
- 预路由测试覆盖正例、负例和噪声 query。

### P3.2 Tool smoke test

目标：

- 本地 Tool 新增或编辑后可以运行 smoke test。
- MCP Tool 可以测试连接、schema 和一次只读调用。
- 测试结果进入管理页和日志。

验收：

- 管理页能显示最近一次测试状态。
- 失败结果包含错误类型和建议检查项。
- 高风险工具测试默认不执行真实写操作。

## P4 翻译、桌面端和外部输入

### P4.1 实时翻译升级

目标：

- 从手动输入扩展到连续文本流或字幕流。
- 翻译结束后可生成笔记、摘要、术语表和候选记忆事项。
- 支持对翻译结果做后续 Agent 问答。

验收：

- 连续文本流不会阻塞 UI。
- 翻译记录可保存为笔记。
- 术语表和事项提炼需要用户确认。

### P4.2 桌面端可行性验证

短期继续 Web 架构，桌面端只做验证。

目标：

- 一键启动前端、FastAPI、Django 和依赖。
- 验证本地 Ollama、Chroma、MySQL/Redis 的简化方案。
- 验证系统通知、本地文件和字幕文本源。

验收：

- Windows 本地能稳定一键启动。
- 依赖缺失时有明确诊断。
- 不默认开放高风险本地能力。

## 暂不优先

- 团队协作和复杂多租户后台。
- 完整迁移 LangGraph。
- 复杂工作流编排器。
- 默认开放 Shell、浏览器、文件系统等高风险外部工具。
- 大规模重写 UI 视觉体系。

## 推荐实施顺序

1. Agent 运行时拆分。
2. Chat 路由瘦身。
3. 前端 Chat 功能域拆分。
4. RAG 与知识库边界整理。
5. 数据库角色权限和审计。
6. MCP/Tool 风险治理与测试。
7. 事件字段统一和结构化错误。
8. 上下文摘要增强。
9. 主动记忆提炼和 Memory 语义搜索。
10. Skill 路由解释和 Tool smoke test。
11. 实时翻译升级。
12. 桌面端验证。
