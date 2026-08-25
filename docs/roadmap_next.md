# 全量重构开发计划

状态：基础工作包 `1-6` 已完成；工作包 `11` 标准 Skill 单轨重构为当前最高优先级必做项；工作包 `7-10` 冻结
计划基线：2026-07-16
最近复核：2026-08-24
适用范围：当前 `ai_document_assistant` 分支

本文是后续开发的主计划，只维护目标架构、架构重写阶段、依赖关系和验收门。当前运行事实见[当前架构](./project_develop.md)；架构重写的细化执行入口见[架构重写计划](./architecture_rewrite_plan.md)；标准 Skill 核心合同见[标准 Skill 接入需求规格](./standard_skill_integration_requirements.md)；工作包序号入口见[改进执行计划](./improvement_execution_plan.md)；安全问题的实现细节见[安全与可靠性加固计划](./security_hardening_plan.md)。`project_changes/` 只保存已经执行的历史记录。

本计划采用可靠性优先、分阶段、可回滚的架构重写，不是一次性大爆炸发布。先完成 SLO/RPO/RTO、故障隔离、持久任务、备份恢复和迁移回滚基础，再迁移身份、关系数据和业务模块。详细阶段、数值门槛和 `ARCH-GATE` 以 [架构重写计划](./architecture_rewrite_plan.md) 为唯一事实源；本文只维护目标态与 R0-R8 映射。

## 目标架构（`ARCH-GATE` 通过后）

以下内容是目标态，当前尚未完成。项目应从当前 React + Django + FastAPI 三进程开发仓库，收敛为一个边界清楚、可迁移、可测试的模块化应用：

- 浏览器只面向一个同源 API 入口。
- FastAPI API runtime 承载用户、认证和现有业务 API；同一代码库的 worker runtime 独立运行并承担可恢复的长任务；Django 用户服务完成兼容迁移后退出运行链路。
- MySQL schema 全部由版本化 migration 管理，不在应用启动阶段生成 migration 或执行通用 DDL。
- MySQL 是关系事实和认证撤销/审计的权威；部署拓扑具备 primary/replica、PITR 或明确的单实例限制。
- Redis 只承载明确有 TTL、容量和故障策略的缓存、限流与短期运行状态，不承担不可恢复的认证事实。
- Chroma 是带版本 manifest 的可重建 projection；源文件通过不可变对象和 checksum/atomic finalize 的 Storage 接口访问。
- API、worker、模型、Storage 和向量索引分别有资源上限、降级语义和 readiness 状态。
- Agent、RAG、模型和 MCP 都通过显式 adapter 接入，不让第三方 SDK 类型扩散到业务层。
- Skill 全面采用标准 `SKILL.md` package、统一版本/安装/授权领域和可视化管理；不存在内置私有格式、双 Registry 或 API 进程脚本执行。
- 前端按功能域组织；服务端状态、客户端状态和持久化偏好不再混在页面组件中。
- OpenAPI、SSE event schema、数据库 migration 和前端类型成为自动校验的合同。
- 本地开发和 production profile 使用相同代码路径，只在配置、基础设施和安全策略上区分。

在 `ARCH-GATE` 通过前，README 和开发说明中的三进程启动方式仍是过渡基线，不能视为目标运行方式。

## 当前基线

### 已验证并保留的能力

- Agent 运行时已经拆为 run preparation、context builder、factory、event pump 和 SSE driver。
- Query 与 regenerate 共用准备和流式执行链路。
- GuardedTool 已统一工具调用次数、确认、超时和输出截断。
- pending action 使用 Redis、TTL、用户隔离和一次性消费。
- Skill 已有标准 package parser、版本领域、对象存储、管理 API/UI、资源编辑和 A/有限 B 运行桥接；CapabilityGrant、SkillRunBinding、private Skill/Tool 过滤、多实例 revision/outbox reconcile、stale `503` 和旧运行目录静态禁回归已经落地。前端允许格式兼容但 runtime 未就绪的 C 包禁用安装和管理，仍禁止启用或执行。Tool/MCP 仍是 Doki host capability provider；该实现尚未通过完整可靠性、真实 E2E 和跨平台门禁，不是目标完成态。
- 笔记、记忆、知识库、会话和模型配置查询大多携带 `user_id` 过滤。
- 知识库图片路径已有统一 containment、文件类型校验以及批量数量/字节预算。
- 聊天流式与历史消息共用安全 Markdown 渲染，不再执行原始 HTML 或危险 URL。
- Django 签发严格校验、可轮换的 access/refresh token；FastAPI 只接受 access token，前端只有一个认证状态来源。
- Django migration 和 FastAPI Alembic baseline 已进入版本控制，两个应用启动都不修改 schema。
- canonical JSON API 使用 `ApiResponse[T]`，OpenAPI 展示真实 envelope；SSE 事件固定携带 `schema_version: "1.0"`。
- Backend `216 passed`、Django `19 passed`、Frontend `6 files / 28 tests passed`；Ruff、compileall、`uv lock`、requirements、lint/build 和 OpenAPI 通过。Alembic head 为 `20260824_0002`，upgrade/downgrade offline SQL 通过。
- Offline smoke `4/4`、regression `117/117`，hard veto 为 0。

