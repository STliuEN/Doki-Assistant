# 下一阶段路线图

本文只维护尚未完成的工作。已经完成的设计和实施过程保留在 `project_changes/`，不会继续作为待办重复出现。

依赖生成物、OpenAPI、安全配置、前端 lint 和 CI 的专项实施步骤见 [仓库更新完整性整改计划](./maintenance_update_plan.md)。

## 已完成基线

以下能力是当前架构，不再列入后续计划：

- Agent 运行时已从旧 `agent.py` 拆分为 factory、context builder、streaming 和 runtime 子模块。
- Query 与 regenerate 共用 `prepare_agent_run` 和 SSE driver。
- Tool 调用次数、确认、超时和输出截断统一进入 GuardedTool。
- 高风险 pending action 使用 Redis、TTL、用户隔离和一次性消费。
- 前端 SSE 消费已拆入 `features/chat/useChatStream` 并有 Vitest 合同测试。
- MCP server/tool 已支持 catalog、refresh、配置更新、禁用和删除，并写回 `mcp.yaml`。
- 本地 smoke benchmark 已覆盖 Agent 流、工具安全、SSE 合同和 scorer。

## 优先级原则

- P0 处理数据、安全和无法可靠运维的问题。
- P1 处理核心运行时正确性、治理和可测试性。
- P2 完成产品闭环和主要前端维护性工作。
- P3 扩展覆盖面或验证远期方向。
- 新功能不得绕过 JWT 用户隔离、GuardedTool 或已有 SSE 合同。

## P0 数据与安全基线

### P0.1 正式数据库 migration

现状：FastAPI 启动时使用 `create_all` 和自定义补列逻辑，没有版本化 migration。

目标：

- 引入 Alembic 或等价的版本化 migration。
- 为现有业务表生成可审阅的 baseline。
- 停止在启动阶段隐式修改复杂 schema。
- 提供升级、回滚和备份说明。

验收：

- 空数据库和已有数据库都能通过同一 migration 序列升级。
- migration 可在不启动模型、Redis 或 MCP 的环境执行。
- CI 能验证 migration 可应用到临时数据库。

### P0.2 生产配置边界

现状：Django `DEBUG=True`、服务端 CORS 宽松，仓库没有生产部署配置。

目标：

- 使用环境变量控制 DEBUG、ALLOWED_HOSTS 和 CORS origins。
- 移除示例中的弱 secret，启动时拒绝空或默认 JWT secret。
- 定义反向代理、TLS、静态文件、进程守护和日志轮转方案。
- 明确 MySQL、Redis、上传文件和 Chroma 的备份恢复方式。

验收：

- production profile 不允许任意 origin。
- 缺少必需 secret 时启动失败并给出明确错误。
- 文档中存在可重复的最小部署与回滚流程。

### P0.3 认证合同收敛

现状：Django API 文档与部分视图的认证要求曾发生漂移，用户服务和 FastAPI 分别处理 token 黑名单。

目标：

- 为所有用户接口显式声明 authentication 和 permission。
- 修正注销等接口的未认证行为。
- 统一 token 过期、刷新、注销和黑名单合同。
- 增加跨 Django/FastAPI 的认证集成测试。

验收：

- 受保护接口对无 token、无效 token、过期 token 和黑名单 token 返回一致状态。
- 注销后两个服务都拒绝旧 token。
- OpenAPI 与实现的认证标记一致。

## P1 Agent 正确性与可观测性

### P1.1 摘要覆盖边界

目标：

- 持久化摘要覆盖到的最后消息 ID，而不只依赖轮数推断。
- 删除、重新生成和插入消息后正确失效或重算摘要。
- 摘要失败时可靠回退到 token 裁剪。
- 支持独立摘要模型配置。

验收：

- 长会话多次摘要不会重复或遗漏消息。
- regenerate 不把被替换回答放入上下文。
- 边界变化有独立单元测试。

### P1.2 统一事件和错误分类

目标：

- 稳定定义 `run_id/stage/tool/duration_ms/error_type` 等字段。
- 区分参数、认证、权限、外部服务、超时、取消和内部异常。
- 让日志、SSE、Benchmark 和前端使用同一分类。
- 为事件 schema 添加自动校验。

验收：

- 本地 Tool、MCP Tool 和 RAG 错误可以统一展示和筛选。
- 未知字段或缺失必需字段能在测试阶段失败。

### P1.3 运行记录与取消

目标：

- 持久化 run 开始、结束、停止原因、模型、Skill、Tool 和耗时摘要。
- 客户端断开时取消 Agent 和外部工具任务。
- 区分用户取消、运行预算超时和服务异常。
- 为长任务保留可诊断但经过截断的事件记录。

