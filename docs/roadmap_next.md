# 全量重构开发计划

状态：基础工作包 `1-6` 已完成；长期阶段继续实施
计划基线：2026-07-16
最近复核：2026-08-18
适用范围：当前 `ai_document_assistant` 分支

本文是后续开发的主计划，只维护目标架构、实施阶段、依赖关系和验收门。下一项工作的序号入口见 [改进执行计划](./improvement_execution_plan.md)，安全问题的实现细节见 [安全与可靠性加固计划](./security_hardening_plan.md)，依赖、OpenAPI、lint 和 CI 的第一轮完整性整改记录见 [仓库更新完整性整改计划](./maintenance_update_plan.md)。`project_changes/` 只保存已经执行的历史记录。

本计划采用渐进式重构，不进行一次性重写。每个阶段必须保持现有用户数据可恢复、主流程可运行、验证命令可重复，才能进入下一阶段。

## 重构结果

完成后，项目应从当前 React + Django + FastAPI 三进程开发仓库，收敛为一个边界清楚、可迁移、可测试的模块化应用：

- 浏览器只面向一个同源 API 入口。
- FastAPI 承载用户、认证和现有业务 API；Django 用户服务完成兼容迁移后退出运行链路。
- MySQL schema 全部由版本化 migration 管理，不在应用启动阶段生成 migration 或执行通用 DDL。
- Redis 只承载明确有 TTL 和一致性策略的缓存、会话、限流与短期运行状态。
- Chroma 和源文件操作通过受约束的存储接口访问，文件路径和用户边界统一校验。
- Agent、RAG、模型和 MCP 都通过显式 adapter 接入，不让第三方 SDK 类型扩散到业务层。
- 前端按功能域组织；服务端状态、客户端状态和持久化偏好不再混在页面组件中。
- OpenAPI、SSE event schema、数据库 migration 和前端类型成为自动校验的合同。
- 本地开发和 production profile 使用相同代码路径，只在配置、基础设施和安全策略上区分。

## 当前基线

### 已验证并保留的能力

- Agent 运行时已经拆为 run preparation、context builder、factory、event pump 和 SSE driver。
- Query 与 regenerate 共用准备和流式执行链路。
- GuardedTool 已统一工具调用次数、确认、超时和输出截断。
- pending action 使用 Redis、TTL、用户隔离和一次性消费。
- Skill、Tool 和 MCP 已有统一 registry 和管理 API。
- 笔记、记忆、知识库、会话和模型配置查询大多携带 `user_id` 过滤。
- 知识库图片路径已有统一 containment、文件类型校验以及批量数量/字节预算。
- 聊天流式与历史消息共用安全 Markdown 渲染，不再执行原始 HTML 或危险 URL。
- Django 签发严格校验、可轮换的 access/refresh token；FastAPI 只接受 access token，前端只有一个认证状态来源。
- Django migration 和 FastAPI Alembic baseline 已进入版本控制，两个应用启动都不修改 schema。
- canonical JSON API 使用 `ApiResponse[T]`，OpenAPI 展示真实 envelope；SSE 事件固定携带 `schema_version: "1.0"`。
- Backend `118 passed`、Django `19 passed`、Frontend `20 passed`；Ruff、lint、build、OpenAPI、migration drift 和 Alembic offline SQL 通过。
- Offline smoke `4/4`、regression `117/117`，hard veto 为 0。

这些能力属于重构保护面。除非测试证明现有合同错误，不因目录调整而改变行为。

### 仍需替换的基础

- Django 只承担用户、JWT 和头像，却引入第二套运行时、依赖、数据库配置、文档和部署边界。
- RAG 的 MySQL、Chroma、MD5 文本文件、源文件和图片缺少统一事务/补偿边界。
- 前端页面直接处理请求、缓存、持久化、流式事件和渲染，组件测试覆盖不足。
- 自定义模型与 Embedding 地址仍缺少统一的 DNS、重定向和私网地址 egress 策略。
- 生产反向代理/TLS、备份恢复、可观测性、依赖扫描和发布回滚仍未完成演练。
- 用户唯一标识、数据库角色/审计来源和头像完整 UI 流程仍待后续阶段收敛。

## 架构决策

