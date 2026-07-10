# 当前架构

本文描述当前仓库中的服务、模块和运行边界。历史设计过程位于 `project_changes/`；尚未完成的工作位于 [下一阶段路线图](./roadmap_next.md)。

## 系统边界

Doki 助手是一个由三个应用进程组成的本地开发系统：

```mermaid
flowchart TD
  Browser[Browser] --> Front[React/Vite]
  Front -->|/user /file| Django[DjangoUserService]
  Front -->|Business API and SSE| API[FastAPI backend]

  Django --> UserDB[(MySQL user database)]
  Django --> Redis[(Redis)]

  API --> BusinessDB[(MySQL business database)]
  API --> Redis
  API --> Chroma[(ChromaDB)]
  API --> Files[(Local files)]

  API --> Runtime[Agent runtime]
  Runtime --> Local[Local Tools]
  Runtime --> MCP[MCP Tools]
  MCP --> External[External MCP server]
```

| 服务 | 主要职责 | 不负责 |
|------|----------|--------|
| React | 页面、交互状态、API 调用、SSE 消费 | 业务持久化、JWT 签发 |
| Django | 用户、JWT、用户资料、头像文件 | Agent、RAG、笔记和记忆 |
| FastAPI | Agent 和全部业务模块 | 登录注册、JWT 签发 |

开发环境由 Vite proxy 聚合两个后端。生产环境目前没有对应的反向代理或部署定义。

## 仓库结构

```text
backend/
  app/
    agent/          AgentFactory、上下文、流式运行、Skill/Tool、MCP
    cache/          Redis 缓存辅助
    config/         YAML 配置
    core/           初始化、日志、限流、响应和异常
    db/             MySQL、Redis 连接
    models/         SQLAlchemy 模型
    prompt/         Prompt 文本
    rag/            文档处理、向量索引、检索和重排
    router/         FastAPI 路由
    schemas/        Pydantic schema
    services/       业务服务和运行准备
    utils/          认证、模型、路径、文件、视觉等辅助
  tests/
  main.py

front/
  src/
    api/            Axios client、endpoint 和业务 API
    components/     通用与业务组件
    features/chat/  聊天 SSE hook、类型、存储和测试
    hooks/          通用 hooks
    i18n/           中英文文案
    layouts/        主布局和认证布局
    pages/          页面级组件
    router/         React Router
    stores/         Zustand stores
    types/          共享类型

DjangoUserService/
  apps/user/        用户模型、序列化、JWT 和用户接口
  apps/file/        头像上传
  DjangoUserService/ settings、URL、ASGI/WSGI
  manage.py

benchmarks/
  cases/            YAML cases
  fixtures/         离线脚本和工具数据
  runners/          CLI、harness、scorer、report
  schemas/          case JSON Schema
  baselines/        smoke baseline
  results/          本地运行产物
```

## FastAPI 启动过程

入口是 `backend/main.py`。

启动事件依次执行：

1. 创建缺失的 SQLAlchemy 表，并补充缺失列。
2. 初始化数据库会话管理器。
3. 建立 Redis 连接池。
4. 后台启动聊天模型、Embedding、Chroma NoteService 和 Reranker 初始化。
5. 刷新 MCP 工具并 reload SkillRegistry。

重型模型在后台初始化，因此 Uvicorn 端口可用不等于 Embedding 或 Reranker 已完成预热。`/health/ready` 当前只检查 MySQL 和 Redis。

关闭事件会关闭 MCP provider、Redis 连接池和 SQLAlchemy engine。

## FastAPI 分层

### Router

`backend/app/router/` 负责协议层：

- 接收 HTTP/SSE 参数。
- 注入 JWT、数据库会话和限流依赖。
- 调用 service 或 Agent 编排。
- 返回统一响应或 StreamingResponse。

主要 namespace：

| Namespace | 模块 |
|-----------|------|
| `/chat` | Agent、会话、RAG query、重新生成、高风险确认 |
| `/knowledge` | 文档入库、向量数据、Embedding/Reranker 配置 |
| `/note` | 笔记 CRUD、批处理和 AI 辅助 |
| `/note-template` | 笔记模板 |
| `/memory` | 记忆和事项 |
| `/model-config` | 用户模型配置 |
| `/translate` | 流式翻译 |
| `/skills` | Skill catalog 和管理 |
| `/tools` | 本地 Tool catalog 和管理 |
| `/api/mcp` | MCP catalog、权限和管理 |
| `/health` | 存活与就绪检查 |

Vite 对 `/api/skills` 和 `/api/tools` 去掉 `/api` 后再转发，因此浏览器使用的路径与 FastAPI 原始路径不同。