这些能力属于重构保护面。除非测试证明现有合同错误，不因目录调整而改变行为。它们是迁移基线，不等于架构重写完成。

### 仍需替换的基础

- Django 只承担用户、JWT 和头像，却引入第二套运行时、依赖、数据库配置、文档和部署边界。
- RAG 的 MySQL、Chroma、MD5 文本文件、源文件和图片缺少统一事务/补偿边界。
- 前端页面直接处理请求、缓存、持久化、流式事件和渲染，组件测试覆盖不足。
- 自定义模型与 Embedding 地址仍缺少统一的 DNS、重定向和私网地址 egress 策略。
- 生产反向代理/TLS、备份恢复、可观测性、依赖扫描和发布回滚仍未完成演练。
- 用户唯一标识、数据库角色/审计来源和头像完整 UI 流程仍待后续阶段收敛。
- Skill 数据权威已切到 MySQL + 不可变 package Storage；旧 `backend/app/agent/skills` 的 20 个运行文件已经删除，标准 seed package 保留在 `backend/app/skills/seed_packages`。系统级 grant/RunBinding、private 过滤和多实例 reconcile 已完成；仍缺 durable import worker、per-user scope、累计资源 token 预算、C 级隔离执行和完整真实 E2E/故障恢复，必须在工作包 `11` 后续阶段补齐。

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
  -> worker runtime (same codebase, separate process/resource pool)
  -> approved model and MCP endpoints
```

worker 是同一代码库的独立运行时，不是新的业务服务。AR-1 必须先落地最小 durable job runner（可先用 MySQL polling）；队列产品选型可以后置，但不能继续依赖请求内线程、`asyncio.create_task` 或进程内队列承载事实状态。

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
7. 架构重写前冻结新增产品功能和非必要结构扩展；仅允许 P0 安全、数据完整性、服务启动阻断修复，并要求同步验证其在目标结构中的落点。
8. `project_changes/<日期-主题>/` 每个实施批次记录 `plan.md`、`change-log.md` 和 `test-record.md`，但活文档只更新当前事实。
9. “一个单体”指一个业务代码库和关系写权威，不指一个进程；API 与 worker 必须按故障域和资源预算隔离。

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

## 架构重写前置门禁

在开始工作包 `7-10` 或任何新的普通产品改进前，必须完成[架构重写计划](./architecture_rewrite_plan.md)的 `AR-0` 至 `AR-6`、标准 Skill `SK-0` 至 `SK-5`，并依次通过 `SKILL-GATE` 和 `ARCH-GATE`。工作包 `11` 是当前核心重构，不等待 `ARCH-GATE`；但它不能绕过所依赖的 AR 安全与可靠性基础。

```text
AR-0 可靠性契约/P0止血 + SK-0
  -> AR-1 API/worker隔离与持久任务 + SK-1
  -> AR-2 身份迁移与认证回滚
  -> AR-3 可恢复关系数据迁移
  -> AR-4 Storage canonical 与索引投影 + SK-2
  -> AR-5 首域 skills/tools/mcp + SK-3
  -> SK-4 C级隔离执行
  -> AR-6 灰度切换/HA/停用 + SK-5
  -> SKILL-GATE
  -> ARCH-GATE -> 7-10 / 新功能