### ADR-001：收敛为 FastAPI 模块化单体

推荐方案：把用户和认证能力迁入 FastAPI，最终下线 `DjangoUserService`。

理由：

- 当前没有依赖 Django Admin、ORM 生态或模板系统的核心产品能力。
- 用户服务与业务服务共享 JWT secret 和 Redis 黑名单，分离没有形成独立安全边界。
- 跨服务用户状态校验、双 migration、双 OpenAPI 和双依赖管理增加了实际故障面。
- 项目当前以本地和单仓开发为主，模块化单体比两个后端进程更容易部署和恢复。

保留 Django 的条件：如果后续明确需要独立团队、独立扩缩容、Django Admin 或外部用户服务消费者，应在 R1 结束前提交 ADR 推翻本决策，并定义正式服务合同。没有该证据时按收敛方案执行。

### 目标运行拓扑

```text
Browser
  -> reverse proxy / Vite dev proxy
  -> FastAPI application
       -> auth and users
       -> chat and agent
       -> notes and memory
       -> knowledge and indexing
       -> model and integrations
       -> platform services
  -> MySQL
  -> Redis
  -> Chroma / source files
  -> optional worker process
  -> approved model and MCP endpoints
```

worker 是同一代码库的可选进程，不是新的业务服务。只有 PDF 解析、Embedding、重建索引等任务证明会阻塞 API 或需要可靠重试时才引入；队列实现通过 ADR 选择，不能同时维护 Celery、临时 thread 和多套 background task。

### 目标代码布局

```text
backend/app/
  main.py
  platform/
    config/
    db/
    cache/
    auth/
    errors/
    logging/
    storage/
  modules/
    users/
    chat/
    notes/
    memory/
    knowledge/
    models/
    skills/
    tools/
    mcp/
    translate/
  agent/
    runtime/
    routing/
    adapters/
  workers/
  migrations/

front/src/
  app/
    router/
    providers/
  shared/
    api/
    ui/
    lib/
  features/
    auth/
    chat/
    notes/
    memory/
    knowledge/
    models/
    integrations/
    profile/
```

目录不是目标本身。只有当模块拥有明确 router、schema、service/use case、query/repository 和测试边界时才移动文件。简单查询不强制套用 repository 或 unit-of-work 抽象。

## 实施原则

1. 先建立 characterization tests，再移动或替换实现。
2. API、SSE、数据和文件格式变更必须先定义兼容窗口和回滚路径。
3. 每次只迁移一个纵向功能域；旧实现与新实现不能无限期双写。
4. 所有 destructive migration 先备份、dry-run、校验数量，再切换读取路径。
5. 第三方模型、向量库和 MCP 通过 adapter 隔离，业务 service 不直接依赖 SDK response 类型。
6. 不以代码行数或目录数量作为完成标准，以合同、故障恢复和测试通过为准。
7. 安全修复不等待大重构；P0 问题直接在现有结构中修复并保留到新结构。
8. `project_changes/<日期-主题>/` 每个实施批次记录 `plan.md`、`change-log.md` 和 `test-record.md`，但活文档只更新当前事实。

## 2026-08-17 基础迭代结果

| 工作包 | 对应阶段切片 | 状态 | 结果 |
|--------|--------------|------|------|
| 1 知识库路径 containment | R0/R2 storage | 已完成 | 文件根目录、用户边界、符号链接与批量预算有自动测试 |
| 2 聊天安全渲染 | R0/R6 chat | 已完成 | 移除原始 HTML，流式/历史消息统一安全渲染 |
| 3 Token 生命周期 | R0/R3 auth | 已完成 | access/refresh、轮换、撤销、严格 claim 和前端单一状态来源落地 |
| 4 部署与鉴权可靠性 | R0/R2/R7 | 已完成 | 固定账号和启动副作用移除；生产配置、CORS 与限流 fail fast |
| 5 版本化数据库迁移 | R2 database | 已完成 | Django migration 与 Alembic baseline 入库，启动只校验 revision |
| 6 API/SSE 合同与特征测试 | R1/R7 | 已完成 | 泛型 envelope、版本化 SSE、真实响应/认证/迁移合同测试落地 |