### Services

`backend/app/services/` 保存跨路由复用的业务规则。关键服务包括：

- `agent_run_service.py`：模型配置、Prompt 模式、Skill 预路由、MCP 自愈、Tool 解析和 system prompt。
- `database_session_manager.py`：会话消息、摘要和消息变更。
- `session_query_service.py`：会话读取、删除、RAG query 和重排入口。
- `note_service.py`：笔记业务与向量索引。
- `memory_service.py`：记忆事项 CRUD 和状态变化。
- `model_config_service.py`：用户模型配置与系统默认模型。
- `embedding_config_service.py`、`reranker_config_service.py`：知识库模型配置。
- `pending_action_store.py`：Redis 中一次性消费的高风险待确认动作。

### Models 与数据库

FastAPI 使用 SQLAlchemy async engine 和 MySQL。业务模型包括：

- `ChatSession` / `ChatMessage`。
- `Note` / `NoteTemplate`。
- `MemoryItem`。
- `KnowledgeSourceDocument`。
- `UserModelConfig`。
- 用户 Embedding 配置记录。Reranker 当前保存到 `backend/data/reranker_config.json`，不在业务表中。

FastAPI 目前没有 Alembic。启动时调用 `create_all`，并通过自定义逻辑增加缺失列；复杂 schema 迁移仍需要正式 migration 方案。

## Agent 运行时

旧版集中式 `backend/app/agent/agent.py` 已删除。当前职责拆分如下：

```text
backend/app/agent/
  factory.py             创建聊天模型和 AgentExecutor
  context_builder.py     历史、摘要、上下文窗口
  streaming.py           query、regenerate、confirm 的流式编排
  intent_router.py       Skill 预路由
  routing_calibration.py 路由阈值校准和缓存
  skill_registry.py      Skill、Local Tool、MCP Tool 注册与解析
  tool_guard.py          调用预算、确认、超时、输出截断
  tool_context.py        当前 user/session/run contextvars
  runtime/
    budget.py            读取 Agent 预算
    events.py            运行时事件结构
    event_pump.py        AgentExecutor astream_events 消费
    sse_driver.py        SSE、超时、停止和收尾
```

### Query 和 regenerate

```text
router/chat.py
  -> prepare_agent_run
      -> model config
      -> prompt mode
      -> route_skills
      -> MCP ensure_fresh
      -> resolve_skills
      -> build_chat_system_prompt
  -> streaming.py
      -> bind_run_context
      -> context_builder
      -> AgentFactory.create_agent_executor
      -> stream_agent_events
      -> drive_sse_stream
      -> save/replace message
```

Query 和 regenerate 共用 `prepare_agent_run`。二者分别构造新消息上下文和重新生成上下文，但使用同一 AgentFactory 与 SSE driver。

### SSE 合同

当前前端消费：

| 类型 | 作用 |
|------|------|
| `thinking` | 阶段、工具、耗时和运行状态 |
| `waiting_confirmation` | 高风险动作等待用户选择 |
| `response` | 最终回答增量 |
| `done` | 完成和 session 信息 |
| `error` | 运行错误 |

前端合同测试位于 `front/src/features/chat/__tests__/useChatStream.test.ts`，后端合同测试位于 `backend/tests/test_chat_stream_contract.py`。

## Skill 与 Tool

### Skill

```text
backend/app/agent/skills/<skill_id>/
  skill.yaml
  SKILL.md
```

`skill.yaml` 定义 ID、标签、绑定工具、默认状态、可见性、`always_on`、`routable` 和路由样例。`SKILL.md` 作为本轮 system prompt 的能力说明。

前端传入的 `skill_ids` 是候选上界：未显式指定 Tool 时，意图路由只在候选 Skill 中收窄。显式 `tool_ids` 表示精确工具控制，会跳过 Skill 收窄。

### 本地 Tool

```text
backend/app/agent/tools/<tool_id>/
  __init__.py
  tool.yaml
  TOOL.md
  tool.py
```

`tool.yaml` 定义 entrypoint、风险、确认、超时和输出长度。`TOOL.md` 进入工具说明，`tool.py` 返回 LangChain `BaseTool`。

### GuardedTool

本地 Tool 与 MCP Tool 在进入 Agent 前统一包装为 `GuardedTool`：

1. 增加本轮工具调用计数并检查预算。
2. 对 `requires_confirmation` 工具写入 Redis pending action 并阻断本次执行。
3. 使用 `asyncio.wait_for` 执行并限制超时。
4. 截断超过 `max_output_chars` 的结果。

pending action 默认 TTL 为 600 秒，按 `user_id` 校验，确认后一次性消费。