验收：

- 断开客户端不会留下持续运行的后台 Agent task。
- 管理员能根据 run ID 关联日志、工具调用和最终消息。

## P1 权限与 MCP 治理

### P1.4 数据库角色和审计

目标：

- 使用数据库角色替代 YAML 管理员名单作为主来源。
- 配置文件和环境变量只保留本地兜底。
- 记录 Skill、Tool、MCP 和模型配置的管理操作。
- 审计记录包含操作者、目标、前后值、结果和时间。

验收：

- 修改管理员不需要重启服务。
- 普通用户不能调用任何写管理 API。
- 管理操作可追溯且不会记录 secret 明文。

### P1.5 MCP 测试和 secret 管理

现状：MCP 可以 refresh 和修改，但没有独立的连接测试 API、数据库持久化或 secret store。

目标：

- 提供 server 连接测试和 tool schema/只读调用测试。
- 展示最近测试时间、延迟和结构化错误。
- MCP env 中的 secret 改由环境变量引用或 secret store 管理。
- Shell、文件系统、数据库写入和外部发送类 server 默认关闭。

验收：

- 管理员可在不进入聊天的情况下诊断 MCP。
- 高风险测试默认不执行真实写操作。
- API 和 UI 不返回 secret 明文。

## P2 前端与产品闭环

### P2.1 Chat 功能域继续拆分

现状：SSE hook 已拆出，但 `AIChat.tsx` 仍包含大量设置、catalog 和渲染逻辑。

目标结构：

```text
front/src/features/chat/
  api/
  components/
  hooks/useChatSettings.ts
  hooks/useSkillCatalog.ts
  hooks/useChatStream.ts
  storage.ts
  types.ts
```

验收：

- `AIChat.tsx` 只负责页面组合。
- 消息渲染、设置和 catalog 可以独立测试。
- Tool 确认和 regenerate 不依赖页面内部隐式状态。

### P2.2 其他大页面拆分

按风险顺序处理：

1. `NoteEditor.tsx`。
2. `ToolManager.tsx`。
3. `KnowledgeBase.tsx`。

拆分以业务边界和测试收益为依据，不进行纯目录重排。

### P2.3 记忆主动闭环

目标：

- 对话、笔记和翻译结束后生成候选事项。
- 用户确认后才写入 memory。
- 到期 reminder/todo/review 在页面内主动提示。
- 保存来源会话、消息或笔记。

验收：

- 自动提炼不会静默污染记忆。
- 完成、延期和归档后不重复提醒。

### P2.4 Memory 语义搜索

目标：

- 支持关键词和向量混合搜索。
- 按类型、状态、到期时间和 user ID 过滤。
- Agent Tool 返回来源、状态和更新时间。

## P2 RAG 与测试

### P2.5 RAG 边界和模型配置收敛

目标：

- 继续拆小 `knowledge_service.py`、`vector_store.py` 和 `rag_service.py`。
- 统一环境变量、用户配置和运行时实例的优先级。
- 删除不生效的 legacy `rag.yaml`。
- 为上传、解析、索引、召回和重排分别建立测试替身。

### P2.6 Benchmark 扩展

目标：

- 保留 offline smoke 作为日常 gate。
- 新增可选的真实 MySQL/Redis 集成层。
- 新增真实模型质量层，不纳入默认离线 gate。
- 对上下文摘要、MCP 恢复、客户端取消和认证边界增加 cases。

## P3 工程化

### P3.1 CI

- 后端单元测试与 compile check。
- 前端 test、build、lint。
- Markdown 本地链接和关键路径检查。
- Benchmark smoke gate。
- 可选数据库 migration 验证。

### P3.2 可复现开发环境

- 评估 Docker Compose 只承载 MySQL/Redis，而应用保留本地运行。
- 提供端口、volume 和健康检查定义。
- 不把大模型权重打进镜像。

### P3.3 翻译与桌面输入

- 连续字幕或文本流翻译。
- 翻译结果保存为笔记、术语表或候选记忆。
- 评估桌面通知和本地字幕来源。

这些能力必须在核心安全、运行时和部署基线稳定后推进。

## 推荐顺序

1. 正式 migration、生产配置、认证合同。
2. 摘要边界、事件分类、取消和 run 记录。
3. 数据库角色、审计和 MCP 测试。
4. Chat 与大页面拆分。
5. 记忆闭环和 Memory 搜索。
6. RAG 测试边界与 Benchmark 扩展。
7. CI、可复现基础设施和远期输入能力。