这六项只完成了各阶段的基础切片，不等于 R0-R8 全部结束。尤其是服务端 egress、用户域收敛、模块化重组、长任务、完整前端重构和生产发布仍按下文阶段推进。认证合同为破坏性升级，旧的无类型 JWT 不兼容，部署后用户必须重新登录。数据库验证只使用临时 SQLite、revision 检查和 Alembic offline SQL，没有连接或修改现有 MySQL。

## 阶段依赖

```text
R0 safety freeze
  -> R1 contracts and characterization
  -> R2 platform and migration foundation
  -> R3 users/auth consolidation
  -> R4 backend domain modularization
       -> R5 agent, RAG and async work
       -> R6 frontend feature refactor
  -> R7 quality, performance and operations gates
  -> R8 cutover and legacy removal
```

R5 与 R6 可在 R3 稳定后并行。R7 是持续工作，但只有前置阶段功能稳定后才能设置最终门槛。R8 不能提前执行。

## R0 安全冻结

目标：先消除会使重构环境、测试数据或用户凭据失去可信度的问题。

状态：工作包 `1-4` 覆盖的路径、渲染、token、固定账号、CORS、限流和异步鉴权已完成；统一服务端 egress 策略保留为本阶段剩余项。

已完成：

- 修复知识库图片单文件和批量接口的路径 containment。
- 移除聊天消息原始 HTML，并过滤危险 URL。
- 使用 access/refresh token、严格过期与用户状态校验、确定性 Redis 撤销键和 fail-closed 故障语义。
- 统一前端认证来源，确保 401、注销和 refresh 失败完整清理认证状态。
- 把异步鉴权链中的同步 HTTP 请求替换为有 timeout、取消和故障合同的异步 client。
- 停止默认创建固定密码账号，启用登录/注册/refresh 限流。
- 补充上述问题的单元、API 和前端回归测试。

剩余：

- 为自定义模型和 Embedding 地址增加部署模式相关的 DNS、重定向和私网地址 egress 策略。
- 完成反向代理/TLS、依赖扫描、secret scanning 和生产回滚演练。

详细要求见 [安全与可靠性加固计划](./security_hardening_plan.md)。

当前验收：

- `SEC-01`、`SEC-02`、`AUTH-01`、`AUTH-02`、`AUTH-03`、`DEPLOY-01`、`DEPLOY-02` 和 `REL-01` 已有自动测试。
- 受控恶意输入不能读取项目文件、执行 HTML 或重放 refresh token。
- Backend、Django、Frontend 和 Benchmark 门禁通过。
- R0 只有在 egress 和生产演练完成后才整体关闭。

相对工作量：M。

## R1 合同与特征测试

目标：在移动代码前固定系统真正需要保持的外部和数据行为。

状态：工作包 `6` 已完成 HTTP/SSE 与认证合同基线；完整数据清单、性能基线和所有待迁移路由的 characterization test 仍未完成。

工作：

### HTTP 与 SSE

- 已定义泛型 `ApiResponse[T]`，canonical JSON handler 的 OpenAPI 与真实 envelope 一致。
- 文件下载、SSE 和普通 JSON 已分别声明；SSE 路由发布 `text/event-stream`。
- chat、knowledge、note 和 translate 事件固定携带 `schema_version: "1.0"`，并有合同测试。
- 认证、refresh、logout、撤销存储故障和限流状态码已有跨服务合同测试。
- 后续如统一 `run_id/session_id/sequence/timestamp/payload` 事件 envelope，必须升级 schema version 并定义兼容窗口。

### 数据与文件

- 盘点两个 MySQL database 的表、行数、主键、索引和外键缺口。
- 盘点 Redis key 前缀、TTL、所有者和不可用策略。
- 盘点 Chroma collection、metadata、MD5 文件、源文件和解析图片格式。
- 为当前数据生成只读一致性检查，不在此阶段修改生产数据。

### Characterization tests

- Django 已覆盖注册、登录、refresh、注销、改密/版本失效、锁定及 Redis 故障；头像完整流程仍待补充。
- FastAPI 已覆盖认证、知识路径、canonical JSON 响应、SSE、迁移与限流合同；其余业务路由继续补齐 TestClient 测试。
- 对跨用户访问建立 hard veto 测试。
- 记录关键页面和 API 的初始性能、bundle 与响应大小基线。