## MCP

MCP 是外部 Tool 来源，不替代本地 Tool。

```text
mcp.yaml
  -> McpToolProvider tools/list
  -> McpToolRegistry
  -> adapter to BaseTool
  -> ToolRegistry
  -> resolve_skills
  -> GuardedTool
  -> provider tools/call
```

当前支持：

- stdio、SSE、HTTP/streamable HTTP transport。
- server enable、label、description 和 URL 更新。
- tool label、description、enable、风险、确认、超时和输出限制 override。
- server/tool 删除写回 `mcp.yaml`。
- 普通用户只读，管理员 refresh 和修改。
- provider 错误状态和 Agent 请求时的惰性自愈。

完整说明见 [MCP 接入与管理](./mcp_integration_plan.md)。

## RAG 与知识库

```text
upload
  -> save source file and metadata
  -> parse document
  -> split chunks
  -> embedding
  -> Chroma index

query
  -> retrieve knowledge and note candidates
  -> rerank candidates
  -> build context
  -> LLM answer
```

模块边界：

- `router/knowledge_router.py`：HTTP/SSE 接口。
- `router/knowledge_service.py`：上传、源文件、任务和切片编排。
- `rag/document_handler/`：文档解析。
- `rag/vector_store.py`：Chroma 索引和 retriever。
- `rag/rag_service.py`：查询期召回、重排和上下文生成。
- `rag/reorder_service.py`：CrossEncoder Reranker。
- `utils/pdf_multimodal_loader.py`、`vision_service.py`：PDF 视觉处理。

有效配置分散在 `.env`、`config/chroma.yaml` 以及可写的 Embedding/Reranker 配置服务中。`config/rag.yaml` 已不生效。

## 前端

页面路由位于 `front/src/router/index.tsx`。主要页面：

- `/`、`/notes`、`/notes/:id`：笔记。
- `/chat`、`/chat/:sessionId`：Agent 对话。
- `/knowledge`：知识库。
- `/memory`：记忆中心。
- `/skills`、`/tools`：Skill/Tool/MCP 管理。
- `/model-settings`：模型配置。
- `/translate`：翻译。
- `/sessions`：会话列表。
- `/profile`、`/settings`：用户和界面设置。

JWT 保存在 `localStorage.jwt_token`。Axios interceptor 为 HTTP 请求添加 Bearer token，并在 401 时清理 token、跳转登录页。流式请求由 `features/chat/hooks/useChatStream.ts` 处理。

当前只完成聊天功能域拆分的第一阶段：SSE hook、types 和 storage 已移入 `features/chat`，但 `AIChat.tsx`、`NoteEditor.tsx`、`ToolManager.tsx` 和 `KnowledgeBase.tsx` 仍是较大的页面组件。

## 用户与认证

```text
React -> Django /user/login/
      <- JWT with user_id, jti, exp
React -> FastAPI Authorization: Bearer <token>
FastAPI -> decode shared-secret JWT -> user_id
```

- Django 签发 HS256 JWT，当前有效期 24 小时。
- FastAPI 使用 `SECRET_KEY` 和 `ALGORITHM` 解码。
- 两个服务通过 Redis 黑名单识别已撤销 token。
- FastAPI 业务数据查询必须携带当前 `user_id`。
- 管理员来自 `security.yaml` 与 `ADMIN_USER_IDS/ADMIN_USERNAMES`。

当前权限不是数据库角色模型，也没有完整管理审计。

## 数据位置

| 数据 | 位置 |
|------|------|
| 用户与认证数据 | Django MySQL database |
| 会话、笔记、记忆、知识元数据、模型配置 | FastAPI MySQL database |
| 缓存、token 黑名单、pending action | Redis |
| 知识库和笔记向量 | `backend/data/chromadb` |
| 上传源文件和解析图片 | `backend/data/` |
| Django 头像 | `DjangoUserService/media/` |
| Reranker 权重 | `backend/models/` |
| Benchmark 结果 | `benchmarks/results/` |

这些运行数据大多被 `.gitignore` 排除，不应作为可复现配置提交。

## 当前技术债

- FastAPI 数据库 schema 使用启动期自动补列，没有正式 migration 工具。
- 管理员权限仍是文件/环境变量名单。
- MCP 配置写回跟踪中的 YAML，缺少数据库配置和审计。
- RAG 关键文件仍较大，上传、索引和查询的测试隔离不足。
- 前端多个页面仍承担请求、状态与渲染混合职责。
- 生产部署、安全 header、TLS、secret manager 和 CI/CD 尚未定义。

这些未完成项在 [下一阶段路线图](./roadmap_next.md) 中按优先级维护。