```

重写期间允许并要求完成标准 Skill 单轨改造及其可视化管理；除此之外只允许 P0 安全、数据完整性、启动阻断修复和门禁底座，不允许借机新增其他用户功能。

## 现有 R0-R8 阶段依赖（映射维度）

```text
R0/R1 reliability contract and characterization
  -> R2 platform, durable jobs and migration foundation
  -> R3 users/auth consolidation
  -> R5 storage, agent/RAG and async projection foundation
  -> R4 backend domain modularization
       -> R6 frontend feature refactor
  -> R7 quality, SLO and fault gates
  -> R8 canary cutover, HA and legacy removal
```

R5 的可靠性底座不能等待产品工作包 8 解锁；durable job、SSE replay、索引状态和 readiness 属于 AR-1/AR-4 的前置基础。Skill package 是 Storage 和 worker 的首个业务 consumer，`skills/tools/mcp` 是 R4 的首个后端域，Skill 管理是前端共享基础后的首个功能域。R7 是持续工作，但最终门槛只能在 AR-6/SK-5 前完成。R8 不能提前执行。

## R0 可靠性与安全冻结

目标：先消除会使重构环境、测试数据或用户凭据失去可信度的问题，并冻结可量化的可靠性合同。

状态：工作包 `1-4` 覆盖的路径、渲染、token、固定账号、CORS、限流和异步鉴权已完成；统一 egress、SLO/RPO/RTO、故障矩阵、备份 manifest、分层 readiness 和 Chroma 破坏性 reset 止血仍待 AR-0。

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
- 明确 API/worker/模型/Storage/Chroma 的故障域、timeout/retry/circuit breaker/bulkhead/fallback 和资源预算。
- 为关系库、认证审计、源文件和索引生成同一 generation manifest，完成隔离恢复抽样和组合故障演练。
- 禁止 Chroma 初始化异常递归删除持久目录，改为隔离、只读降级和可审计重建。
- 完成反向代理/TLS、依赖扫描、secret scanning 和生产回滚演练。

详细要求见 [安全与可靠性加固计划](./security_hardening_plan.md)。

当前验收：

- `SEC-01`、`SEC-02`、`AUTH-01`、`AUTH-02`、`AUTH-03`、`DEPLOY-01`、`DEPLOY-02` 和 `REL-01` 已有自动测试。
- 受控恶意输入不能读取项目文件、执行 HTML 或重放 refresh token。
- Backend、Django、Frontend 和 Benchmark 门禁通过。
- R0 只有在 egress 和生产演练完成后才整体关闭。

相对工作量：M。

## R1 合同、特征测试与恢复语义

目标：在移动代码前固定系统真正需要保持的外部和数据行为。

状态：工作包 `6` 已完成 HTTP/SSE 与认证合同基线；完整数据清单、性能基线和所有待迁移路由的 characterization test 仍未完成。

工作：

### HTTP 与 SSE

- 已定义泛型 `ApiResponse[T]`，canonical JSON handler 的 OpenAPI 与真实 envelope 一致。
- 文件下载、SSE 和普通 JSON 已分别声明；SSE 路由发布 `text/event-stream`。
- chat、knowledge、note 和 translate 事件固定携带 `schema_version: "1.0"`，并有合同测试。
- 后续 SSE 合同必须加入 `event_id`、`run_id`、序号和 cursor；断线支持 `Last-Event-ID` 重放或 polling fallback，不能只保证 schema version。
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
- 记录普通 API p95/p99、SSE 首事件和重连、队列积压、索引新鲜度、RPO/RTO 及告警阈值基线。

产物：

- ADR-001 最终决议。
- 版本化 OpenAPI 和 SSE schema。
- 数据清单、备份命令和迁移前校验报告。
- 可运行的旧行为特征测试。

退出门：所有计划迁移的路由和数据都有现状测试或明确废弃决策。

相对工作量：M。

## R2 平台、持久任务与 migration 基础

目标：建立后续模块共享且不会反复改写的基础设施，并先提供可恢复的 API/worker 任务底座。

状态：工作包 `4-5` 已完成生产配置校验、CORS/限流基础和两套版本化 migration；统一 settings、transaction、storage、egress、日志、API/worker 隔离和 durable job 仍待实施，属于 `AR-1` 的交付内容。

工作：

### 配置（部分已完成；统一平台待 `AR-1`）

- 已为 Django/FastAPI 增加 dev/test/prod 边界和生产 fail-fast 校验。
- 目标是使用单一 Pydantic Settings 入口，按 dev/test/prod profile 校验（待 `AR-1`）。
- 目标是删除模块内散落的 `load_dotenv()` 和 import-time 配置快照（待 `AR-1`）。
- 目标是把 secret、路径、外部 URL 和运行预算按命名空间组织（待 `AR-1`）。

### 数据库

- 已引入 Alembic baseline `20260817_0001`，应用启动只验证 revision。
- 已跟踪 Django user migration，并移除启动期 migration 生成和执行逻辑。
- CI 已加入 Alembic、Django migration drift 和 Django tests；当前验证未连接或修改现有 MySQL。
- 目标是定义 transaction helper；router 不直接管理 commit/rollback（待 `AR-1`）。
- 目标是规定只有 application/use-case 层可以 commit；outbox 与业务事实同一事务，并用静态检查阻止 service/repository 直写提交（待 `AR-1`）。
- 目标是补齐关键唯一约束、组合索引和删除策略（待 `AR-1`/`AR-3`）。

### 通用平台

- 目标是统一错误类型、request/run ID、结构化日志和敏感字段脱敏（待 `AR-1`）。
- 目标是定义 Redis key builder，禁止业务代码手写不一致前缀（待 `AR-1`）。
- 目标是定义受根目录约束的 storage interface（待 `AR-1`）。
- 目标是统一 HTTP client timeout、重试、重定向和 egress policy（待 `AR-1`）。
- 目标是 API 与 worker 独立进程/资源池，落地 lease/heartbeat/fencing、幂等、重试、DLQ、取消、背压和配额（待 `AR-1`）。
- 目标是 readiness 分层为 live/core/auth/model/index/worker，并让后台初始化失败反映为可见降级（待 `AR-0`/`AR-1`）。

最终退出门：

- 空数据库可应用全部 migration；已有数据库可从 baseline 升级。
- 应用启动不再执行 schema 修改。
- 配置缺失在启动阶段给出确定错误。
- 所有文件和 Redis 操作通过共享 platform API。
- 进程重启、重复投递和 worker 崩溃不会丢失 job 状态或留下未解释的 outbox。

相对工作量：L。

## R3 用户与认证收敛

目标：把用户、认证、角色和头像迁入 FastAPI，同时保留可证明的增量同步和 restore-forward 兼容期。

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
2. 建立 snapshot、change capture 和 watermark，离线导入用户并比对数量、UUID、状态、hash、权限和审计。
3. 在测试环境用旧 token、新 token、注销、锁定、改密、refresh、Redis 丢失和 key rotation 场景交叉验证。
4. 先 shadow read，再执行写入栅栏、请求 drain 和 watermark barrier；前端代理按 canary 切到 FastAPI。
5. 观察期内明确唯一写入者、冲突合并和增量重放顺序；不以“只切代理”作为回滚证明。
6. 完成 restore-forward、备份恢复和 token/session 兼容演练后，才停止 Django 签发并下线进程。

回滚：保留迁移前 snapshot、增量日志和旧只读入口；回滚先重放切换后的确认写入，再按差异阈值执行 restore-forward 或经演练的 quiesce 回切，不反向覆盖新权威库。

退出门：

- 用户数量和身份字段迁移一致。
- 旧密码可登录并升级 hash，或有明确重置流程。
- 注销、锁定、改密和 refresh 在单一服务内一致生效。
- 前端不再依赖 Django 进程。

相对工作量：XL。

## R4 后端功能域模块化

目标：在 AR-0 至 AR-4 的可靠性、事务、任务、存储和投影合同完成后，按业务能力重组 FastAPI，消除 router、service、全局 init manager 和存储实现之间的隐式耦合。

状态：产品模块化尚未开始；本节不得被解释为可以绕过 AR-4 先移动 knowledge、notes 或 chat。模块迁移对应架构阶段 `AR-5`，这里保留 R4 追踪标签。

迁移顺序：

1. `skills/tools/mcp`：当前最高优先级域；统一标准 package、catalog、版本、安装、权限、配置、审计和隔离执行，并删除私有内置 Skill runtime。
2. `notes` 与 `memory`：在 Skill 首域门通过后复用模块模板。
3. `chat` 与 sessions：统一消息、摘要和 regenerate transaction。
4. `models`：统一系统配置、用户配置、加密和 provider adapter。
5. `knowledge`：只能在 `AR-4` canonical Storage、projection manifest 和 durable job 合同通过后迁移复杂的文件、数据库和向量状态。

每个模块包含：

- router 只负责 HTTP 解析、依赖和响应。
- schema 定义模块输入输出，不复用 ORM model 作为 API 类型。
- service/use case 定义 transaction 和权限边界。
- query/repository 只在能隔离复杂持久化时引入。
- adapter 负责 MySQL、Chroma、文件或第三方 SDK。
- tests 覆盖正常、越权、冲突、部分失败和重试。

Skill 首域还必须完成[标准 Skill 接入需求规格](./standard_skill_integration_requirements.md)的剩余 `SK-1` 至 `SK-5` 门禁。所有来源已经使用同一标准 validator/Storage/Registry/runtime，前端可生成标准可导出版本并增量编辑资源，`skill.yaml` loader、源码目录 CRUD 和旧运行文件也已删除并受静态测试保护；后续重点是 durable import、per-user scope、累计 token 预算、C runner/沙箱和真实环境验收。

知识库额外要求：

- MySQL source document 是状态主记录，包含 `queued/processing/ready/failed/deleting`。
- Chroma、MD5 和图片写入必须幂等，并有可重跑 reconciliation job。
- 不再把文本 MD5 文件作为唯一事实来源；迁移后由数据库唯一约束防重。
- 删除先标记状态，再执行向量/文件清理，失败可重试而不丢主记录。

退出门：模块间只能通过公开 service/schema 或 event 合同调用；不得跨模块直接查询私有表或拼接私有文件路径；跨模块调用必须遵守 UoW、job、权限和资源预算合同。

相对工作量：XL。

## R5 Agent、RAG 与异步投影

目标：保留已验证 Agent 核心，收敛模型/工具 adapter、运行状态、取消和长任务执行；可靠任务底座属于 `AR-1`，Storage/Vector 投影属于 `AR-4`，不得等产品工作包 8 解锁。

### Agent runtime

- 保留 `prepare_agent_run`、event pump、SSE driver 和 GuardedTool 的现有测试合同。
- 把模型、retriever、Tool registry、pending action 和 session store 定义为显式 ports。
- 使用 request-scoped run context，减少可变全局 `init_manager`。
- 持久化 run 状态、停止原因、模型、Skill/Tool 摘要和耗时。
- 每次 Run 固定标准 Skill version、digest、registry revision 和 effective grants；正文/资源渐进加载，无信号不得回退全部 Skill。
- 客户端断开时传播 cancellation 到模型、retriever 和 MCP 调用。
- run/job/event 使用可关联 ID；事件持久化后才能通过 SSE replay 或 polling 返回。

### RAG

- 上传、解析、切片、Embedding、写索引和发布状态拆成可重试步骤。
- 统一用户 Embedding/Reranker 配置的解析和实例缓存失效。
- 文件解析设置页数、解压后大小、图片数、总像素和处理时间预算。
- 将视觉模型和本地 reranker 的重资源初始化从 API startup 解耦。
- API 与 worker 使用独立资源池；Embedding、解析和重建任务有全局/用户级并发上限、磁盘配额和 admission control。

### 异步队列决策

AR-1 先落地最小 durable job runner（可用 MySQL polling），再通过 ADR 决定是否替换为专用队列。无论实现选型，都必须支持幂等 key、原子 claim、lease/heartbeat、fencing token、重试退避、超时、取消、进度、DLQ、重启恢复和背压。Skill validation/runner 是首个正式 conformance workload；package 只读挂载，脚本在独立进程限制 CPU/内存/PID/磁盘/输出/网络/secret，并能终止进程树。旧的 thread、`asyncio.create_task` 和进程内队列只能作为迁移兼容层，不能继续承载权威任务状态。

退出门：

- Agent 现有 117 个 offline regression case 不回退。
- 重复上传/重试不会产生重复向量或孤立文件。
- API 进程不因模型初始化或大文档处理失去 readiness。
- 客户端取消和 worker 失败有确定状态。
- 进程 kill、网络中断、重复投递和旧版本 worker 不能覆盖新 projection；索引落后和失败状态对用户可见。

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

1. `auth/shared foundation`：完成 token、401、权限动作和 OpenAPI client 基础。
2. `skills/tools/integrations`：优先交付标准 package 新建/导入/编辑/资源/设置/版本/权限/诊断/回滚/导出，删除内置 Skill 页面分支。
3. `chat`：拆出 message renderer、composer、catalog、settings、confirmation 和 history。
4. `knowledge`：拆出 upload job、document list/detail、Embedding 和 Reranker settings。
5. `notes`：拆出 editor、autocomplete、AI assist、related、template 和 batch actions。
6. `profile/memory/models/translate/sessions`：迁移剩余页面并清理旧 API 层。

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

标准 Skill 工作包 `11` 不在本产品迭代队列中；它是当前核心架构主线，必须先按 `SK-0` 至 `SK-5` 完成并通过 `SKILL-GATE`。

以下工作包 `7-10` 均为保留项，尚未执行。它们的产品 UI/API 在 `SKILL-GATE` 和 `ARCH-GATE` 通过前冻结。可靠性底座（AR-1 的 durable job、AR-4 的投影状态、SSE replay、readiness 和恢复工具）不属于产品工作包，必须提前实施并验收。具体工作包、依赖和验收条件见[改进执行计划](./improvement_execution_plan.md)：工作包 `7` 对应 F1/F2，`8` 对应 F3，`9` 对应 F4，`10` 对应 F5/F6。

| 顺序 | 功能 | 状态 | 用户价值 | 主要依赖 |
|------|------|------|----------|----------|
| F1 | 回答引用与来源抽屉 | 冻结，待 `ARCH-GATE` | 让知识库回答可核验并可返回原文 | `ARCH-GATE`、R0 安全渲染、R1 SSE/API 合同 |
| F2 | 回答一键沉淀为笔记或记忆 | 冻结，待 `ARCH-GATE` | 打通聊天、笔记、记忆，保留来源关系 | `ARCH-GATE`、R1 合同、R4 模块边界 |
| F3 | 知识处理任务中心 | UI/API 冻结；底层任务基础由 AR-1/AR-4 前置实施 | 提供持久进度、取消、失败诊断和重试 | `ARCH-GATE`、AR-1 durable job、AR-4 projection |
| F4 | 跨域统一搜索 | 冻结，待 `ARCH-GATE` | 统一检索笔记、记忆、会话和知识文档 | `ARCH-GATE`、AR-3/AR-4 数据边界和隔离测试 |
| F5 | Agent 运行记录 | 冻结，待 `ARCH-GATE` | 展示模型、Skill、Tool、耗时、错误和停止原因 | `ARCH-GATE`、R1 event schema、R5 run context |
| F6 | 版本化导出与恢复 | UI/API 冻结；恢复底座由 AR-0/AR-6 前置实施 | 让个人知识资产可迁移、可校验、可恢复 | `ARCH-GATE`、AR-3/AR-4、AR-6 恢复演练 |

`SKILL-GATE` 和 `ARCH-GATE` 均通过后，产品功能才按 F1、F2、F3、F4、F5、F6 推进。解锁后的第一批仍建议 F1/F2；F3 和 F4 还必须满足任务状态与统一数据边界的专项验收。

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

### 可观测、SLO 与故障门

- 为 HTTP、Agent run、Tool、MCP、RAG job 添加结构化 duration/status/error_type。
- 定义 process/core/auth/model/index/worker readiness 与 liveness；readiness 不触发昂贵模型调用，但必须反映后台初始化失败和可用降级能力。
- 记录数据库慢查询、Redis 命令/淘汰、outbox/队列积压、投影版本差异、外部调用超时和恢复耗时。
- 使用架构计划中的数值合同：普通 API p95/p99、SSE 首事件/重放、任务队列年龄、索引新鲜度、RPO/RTO、资源水位和 bundle 大小预算。
- 故障注入覆盖 MySQL failover/PITR、Redis 丢失/分区、Storage/Chroma 损坏、磁盘满、进程 kill、时钟偏移、模型/MCP 超时和重复投递；每项必须验证告警与数据一致性断言。

退出门：所有主分支 required checks 稳定通过；组合故障下 core API、认证、任务和索引均符合降级合同；实测 SLO/RPO/RTO 和告警阈值达到 AR-0 批准值。

相对工作量：L，贯穿 R0-R8。

## R8 切换、清理与部署

目标：在 canary、HA、恢复和观察期证据完成后删除兼容期代码，形成单一入口、分运行时和可恢复部署流程。

工作：

- 停止并移除 Django 代理路径、启动命令和运行依赖。
- 在数据备份和验收记录确认后归档或删除 `DjangoUserService/`；Git 历史保留实现。
- 删除旧 JWT、黑名单兼容、双配置、无效 `rag.yaml` 和未使用 Celery/数据库驱动。
- 删除已经迁移的旧 router/service/helper，不保留同名 v1/v2 无限并存。
- 提供一键本地启动、基础设施启动和 production deployment/runbook。
- 演练数据库故障转移/PITR、Redis 丢失、Storage/Chroma 重建、API/worker 版本回滚、SSE 连接 drain 和 restore-forward。
- 观察期保留旧镜像、旧路由、增量日志和快照；确认零请求、零积压和零未解释差异后再归档旧组件。
- 更新根 README、架构、API、环境变量和故障排除文档。

退出门：

- 浏览器和 FastAPI 主流程不需要 Django 进程。
- 干净环境可按文档完成 install、migrate、seed、start、test 和 rollback。
- 旧数据校验报告、迁移记录和回滚演练可追溯。
- [安全与可靠性加固计划](./security_hardening_plan.md) 的公网就绪条件全部满足，或 README 继续明确只支持本地使用。
- API 与 worker 资源隔离、canary 自动 abort、告警和恢复演练记录齐全。

相对工作量：M。

## 工作包与里程碑

| 里程碑 | 包含阶段 | 状态 | 对外结果 | 规模 |
|--------|----------|------|----------|------|
| A0 可靠性冻结 | AR-0 | 未执行 | SLO/RPO/RTO、故障矩阵、备份 manifest、readiness 和 P0 止血 | L |
| A1 运行时与任务平台 | AR-1 | 未执行 | API/worker 隔离、事务/UoW、durable job、SSE replay 和依赖故障合同 | XL |
| A2 身份收敛 | AR-2 | 未执行 | FastAPI 成为用户与认证唯一入口 | XL |
| A3 关系数据收敛 | AR-3 | 未执行 | 可 checkpoint、增量重放和 restore-forward 的权威 schema 迁移 | XL |
| A4 存储与索引投影 | AR-4 | 未执行 | canonical Storage、版本化 projection、对账和重建 | XL |
| A5 模块化重组 | AR-5 | 未执行 | 后端/前端功能域边界可测试 | XL |
| A6 灰度切换与 HA | AR-6 | 未执行 | canary、故障恢复、单一入口和旧运行时停用 | XL |
| S0-S5 标准 Skill 单轨 | SK-0 至 SK-5 | A 级与有限 B 级已形成；各阶段退出门未通过 | 标准 A/B/C package、可视化管理、隔离执行和旧内置能力退出 | XL |
| SG Skill 门禁 | SKILL-GATE | 未通过 | 标准 Skill 迁移、安全、恢复和跨平台证据齐全 | - |
| AG 架构解锁门 | ARCH-GATE | 未通过 | 在 SG 通过后解锁工作包 7-10 和后续非 P0 功能 | - |
| M0 安全可信基线 | R0 | 基础切片完成，egress 保留 | 已知文件、渲染、凭据和 token 高风险输入被阻断 | M |
| M1 合同冻结 | R1 | 部分完成 | API/SSE/认证合同已验证，数据清单与全路由特征测试待补 | M |
| M2 平台与任务可迁移 | R2 | 部分完成 | migration 与生产配置基础完成，durable job、storage/egress 和运行时隔离待补 | XL |
| M3 单一身份源 | R3 | 未执行 | FastAPI 承载用户认证，Django 可下线 | XL |
| M4 存储/投影稳定性 | R5 | 未执行 | Agent/RAG 可取消、可重试、可对账、可重建 | XL |
| M5 模块化后端 | R4 | 未执行 | 功能域边界和数据补偿明确 | XL |
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

基础工作包 `1-6` 已完成。标准 Skill 重构已经关闭显式 Tool/Skill ID 授权绕过，落地 CapabilityGrant、SkillRunBinding、资源编辑、OpenAPI、多实例 revision/outbox reconcile 和旧运行目录退出，但尚未完成任何阶段的完整退出门。下一步不是扩展产品功能，而是补齐 durable import worker、per-user scope、资源累计 token 预算和真实 MySQL/API/第三方 A/B 聊天 E2E，再实施 `SK-4` 独立 runner/沙箱并完成 `SK-5` 的恢复与跨平台证据。只有 `SKILL-GATE` 和 `ARCH-GATE` 都通过后，才可从[改进执行计划](./improvement_execution_plan.md)选择 `7-10`。每个 `AR-*`/`SK-*` 阶段必须在对应 `project_changes/<日期-主题>/` 建立 `plan.md`、`change-log.md` 和 `test-record.md`。