产物：

- ADR-001 最终决议。
- 版本化 OpenAPI 和 SSE schema。
- 数据清单、备份命令和迁移前校验报告。
- 可运行的旧行为特征测试。

退出门：所有计划迁移的路由和数据都有现状测试或明确废弃决策。

相对工作量：M。

## R2 平台与 migration 基础

目标：建立后续模块共享且不会反复改写的基础设施。

状态：工作包 `4-5` 已完成生产配置校验、CORS/限流基础和两套版本化 migration；统一 settings、transaction、storage、egress 与日志平台仍待实施。

工作：

### 配置

- 已为 Django/FastAPI 增加 dev/test/prod 边界和生产 fail-fast 校验。
- 使用单一 Pydantic Settings 入口，按 dev/test/prod profile 校验。
- 删除模块内散落的 `load_dotenv()` 和 import-time 配置快照。
- 把 secret、路径、外部 URL 和运行预算按命名空间组织。

### 数据库

- 已引入 Alembic baseline `20260817_0001`，应用启动只验证 revision。
- 已跟踪 Django user migration，并移除启动期 migration 生成和执行逻辑。
- CI 已加入 Alembic、Django migration drift 和 Django tests；当前验证未连接或修改现有 MySQL。
- 定义 transaction helper；router 不直接管理 commit/rollback。
- 补齐关键唯一约束、组合索引和删除策略。

### 通用平台

- 统一错误类型、request/run ID、结构化日志和敏感字段脱敏。
- 定义 Redis key builder，禁止业务代码手写不一致前缀。
- 定义受根目录约束的 storage interface。
- 统一 HTTP client timeout、重试、重定向和 egress policy。

最终退出门：

- 空数据库可应用全部 migration；已有数据库可从 baseline 升级。
- 应用启动不再执行 schema 修改。
- 配置缺失在启动阶段给出确定错误。
- 所有文件和 Redis 操作通过共享 platform API。

相对工作量：L。

## R3 用户与认证收敛

目标：把用户、认证、角色和头像迁入 FastAPI，同时保留可回滚兼容期。

### 新模型

- `users`：沿用现有稳定 UUID，唯一 email，按 ADR 决定唯一 username。
- `auth_sessions` 或 `refresh_tokens`：记录 token family、version、过期、撤销和设备摘要。
- `roles/user_roles`：替代 YAML 管理员名单作为主来源。
- `audit_events`：记录用户、模型、Skill、Tool 和 MCP 管理操作，不保存 secret 明文。

### 密码与 token 迁移

- 导入 Django 用户时保留 UUID、email、状态、资料和 password hash。
- 提供 Django PBKDF2 hash 兼容 verifier；首次成功登录后重哈希到目标算法。
- 无法安全兼容的 hash 必须走强制重置，不能静默创建默认密码。
- 新 access token 使用短 TTL；refresh token 固定最大寿命并轮换。
- issuer、audience、type、session/token version 和用户状态成为必检项。

### 兼容切换

1. FastAPI 新增与现有 `/user/*`、`/file/*` 兼容的路由。
2. 离线导入用户并比对数量、UUID、状态和 hash 类型。
3. 在测试环境用旧 token、新 token、注销和锁定场景交叉验证。
4. 前端代理切到 FastAPI，但保持请求路径和响应短期兼容。
5. 观察期内 Django 只读或停止签发新 token；不长期双写用户。
6. 完成备份恢复演练后下线 Django 进程。

回滚：保留迁移前数据库备份和代理切换开关；回滚时恢复路由，不反向覆盖旧用户库。

退出门：

- 用户数量和身份字段迁移一致。
- 旧密码可登录并升级 hash，或有明确重置流程。
- 注销、锁定、改密和 refresh 在单一服务内一致生效。
- 前端不再依赖 Django 进程。

相对工作量：XL。

## R4 后端功能域模块化

目标：按业务能力重组 FastAPI，消除 router、service、全局 init manager 和存储实现之间的隐式耦合。

迁移顺序：

1. `notes` 与 `memory`：数据关系清楚，适合作为模块模板。
2. `chat` 与 sessions：统一消息、摘要和 regenerate transaction。
3. `models`：统一系统配置、用户配置、加密和 provider adapter。
4. `skills/tools/mcp`：统一 catalog、权限、配置和审计。
5. `knowledge`：最后迁移复杂的文件、数据库和向量状态。

每个模块包含：

- router 只负责 HTTP 解析、依赖和响应。
- schema 定义模块输入输出，不复用 ORM model 作为 API 类型。
- service/use case 定义 transaction 和权限边界。
- query/repository 只在能隔离复杂持久化时引入。
- adapter 负责 MySQL、Chroma、文件或第三方 SDK。
- tests 覆盖正常、越权、冲突、部分失败和重试。

知识库额外要求：

- MySQL source document 是状态主记录，包含 `queued/processing/ready/failed/deleting`。
- Chroma、MD5 和图片写入必须幂等，并有可重跑 reconciliation job。
- 不再把文本 MD5 文件作为唯一事实来源；迁移后由数据库唯一约束防重。
- 删除先标记状态，再执行向量/文件清理，失败可重试而不丢主记录。

退出门：模块间只能通过公开 service/schema 或 event 合同调用；不得跨模块直接查询私有表或拼接私有文件路径。

相对工作量：XL。

## R5 Agent、RAG 与异步工作

目标：保留已验证 Agent 核心，收敛模型/工具 adapter、运行状态、取消和长任务执行。

### Agent runtime

- 保留 `prepare_agent_run`、event pump、SSE driver 和 GuardedTool 的现有测试合同。
- 把模型、retriever、Tool registry、pending action 和 session store 定义为显式 ports。
- 使用 request-scoped run context，减少可变全局 `init_manager`。
- 持久化 run 状态、停止原因、模型、Skill/Tool 摘要和耗时。
- 客户端断开时传播 cancellation 到模型、retriever 和 MCP 调用。

### RAG

- 上传、解析、切片、Embedding、写索引和发布状态拆成可重试步骤。
- 统一用户 Embedding/Reranker 配置的解析和实例缓存失效。
- 文件解析设置页数、解压后大小、图片数、总像素和处理时间预算。
- 将视觉模型和本地 reranker 的重资源初始化从 API startup 解耦。

### 异步队列决策

先用测量证明任务需要 worker，再通过 ADR 选择一种队列。要求支持幂等 key、重试上限、超时、取消、进度和 dead-letter 诊断。旧的 thread、`asyncio.create_task` 和队列实现随迁移删除，不能叠加。

退出门：

- Agent 现有 117 个 offline regression case 不回退。
- 重复上传/重试不会产生重复向量或孤立文件。
- API 进程不因模型初始化或大文档处理失去 readiness。
- 客户端取消和 worker 失败有确定状态。

相对工作量：L。

## R6 前端功能域重构

目标：让页面只组合功能，API、服务端状态、流式状态、表单和渲染可以独立测试。

状态：聊天安全渲染、前端单一认证 store、并发刷新和注册/注销浏览器验收已完成；页面功能域拆分、头像、知识上传及完整 E2E 仍待实施。

### 基础层

- 生成或校验 OpenAPI TypeScript 类型，减少手写响应漂移。
- Axios/fetch 共享一个认证、错误和 abort 策略。
- 评估 TanStack Query 管理普通服务端状态；Zustand 只保留跨页客户端偏好和短期 UI 状态。
- 统一 loading、empty、error、permission denied 和 retry UI。
- 增加 route error boundary 和未登录/权限路由守卫。

### 迁移顺序

1. `auth/profile`：配合 R3 完成 token、401 和头像流程。
2. `chat`：拆出 message renderer、composer、catalog、settings、confirmation 和 history。
3. `knowledge`：拆出 upload job、document list/detail、Embedding 和 Reranker settings。
4. `notes`：拆出 editor、autocomplete、AI assist、related、template 和 batch actions。
5. `tools/integrations`：拆出 Skill、Tool、MCP 权限和配置表单。
6. `memory/models/translate/sessions`：迁移剩余页面并清理旧 API 层。

### 前端安全与性能

- 消息 Markdown 已统一使用安全渲染，禁止任意原始 HTML 和危险 URL。
- 外部链接统一 `rel="noopener noreferrer"`，图片和下载来源受约束。
- 清理 blob URL、AbortController 和流式 reader，避免页面切换后泄漏。
- 对当前大 chunk 建立不回退预算，按编辑器和 Markdown 能力延迟加载。

退出门：

- 页面组件不直接拼接 API URL 或操作 token storage。
- Chat、Knowledge、NoteEditor、Profile 有组件/交互测试。
- 登录、聊天、上传、笔记和模型配置有 Playwright 主流程。
- lint、test、typecheck、build 和 bundle budget 进入 CI。

相对工作量：XL。

## 产品迭代队列

以下功能均为保留项，尚未执行。具体可选择的工作包、依赖和验收条件见 [改进执行计划](./improvement_execution_plan.md)：工作包 `7` 对应 F1/F2，`8` 对应 F3，`9` 对应 F4，`10` 对应 F5/F6。

| 顺序 | 功能 | 状态 | 用户价值 | 主要依赖 |
|------|------|------|----------|----------|
| F1 | 回答引用与来源抽屉 | 保留，未执行 | 让知识库回答可核验并可返回原文 | R0 安全渲染、R1 SSE/API 合同 |
| F2 | 回答一键沉淀为笔记或记忆 | 保留，未执行 | 打通聊天、笔记、记忆，保留来源关系 | R1 合同、R4 notes/memory/chat 边界 |
| F3 | 知识处理任务中心 | 保留，未执行 | 提供持久进度、取消、失败诊断和重试 | R2 migration、R4 knowledge 状态、R5 worker 决策 |
| F4 | 跨域统一搜索 | 保留，未执行 | 统一检索笔记、记忆、会话和知识文档 | R2/R4 数据边界和用户隔离测试 |
| F5 | Agent 运行记录 | 保留，未执行 | 展示模型、Skill、Tool、耗时、错误和停止原因 | R1 event schema、R5 run context、R7 可观测性 |
| F6 | 版本化导出与恢复 | 保留，未执行 | 让个人知识资产可迁移、可校验、可恢复 | R2 migration/storage、R7/R8 恢复演练 |

产品功能应按 F1、F2、F3、F4、F5、F6 推进。F1 与 F2 可形成第一个用户可见增量；F3 和 F4 在数据状态未版本化前不启动。

## R7 质量、性能与运维门禁

目标：把重构期间依赖人工记忆的检查变为自动 gate。

### 测试层

| 层 | 目标 |
|----|------|
| Unit | 纯业务规则、路径/URL 策略、token、scorer、event schema |
| API | FastAPI dependency override + 临时数据库/存储替身 |
| Integration | MySQL、Redis、Chroma、跨服务迁移兼容；可选独立 CI job |
| Frontend | hooks、components、错误态和安全渲染 |
| E2E | 注册/登录、聊天、知识上传、笔记、注销和管理员权限 |
| Benchmark | Agent 质量、工具安全、隔离 veto、延迟和事件合同 |

不追求单一全仓覆盖率数字。认证、路径、权限、migration 和数据删除必须达到分支覆盖；UI 展示代码按风险设置较低门槛。

### CI

- Ruff 覆盖 `main.py app tests scripts mcp_servers seed_templates.py`。
- Django 在退出前运行 migration check 和用户测试；退出后删除对应 job。
- Backend 运行 unit/API、OpenAPI、migration、requirements 和 offline benchmark。
- Frontend 运行 lint、typecheck、unit/component、build 和关键 E2E。
- 增加依赖漏洞、secret 和许可证检查；扫描结果使用可审阅例外，不静默忽略。
- generated artifacts 和测试结果使用临时目录，结束后不污染工作树。

### 可观测与性能

- 为 HTTP、Agent run、Tool、MCP、RAG job 添加结构化 duration/status/error_type。
- 定义 readiness 与 liveness；readiness 不触发昂贵模型调用。
- 记录数据库慢查询、Redis 命令、队列积压和外部调用超时。
- 建立上传大小、解析时间、SSE 首 token、普通 API p95 和 bundle 大小预算。

退出门：所有主分支 required checks 稳定通过，故障注入能验证 Redis、模型、MCP 和 worker 不可用时的降级策略。

相对工作量：L，贯穿 R0-R8。

## R8 切换、清理与部署

目标：删除兼容期代码，形成单一运行方式和可恢复部署流程。

工作：

- 停止并移除 Django 代理路径、启动命令和运行依赖。
- 在数据备份和验收记录确认后归档或删除 `DjangoUserService/`；Git 历史保留实现。
- 删除旧 JWT、黑名单兼容、双配置、无效 `rag.yaml` 和未使用 Celery/数据库驱动。
- 删除已经迁移的旧 router/service/helper，不保留同名 v1/v2 无限并存。
- 提供一键本地启动、基础设施启动和 production deployment/runbook。
- 演练数据库、Redis、Chroma 和文件备份恢复，以及应用版本回滚。
- 更新根 README、架构、API、环境变量和故障排除文档。

退出门：

- 浏览器和 FastAPI 主流程不需要 Django 进程。
- 干净环境可按文档完成 install、migrate、seed、start、test 和 rollback。
- 旧数据校验报告、迁移记录和回滚演练可追溯。
- [安全与可靠性加固计划](./security_hardening_plan.md) 的公网就绪条件全部满足，或 README 继续明确只支持本地使用。

相对工作量：M。

## 工作包与里程碑

| 里程碑 | 包含阶段 | 状态 | 对外结果 | 规模 |
|--------|----------|------|----------|------|
| M0 安全可信基线 | R0 | 基础切片完成，egress 保留 | 已知文件、渲染、凭据和 token 高风险输入被阻断 | M |
| M1 合同冻结 | R1 | 部分完成 | API/SSE/认证合同已验证，数据清单与全路由特征测试待补 | M |
| M2 平台可迁移 | R2 | 部分完成 | migration 与生产配置基础完成，storage/egress 平台待补 | L |
| M3 单一身份源 | R3 | 未执行 | FastAPI 承载用户认证，Django 可下线 | XL |
| M4 模块化后端 | R4 | 未执行 | 功能域边界和数据补偿明确 | XL |
| M5 稳定运行时 | R5 | 未执行 | Agent/RAG 可取消、可重试、可观测 | L |
| M6 可测试前端 | R6 | 部分完成 | 安全渲染与认证基础完成，功能域 UI 和完整 E2E 待补 | XL |
| M7 发布就绪 | R7-R8 | 未执行 | required gates、单一运行方式和回滚流程 | L |

规模只表示相对复杂度。没有团队容量、发布窗口和数据规模前，不把它换算为承诺日期。每个里程碑应再拆成不超过一个功能域的独立 change plan。

## 每个变更的完成定义

- 有明确问题、范围、非目标和回滚方法。
- 先增加失败测试或 characterization test，再修改实现。
- 用户、数据、文件和网络边界经过威胁检查。
- API/OpenAPI、migration、环境变量或运行方式变化同步更新活文档。
- 相关 lint、unit、integration、frontend、build 和 benchmark 通过。
- 不提交 `.env`、本机配置、模型、运行数据、Benchmark result 或临时构建。
- `git diff` 只包含该工作包需要的代码、测试、migration 和文档。

## 禁止事项

- 不建立长期 `v2` 目录后让旧实现永久并存。
- 不在没有备份和验证脚本时迁移或删除用户、向量和源文件。
- 不用全局关闭 lint/typecheck 规则换取“重构通过”。
- 不用前端隐藏替代后端权限。
- 不因引入队列、repository、event bus 或微服务看起来更先进就提前增加抽象。
- 不在同一个提交同时切换认证源、数据库 schema、全部 API 和前端路由。

## 下一步

基础工作包 `1-6` 已完成。下一轮可从 [改进执行计划](./improvement_execution_plan.md) 选择 `7-10`，默认优先 `7`；所有四项目前都只是保留计划，选择后仍需在对应 `project_changes/<日期-主题>/` 目录建立 `plan.md`、`change-log.md` 和 `test-record.md`。长期架构工作继续从 R0 的 egress 剩余项、R1 数据清单和 R2 platform API 向 R3-R8 推进，不能把基础切片完成等同于 Django 下线、模块化重构或生产发布完成。
