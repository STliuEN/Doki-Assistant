# 架构重写计划

状态：复审修订后的计划，尚未执行

最近复核：2026-08-24（纳入标准 Skill 核心重构）

适用范围：`ai_document_assistant` 分支

本计划是继续增加普通产品功能、扩大业务边界和进行大规模性能优化前的强制前置计划。工作包 `1-6` 已完成，但不代表架构重写完成；工作包 `7-10` 在 `ARCH-GATE` 前冻结。工作包 `11`“标准兼容 Skill 单轨重构”是当前阶段必须执行的最高优先级核心修改，不属于冻结队列；它按 `SK-0` 至 `SK-5` 贯穿 AR 阶段并通过 `SKILL-GATE`，而 `SKILL-GATE` 是 `ARCH-GATE` 的组成条件。详细合同见[标准 Skill 接入需求规格](./standard_skill_integration_requirements.md)。

## 1. 目标与边界

### 1.1 重写目标

将当前 React + Django + FastAPI 的多进程开发系统，收敛为一个同源入口、一个 FastAPI 模块化业务单体和一个关系数据权威 schema，同时保留 API 与重任务运行时的故障隔离，以及 Redis、向量索引和文件存储各自适合的能力：

```text
Browser
  -> one same-origin entry
  -> API runtime (FastAPI modular monolith)
       -> one MySQL logical schema (authoritative relational data)
       -> Redis (cache and bounded runtime state)
       -> Storage adapter (immutable source objects)
       -> Vector adapter (versioned rebuildable projection)
  -> Worker runtime (same codebase, separate process/resource pool)
       -> durable outbox/job store
       -> bounded model/index resources
       -> isolated Skill validation/execution runner
```

“一个”指代码库、业务边界和关系数据写权威，不指一个进程或一个故障域。API、worker、数据库、缓存、Storage 和向量投影必须能分别限流、降级和恢复。

### 1.2 本次重写包含

- 用户、认证、角色和头像从 Django 迁入 FastAPI，保留用户 UUID 和兼容登录窗口。
- 两套 MySQL 的长期所有权收敛到一套版本化 migration 和一个关系数据权威源。
- 明确 MySQL、Redis、Storage、Chroma 的数据所有权和故障语义。
- 以模块边界、ports/adapters、事务边界和持久 outbox/job 状态重组后端。
- 让前端通过单一同源 API 入口工作，保持现有 URL、JSON envelope 和 SSE `schema_version: "1.0"` 的兼容窗口。
- 建立带 generation manifest 的备份、恢复、对账、重建、切换和 restore-forward 回滚 runbook。
- 为 API、认证、异步任务、索引新鲜度和数据恢复建立可量化 SLO/RPO/RTO 及故障预算。
- 弃用内置 `skill.yaml` runtime，以标准 `SKILL.md` package、统一版本领域、可视化管理、capability grant 和隔离 runner 替换；旧 Skill 只做一次性迁移，不保留双 Registry。

### 1.3 明确不包含

- 不在重写期间新增工作包 `7-10` 的用户功能；标准 Skill 工作包 `11` 是明确的核心重构例外。
- 不把 Chroma 或 Redis 直接改造成关系数据主库。
- 不同时引入 Celery、消息总线、微服务和第二套向量后端。
- 不把“可选 worker”留到迁移后再决定；至少先落地一个可恢复的最小 durable job runner，队列产品化可后置。
- 不以目录数量、代码行数或“删除了一个进程”作为完成标准。
- 不在没有备份、dry-run、数量/摘要校验和恢复演练的情况下连接、迁移或删除现有 MySQL 数据。
- 不以“恢复一个旧备份”作为唯一回滚方案；切换后的已确认写入必须有增量重放路径。

## 2. 当前架构与目标差异

当前事实和依赖见 [当前架构](./project_develop.md)。核心差异如下：

| 维度 | 当前态 | 目标态 |
|------|--------|--------|
| API 入口 | Vite 按路径代理 Django 与 FastAPI | 一个同源入口，FastAPI 统一承载 API；API 与 worker 分离故障域 |
| 用户权威源 | Django MySQL `user_service` | 目标关系库中的 `users/auth_sessions/roles` |
| 业务权威源 | FastAPI MySQL `chat_history` | 同一关系库逻辑 schema，统一 Alembic |
| 用户关联 | 业务表多为字符串 `user_id`，无跨库 FK | 统一 UUID、FK/删除策略和审计字段 |
| 知识源 | MySQL Blob、Chroma、MD5 JSONL、图片目录多路写入 | 一个 canonical source + MySQL 状态 + Chroma projection |
| Redis | 撤销、认证缓存、普通缓存、限流、pending action 混用 | 认证持久事实在 MySQL；Redis 只作缓存/短期状态，按 namespace、容量和 ACL 隔离 |
| 异步任务 | 直接双写、临时 background task 和潜在 Celery 配置并存 | MySQL outbox/job + 独立 worker；具备 lease、fencing、重试、DLQ 和背压 |
| 配置 | 环境变量、YAML、本地 JSON 分散 | 部署只读配置与版本化业务配置分层管理 |
| Skill | `skill.yaml + SKILL.md` 源码目录、进程内 Registry、私有编辑 payload | 单一标准 package 模型；MySQL/Storage 权威、可视化管理、Registry snapshot 和隔离 worker |
| 故障恢复 | 各存储分别恢复，缺少统一对账和重建门 | generation manifest、PITR/增量日志、可续跑迁移、重建和 restore-forward 回滚 |

## 3. 数据权威矩阵

重写期间每类数据只能有一个写入权威。派生数据可以丢失，但必须能从权威数据重建；所有跨存储发布都必须有版本和对账记录。

| 数据类别 | 权威来源 | 派生/缓存 | 失败策略 |
|----------|----------|------------|----------|
| 用户、密码、状态、角色、token version | MySQL `users` 等表 | Redis token/cache | MySQL 写入失败即失败，不用缓存兜底写入 |
| 会话、消息、笔记、记忆、模型配置 | MySQL 业务表 | Redis 查询缓存、Chroma 笔记向量 | 事务提交后异步投影，投影失败可重试 |
| 上传源文件 | 选定的 Storage canonical object（过渡期可保留 Blob 兼容列） | MySQL 元数据、解析图片、Chroma chunks | 源文件写入和校验成功后才发布状态 |
| 文档状态与索引版本 | MySQL 文档/索引任务表 | Chroma collection | 状态机 + 幂等 job + reconciliation |
| 会话、撤销、token version、注销审计 | MySQL `auth_sessions`/`revocations`/`users` | Redis 指定 namespace 作为加速缓存 | MySQL 是权威；Redis 丢失后按认证状态合同恢复，不因缓存缺失放行 |
| 限流、pending action、短期锁 | Redis 指定 namespace | 无永久副本 | 明确 fail-open/closed；丢失只影响短期状态，不改变业务事实 |
| MD5 去重 | MySQL 唯一约束 `(user_id, md5)` | 旧 JSONL 仅迁移期只读 | 校验完成后停止写入并归档 |
| 头像、提取图片 | Storage object key | MySQL URL/hash/size/status | 对象缺失可诊断、可重新生成或重新上传 |
| Reranker、路由校准、MCP 可写配置 | 版本化配置表，或明确只读部署配置 | 本地缓存 | 禁止多实例各自写本地 JSON 作为事实 |
| Skill 身份、版本、安装、policy、grant 和审计 | MySQL 统一 Skill 领域表 | Redis Registry revision/catalog cache、可重建路由向量 | MySQL 写入与 outbox 同事务；单 package 失败隔离并保留上一健康版本 |
| Skill 原始 package、正文、资源和 lockfile | Storage immutable object | worker staging/临时工作区 | checksum 与 atomic finalize 成功后才激活；不写源码目录 |

## 4. 可靠性合同（AR-0 必须定稿）

以下是执行前的初始门槛。AR-0 可以基于真实容量调整数值，但必须留下批准的数值；没有数值不能通过 `ARCH-GATE`。

| 领域 | 初始验收目标 | 统计/恢复边界 |
|------|--------------|----------------|
| 核心 API | 月可用性 ≥ 99.5%；普通 API p95 ≤ 500 ms、p99 ≤ 1.5 s | 不含模型生成、文件上传和维护窗口；按实例与依赖分别计量 |
| SSE/Agent | 接受请求后首个事件 ≤ 2 s；断线后 30 s 内可重放或转轮询 | 事件必须有 `event_id`、`run_id` 和序号；不可承诺 exactly-once |
| 异步任务 | 提交确认 ≤ 1 s；队列年龄 p95 ≤ 60 s；失败任务可在 5 min 内重新领取 | 以持久 job 状态为准，进程重启不能丢状态 |
| 索引新鲜度 | 正常负载下 source commit 到可查询 projection p95 ≤ 5 min | projection 落后可见、可对账、可重建 |
| 权威数据 | MySQL/Storage RPO ≤ 5 min；认证撤销和审计 RPO ≤ 1 min | 以同一 generation manifest、binlog/PITR 水位和对象版本证明 |
| 恢复 | 核心 API RTO ≤ 15 min；worker/index RTO ≤ 30 min | 必须在隔离环境实测，不以文档声称代替 |
| 备份 | 至少保留 7 个日备份、4 个周备份，并定期做恢复抽样 | 备份必须可读、带 checksum 和 generation manifest |

### 4.1 故障域和依赖合同

AR-0 输出每个依赖的 `timeout / retry（仅幂等）/ backoff / circuit breaker / bulkhead / fallback / readiness effect / error code` 矩阵。至少覆盖 MySQL、Redis、Storage、Chroma、模型、Ollama、MCP、API、worker 和 Skill runner。API 不得因模型加载、Embedding、大文档处理或第三方 Skill 耗尽连接池；worker 必须有全局和用户级并发上限、队列上限、磁盘配额和明确拒绝策略。

### 4.2 文档事实源

本文件是 AR 阶段、依赖顺序、ARCH-GATE 和可靠性门槛的唯一事实源。`roadmap_next.md` 只保留目标态和 R0-R8 映射；`improvement_execution_plan.md` 只保留工作包状态和入口链接。若状态冲突，以本文件为准。

## 5. 分阶段重写

依赖关系固定为：

```text
AR-0 reliability contract and P0 containment
  + SK-0 Skill contract, threat model and baseline
  -> AR-1 runtime isolation and durable jobs + SK-1 parser/domain skeleton
  -> AR-2 identity consolidation
  -> AR-3 recoverable relational migration
  -> AR-4 canonical storage and index projection + SK-2 package lifecycle/UI
  -> AR-5 starts with skills/tools/mcp + SK-3 A/B runtime and migration
  -> SK-4 executable runner
  -> AR-6 canary cutover, HA and decommission + SK-5 legacy removal
  -> SKILL-GATE
  -> ARCH-GATE
  -> unlock 7-10 and new product work
```

每个阶段必须先完成入口条件，再提交对应 `project_changes/<日期-主题>/` 三件套。阶段之间允许短暂兼容，但不得无限期双写或保留同名 v1/v2 实现。Skill 所需 AR 基础尚未完成时优先补齐基础；基础可用后，`SK-*` 是第一个落地和验收的业务工作，不得改做 `7-10`。

### AR-0：可靠性契约、盘点与 P0 止血

**目标**：在任何迁移前把“可恢复”变成可测量合同，并先消除会放大数据损失或故障域的现有行为。

**入口条件**：负责人批准功能冻结；`1-6` 基线和文档索引可重复运行；确认本阶段不做生产业务写入。

**范围**：

- 定稿本文件 4 节的 SLO、RPO、RTO、备份保留、错误预算和容量假设；为每项指标指定采集方式、阈值、告警和负责人。
- 盘点两个 MySQL 的 schema、孤儿数据、敏感字段、连接池、备份/PITR/binlog 能力；生成带时间点的 snapshot manifest。
- 盘点 Redis namespace、TTL、容量/淘汰策略、认证与普通缓存隔离、丢失后的安全语义。
- 盘点 Storage、Chroma collection、embedding 版本、MD5 JSONL、提取图片和所有写入者；生成 source-to-projection inventory。
- 建立真实 MySQL/Redis/Storage/Chroma 的隔离集成环境，以及 kill、重启、网络超时、磁盘满和依赖不可用的可重复故障矩阵。
- 把 `/health/live`、`/health/ready` 拆成 process、core、auth、model、index、worker 状态；后台初始化失败不得继续报告完整 ready。
- 立即禁止 Chroma 初始化失败时递归删除持久目录；改为 quarantine/只读降级，保留快照并记录人工恢复任务。
- 为认证、聊天、笔记、知识上传/删除、跨用户访问、任务重启和 SSE 断线建立 characterization tests。
- 同步执行 `SK-0`：定稿标准 `SKILL.md` 格式 ADR、A/B/C 兼容矩阵、package 威胁模型、资源上限和 capability 合同；对现有 Skill 目录做只读 checksum inventory，并冻结现有 API/UI/Prompt/路由 characterization tests。

**非目标**：不切换请求入口，不迁移生产数据，不删除任何现有数据库、文件或索引。

**产物**：可靠性合同、容量模型、依赖故障矩阵、generation manifest 规范、只读盘点报告、分层 readiness 合同、P0 止血记录、`SK-0` 格式/威胁/兼容/迁移基线和恢复 runbook。

**验证与退出门**：每个 SLO/RPO/RTO 有数值和证据来源；备份可读、checksum 可验、随机抽样一致；至少一次隔离恢复和一次故障矩阵演练达标；Chroma 不再有默认破坏性 reset；基线测试无回退；`SK-0` 全部产物评审通过。未完成 `SK-0` 不得进入 AR-1。

**回滚点**：本阶段只产生报告、测试和止血保护；若任一 P0 或恢复证据缺失，停留在 AR-0。

### AR-1：运行时隔离、持久任务与共享合同

**目标**：在迁移任何业务数据前建立可恢复的 API/worker 平台和一致的事务、任务、事件、存储合同。

**入口条件**：AR-0 的 SLO、故障矩阵、备份 manifest、readiness 合同和 P0 止血已评审并通过。

**范围**：

- 同一代码库提供独立 API runtime 与 worker runtime；分别设置进程、连接池、内存、CPU、模型和并发上限，worker 崩溃不能拖垮 API。
- 落地最小 durable job runner（可先用 MySQL polling，不等待队列产品选型）：业务事实与 outbox 在同一事务写入；job 支持 `queued/leased/running/succeeded/failed/cancelled/dead_letter`、lease/heartbeat、过期回收、fencing token、幂等键、指数退避、DLQ 和人工重放审计。
- 明确全局/用户级配额、队列最大长度、admission control、磁盘/模型资源配额和背压拒绝合同；禁止按请求无限创建线程或后台 task。
- 统一 Settings/profile、启动校验、request/run/job/event correlation ID、结构化日志、错误模型和 telemetry schema。
- 统一 transaction helper/UoW：只有 application/use-case 层可以 commit；repository/router 不得 commit；outbox 必须与业务事实同一事务；用静态检查和失败测试强制。
- 统一 Redis namespace、ACL、TTL、连接超时和 fail-open/closed；认证会话/撤销的持久事实不得只在 Redis。
- 定义 Storage port（不可变对象键、checksum、大小、atomic finalize、版本、删除延迟和 quota）及 Vector port（版本、manifest、upsert/delete/rebuild、fencing）。
- SSE 事件加入单调 `event_id`、`run_id`、序号和 cursor；支持 `Last-Event-ID` 重放或 polling fallback，断线不改变 job 的持久状态。
- 为 MySQL、Redis、Storage、模型、Ollama、MCP 和 Chroma 实现统一 timeout/retry/circuit breaker/bulkhead/fallback 矩阵。
- 启动 `SK-1`：实现标准 `SKILL.md` 结构化 parser/validator、统一 Skill 领域骨架、不可变 Registry snapshot 接口和 capability enforcement；Skill 验证/执行成为首个 durable job 隔离 workload。
- Skill runner 必须使用独立进程/资源池，package 只读挂载；CPU、内存、PID、磁盘、输出、网络、secret、取消和进程树终止均纳入平台合同。API 不得 import 或直接执行 package 代码。

**非目标**：不切换用户或业务数据权威，不删除旧实现，不开发任务中心 UI；但可靠性底座必须可运行并可恢复。

**产物**：API/worker 启动与资源清单、durable job runner、Skill parser/domain skeleton、受限 runner 接口、UoW/事务规范、Storage/Vector ports、SSE replay 合同、Registry revision/capability 合同、依赖策略表、指标与告警定义、静态依赖检查。

**验证与退出门**：进程 kill/restart 后 job 可续跑且不重复发布；租约过期可回收；重复投递、毒任务、取消和背压有确定结果；API 在 worker/模型/Skill runner 不可用时仍满足 core readiness；事务回滚不会留下孤儿 outbox；SSE 可重放或转轮询；标准 parser fixtures 和 runner 强制终止测试通过。

**回滚点**：旧路由通过兼容 adapter 运行；只回滚平台 adapter 和 worker，不回滚数据；任何未证明的双写必须关闭。

### AR-2：用户与认证收敛

**目标**：移除 FastAPI 对 Django 用户状态 HTTP 校验的运行时依赖，同时保证切换和恢复期间认证写入不丢失。

**入口条件**：AR-1 的 auth、UoW、durable job、Redis、SSE 和故障合同通过；用户 dry-run、CDC/change log 和 token 兼容测试准备完成。

**范围**：

- 在 FastAPI 建立 `users`、`auth_sessions/refresh_tokens`、`revocations`、`roles/user_roles`、`audit_events`；Redis 仅作缓存，不作为撤销唯一副本。
- 采用非对称签名、`kid`/JWKS、issuer/audience 信任边界和分阶段 key rotation；旧 token 只在兼容窗口验证，新服务不使用共享 HS256 secret 无限期互签。
- 离线导入 Django 用户 UUID、资料、状态、token version 和密码 hash；保留 PBKDF2 verifier，首次成功登录再升级 hash。
- 迁移前建立 snapshot 和 change capture；双读对账后执行写入栅栏、请求 drain 和 watermark barrier。注册、改密、锁定、注销、角色和 refresh 的来源、顺序、冲突合并及幂等键必须明确。
- 兼容现有 `/user/*`、`/file/*` 路径和响应 envelope；SSE/前端视觉不变，但 token/session 状态合同必须更新并可观测。
- 切换期间只承诺 restore-forward；若需回切旧入口，必须先重放切换后的增量写入并通过差异阈值，禁止“只切代理”冒充零数据丢失回滚。
- 同步建立 Skill 管理员、安全管理员、scope、actor 和持久审计权限；详情 API 返回 `allowed_actions`，前端不得以按钮隐藏替代服务端授权。

**非目标**：不在同一发布中迁移全部业务表，不删除 Django 备份或兼容验证器。

**产物**：dry-run/apply/verify 迁移脚本、change log、token/JWKS 迁移说明、cutover barrier runbook、冲突报告、restore-forward 回滚演练。

**验证与退出门**：数量、UUID、状态、hash、权限和审计逐项一致；旧密码可登录或明确重置；token、refresh、注销、锁定和改密在 Redis 丢失时符合合同；切换中断可续跑，已确认写入可增量重放；业务不再调用 Django `/user/detail/`。

**回滚点**：保留旧库只读和增量日志；回滚只能走 restore-forward 或 quiesce 后验证过的入口切换，不反向覆盖新权威库。

### AR-3：可恢复的关系数据收敛

**目标**：把用户和业务数据纳入一个长期关系数据权威 schema，同时让迁移可中断、续跑、对账和恢复。

**入口条件**：AR-2 认证观察期通过；新入口单写策略、写入栅栏、增量捕获、恢复开关和空库 migration 已演练。

**范围**：

- 先定义 schema inventory、UUID 类型、每个父子域的 `RESTRICT/soft-delete/tombstone/purge` 策略；默认不使用隐式级联删除。
- 按 `snapshot -> checkpointed chunk copy -> delta/change replay -> reconciliation -> quiesce/cutover -> observation -> contract` 执行；每个 chunk 有 checkpoint、校验摘要、限速和幂等重放。
- 明确 tombstone、删除期间并发写、冲突合并、差异阈值和自动 abort；大表按主键范围分块，迁移可暂停后续跑。
- 使用 expand/backfill/contract 和 N/N-1 schema compatibility；禁止依赖生产 downgrade。保留 binlog/PITR 水位和旧代码可读窗口。
- 将字符串 `user_id` 统一为 UUID，分批补齐 NOT NULL、唯一约束、索引和 FK；生成孤儿扫描和修复报告。
- 将 `Skill/SkillAlias/SkillVersion/SkillInstallation/SkillPolicy/CapabilityGrant/SkillImport/SkillRunBinding` 纳入统一 schema、UoW、审计和 N/N-1 兼容规则；禁止以本地 JSON、YAML 或独立数据库作为临时权威。

**非目标**：不把向量、缓存或大文件塞进关系库，不在未完成差异修复前删除旧库或旧日志。

**产物**：checkpointed migration、delta replay、schema compatibility matrix、差异/孤儿报告、删除治理、容量评估、恢复 manifest 和 abort/runbook。

**验证与退出门**：全量计数、摘要、主键、随机业务样本、用户隔离和审计一致；迁移中断可续跑，重复 replay 幂等；差异超过阈值自动停止；从空库和 snapshot 均可恢复并满足 AR-0 RPO/RTO。

**回滚点**：切换前保留原库只读、snapshot 和增量日志；切换后只允许 restore-forward 或经过演练的 quiesce 回切，不执行生产 downgrade 或破坏性反向双写。

### AR-4：canonical Storage 与索引投影

**目标**：先解决源文件、元数据和向量投影的事实边界，再让任何业务模块依赖它们。

**入口条件**：AR-1 的 Storage/Vector/job 合同和 AR-3 的关系 schema、manifest、删除治理已落地；canonical source 已由 ADR 决策。

**范围**：

- 选择一个 Storage canonical source（对象存储或受控持久卷）；定义 immutable object key/version、checksum、fsync/atomic finalize、quota、保留期、orphan GC 和跨存储备份 manifest。Blob 只保留兼容读取，不允许双写权威。
- Storage 对象先以不可见 staged key 写入并校验；MySQL 保存文档元数据、对象键、checksum、状态、chunk/index version、tombstone 和 job manifest，发布该对象版本的 source manifest 与 outbox 在同一数据库事务提交。失败的 staged object 由可审计 GC 回收，不引入跨存储分布式事务。
- 上传、解析、切片、Embedding、索引发布和删除使用可重试状态机；每次投影携带 source version 和 fencing token，旧 worker 不能覆盖新版本。
- Chroma 仅作 projection；采用 staged/versioned index、manifest 校验和 atomic pointer swap；损坏时 quarantine/只读降级，从 MySQL+Storage 重建，保留 N 个快照并受控 GC。
- 笔记、知识和图片统一由单一 Vector/Storage adapter 管理；静态检查禁止业务 service 直接导入 Chroma 或拼接私有路径。
- 提供按文档、用户和全库的 reconciliation/rebuild，定义 tombstone 保留到投影确认的规则。
- Skill package 是 canonical Storage 的首个业务 consumer：同步执行 `SK-2`，将原始 ZIP、规范化 package、`SKILL.md`、资源和 lockfile 纳入 staging、checksum、atomic finalize、quota、保留和 GC；先证明其生命周期，再迁移复杂 knowledge。
- `SK-2` 同时交付 draft/import/validate/publish/export、版本 diff/回滚和统一可视化管理；所有保存结果必须可重新导入为标准 package，且任何 UI 操作不得写入 Git 工作树。

**非目标**：不在重建验证前删除 Blob、MD5、图片或旧 collection，不同时维护多个向量后端。

**产物**：Storage/Vector adapter、Skill package Storage/lifecycle、标准可视化管理基础、对象与索引 ADR、状态机、projection manifest、重建/对账/GC 工具、跨存储备份和故障记录。

**验证与退出门**：重复上传、重试、删除和乱序投递不产生不可解释的重复/孤立数据；staged object 与 source manifest 的发布/回收状态可对账；任一投影损坏可恢复；旧版本 worker 被 fencing；跨存储恢复后抽样和 checksum 一致；标准 Skill 新建/编辑/导出可重导入且不产生源码/Git 写入。未完成 `SK-2` 不得迁移 knowledge。

**回滚点**：保留旧检索 adapter、源对象和索引快照；切换回旧 projection 不覆盖新的权威源。

### AR-5：业务域模块化

**目标**：在认证、事务、任务、Storage 和投影可靠性基础完成后，逐域重组 FastAPI 与前端，降低跨域隐式耦合。

**入口条件**：AR-2 至 AR-4 的数据对账、任务恢复、存储 manifest、权限和审计门禁全部通过；待迁移模块已有外部合同和性能基线。

**后端顺序**：`skills/tools/mcp` -> `notes/memory` -> `chat/sessions` -> `models` -> `knowledge`。标准 Skill 是 AR-5 第一个业务域；复杂 knowledge 只能在 AR-4 投影合同完成后移动。

**每个后端模块必须具备**：router、schema、service/use case、query/repository（仅必要时）、adapter、权限测试、部分失败和重试测试。模块不得直接查询其他模块私有表或拼接私有文件路径。

**前端顺序**：`auth/shared foundation` -> `skills/tools/integrations` -> `chat` -> `knowledge` -> `notes` -> `profile/memory/models/translate/sessions`。页面只组合功能；API、服务端状态、SSE 状态和 token 处理放在可测试的 feature/shared 层。

**Skill 首域要求**：同步执行 `SK-3`，实现 A 级 Prompt 与 B 级 Resources 渐进加载、Tool/MCP capability、一次性旧 Skill 幂等迁移和新旧 catalog/Prompt/路由影子对比。前端必须提供标准 package 新建、导入、完整指令编辑、资源管理、配置、版本、权限、诊断、回滚和导出，不得保留“内置 Skill”分支。

**非目标**：不为形式上的目录重排引入微服务；不重做无关视觉；工作包 `7-10` 的任务中心、知识导出等产品 UI 仍冻结。标准 Skill 可视化管理是核心迁移范围，不属于冻结项。

**产物**：模块依赖图、公开 service contracts、标准 Skill A/B 运行时和可视化管理、一次性迁移器与影子对比报告、前端同源 API client、迁移测试边界和删除清单。

**验证与退出门**：跨模块静态检查通过；正常、越权、冲突、部分失败、取消和重试测试通过；OpenAPI/SSE 合同无非预期变化；性能和资源预算不超过 AR-0 基线；`SK-3` 的 A/B、迁移对账、可视化管理和无 Git 写入门全部通过后，才迁移下一个业务域。

**回滚点**：每次只迁移一个纵向域，保留可切换 adapter；发现行为回退时只回滚该域，不回滚已完成的权威数据迁移。

### SK-4：标准 Skill C 级隔离执行

**目标**：在 API/worker、package、权限和 A/B 运行合同稳定后，交付 Node/Python 标准 Skill 的可执行兼容能力。

**入口条件**：AR-1 runner 的 lease/fencing/取消/资源隔离通过；AR-2 权限审计、AR-4 package Storage 和 SK-3 A/B 运行通过。

**范围**：按 package digest 构建锁定环境；批准 `RuntimeBinding`；只读挂载 package；限制 wall time、CPU、内存、PID/进程树、磁盘、输出、网络和 secret；默认断网；以 argv 调用批准的脚本/package command；提供 smoke test、取消、强制终止和产物 manifest。

**非目标**：不提供任意 shell，不在 API 进程执行脚本，不因本机已有 npm/Node 绕过隔离和授权，不自动信任 package 生命周期脚本。

**产物**：Node/Python runner、锁定依赖构建、RuntimeBinding/capability enforcement、smoke test、执行审计和管理员诊断界面。

**验证与退出门**：真实 Node/npm 标准 package 完成导入、构建、执行、产物校验、取消、超时和回滚；无限循环、内存耗尽、派生进程、超量输出和网络越权均被终止或拒绝，API 保持 ready。

**回滚点**：C 级 capability 可独立关闭；A/B Skill 和上一健康 package 版本继续可用；构建环境按 digest 隔离并可受控 GC。

### AR-6：灰度切换、高可用与停用旧运行时

**目标**：在经过 canary、故障演练和恢复证明后形成单一入口、可恢复部署和受控旧系统停用。

**入口条件**：AR-2 至 AR-5 的迁移/对账/重建报告齐全；AR-0 SLO/RPO/RTO 达标；API/worker、数据库、Redis、Storage 和 Chroma 的故障演练通过。

**范围**：

- 生产拓扑至少明确 API 多实例或本地单实例限制；MySQL primary/replica、PITR/binlog、Redis 持久化/隔离、Storage 耐久性和 worker 扩缩容策略必须有运行手册。
- 反向代理支持双 upstream、按租户/比例 canary、自动 abort 条件、连接 drain、SSE 长连接迁移和限流；旧入口保留至观察期结束。
- 先影子读和只读流量，再切换写流量；切换期间监控错误率、数据差异、outbox lag、索引新鲜度和资源水位。
- 演练进程 kill、数据库故障转移、Redis 丢失/淘汰、网络分区、磁盘满、模型/MCP 超时、时钟偏移和重复投递；验证数据一致性断言和告警触发。
- 同步执行 `SK-5`：演练 Skill package 激活/回滚、多实例 revision 收敛、runner kill、Storage 损坏、权限撤销和旧版本 fencing；完成 canary 后删除运行时 Legacy loader、旧文件 CRUD、硬编码 Skill 路由和源码目录写入。
- 观察期内禁止删除旧镜像、旧 schema、旧对象和旧日志；确认零请求、零积压、零未解释差异后，再归档并保留可回装 artifact。
- 更新 README、开发说明、环境变量、API、故障排除和运维 runbook。

**非目标**：不在清理阶段开发 `7-10` 或重做无关 UI；SK-5 的 Skill 切换和旧能力退出属于本阶段必做范围。

**产物**：canary/rollback runbook、HA/备份配置、故障演练报告、发布清单、旧组件归档和最终架构说明。

**验证与退出门**：干净环境可 install/migrate/start/test/rollback；浏览器主流程不需要 Django；canary 自动 abort 和 restore-forward 可执行；实测 RPO/RTO、SLO、告警和资源预算达标；旧组件无运行时引用后才允许停用；`SK-5` 完成且运行时不再读取 `skill.yaml` 或源码 Skill 目录。

**回滚点**：观察期内保留旧镜像、旧路由、只读快照、增量日志和索引快照；回滚优先 restore-forward，禁止破坏性反向双写。

### SKILL-GATE（ARCH-GATE 前置）

标准 Skill 单轨重构必须在总架构门禁前独立验收。最低条件：

- `SK-0` 至 `SK-5` 的 plan、change log、test record 和回滚证据齐全。
- 所有 active Skill 都来自通过统一 validator 的标准 package；前端新建/编辑/导出 package 可重新导入且无损。
- A 级纯指令、B 级资源和 C 级 Node/Python 代表性 package 全部通过兼容、安全和故障测试。
- 当前 Skill 的 alias、Tool binding、默认选择和批准的路由行为完成迁移对账；差异有明确批准。
- 运行链路不存在 `skill.yaml` loader、源码目录写入、双 Registry、API 进程 package import 或硬编码业务 Skill 路由。
- package、版本、安装、policy、grant、Run binding 和审计以 MySQL/Storage 为权威；Redis 丢失可恢复。
- 多实例 revision、更新失败保留旧版本、回滚、worker kill、资源越权、取消/超时和跨平台测试通过。
- 管理前端覆盖新建、导入、编辑、配置、验证、启停、版本、授权、诊断、回滚、导出和卸载；任何操作不污染 Git 工作树。

任一条件失败都停留在对应 `SK-*` 工作包；不得通过 `ARCH-GATE`，也不得转而实施 `7-10`。

## 6. ARCH-GATE 解锁条件

只有以下条件全部满足，才允许开始工作包 `7-10` 或批准新的非 P0 功能：

- `AR-0` 至 `AR-6` 的产物、变更记录和测试记录齐全。
- `SKILL-GATE` 已通过；标准 Skill 是单轨权威，旧内置 Skill runtime 已退出。
- API 与 worker 是独立故障域；worker、模型或 Chroma 不可用时 core API 仍按 readiness/降级合同运行。
- 可靠性合同中的 SLO、RPO、RTO、队列、索引新鲜度和容量阈值均有实测证据，错误预算和告警已接通。
- 用户和业务关系数据只有一个写权威；snapshot、增量捕获、checkpoint、差异阈值和 restore-forward 回滚可验证。
- 认证会话、撤销、token version 和审计有持久权威；Redis 丢失、淘汰或分区不会造成错误放行。
- Storage 是源文件唯一写权威；对象版本、checksum、atomic finalize 和跨存储 generation manifest 可验证。
- Chroma 只作版本化 projection；损坏、删除、乱序投递和旧 worker 覆盖均可隔离、重建和对账。
- durable job 支持幂等、lease/fencing、重试、DLQ、取消、背压和重启恢复；SSE 支持 event id 重放或 polling fallback。
- 关键 API、权限、删除、迁移、恢复、故障注入和资源隔离测试通过；性能不超过约定预算。
- 至少完成一次 MySQL/Redis/Storage/Chroma 跨存储恢复、一次应用/worker 回滚和一次组合故障演练。
- README、架构、开发运行、改进计划和故障排除文档已同步，旧运行方式明确标为过渡或已停用。

门禁未通过时，允许的变更仅限 P0 安全、数据完整性、服务启动和修复门禁所需的测试/文档；不得借机新增用户功能或扩大 API 合同。

### 6.1 阶段证据最低集

每个阶段的 `test-record.md` 至少包含以下证据；命令应使用当时锁定的依赖版本，并注明是否使用隔离替身：

| 阶段 | 最低验证证据 |
|------|--------------|
| AR-0 | SLO/RPO/RTO 与容量基线、只读盘点、generation manifest、备份恢复抽样、Chroma quarantine、依赖故障矩阵、分层 readiness、SK-0 格式/威胁/迁移基线 |
| AR-1 | API/worker 隔离、durable job kill/restart、lease/fencing/DLQ/backpressure、UoW rollback、依赖超时/熔断、SSE replay、Skill runner 强制终止、静态依赖检查 |
| AR-2 | snapshot/change capture、hash/权限/审计对账、key rotation、refresh/注销/锁定/重置、写入栅栏、增量重放和 restore-forward 演练 |
| AR-3 | checkpoint 分块迁移、delta replay、差异阈值 abort、空库/快照恢复、FK/唯一约束、孤儿/tombstone 扫描、N/N-1 schema 兼容 |
| AR-4 | Storage atomic finalize/checksum、Skill package lifecycle、跨存储 manifest、投影版本 fencing、重复/乱序 job、Chroma quarantine/rebuild、对账和 GC |
| AR-5 | Skill A/B/可视化管理/迁移对账、模块边界静态检查、后端 unit/API、前端 lint/typecheck/build/component、权限/部分失败/取消/重试、API/SSE 回归和资源预算 |
| SK-4 | Node/Python package 构建/执行、资源限制、进程树终止、网络/文件/secret 拒绝、真实 package E2E 和产物校验 |
| AR-6/SK-5 | canary/自动 abort、Skill revision/旧能力退出、连接 drain/SSE 迁移、MySQL failover/PITR、Redis 丢失、磁盘满、进程 kill、组合故障、restore-forward、旧依赖扫描 |

涉及真实 MySQL 的 AR-2/AR-3 迁移只能在完成备份、dry-run、审批和隔离恢复演练后执行；本计划本身不授权连接或修改当前环境数据库。

## 7. 与现有 R0-R8 的关系

`roadmap_next.md` 中的 R0-R8 继续作为安全、合同、模块和发布工作的追踪维度，但不再作为绕过架构重写门禁的并行路线：

| 架构重写 | 对应现有阶段 | 说明 |
|----------|--------------|------|
| AR-0 | R0/R1 | 安全冻结、合同和数据盘点 |
| AR-1 | R2 | 平台接口、migration 和共享基础 |
| AR-2 | R3 | 用户与认证收敛 |
| AR-3 | R2/R3/R8 | 关系库合并、约束和旧库停用 |
| AR-4 | R2/R5/R7 | Storage canonical、索引投影、任务状态、对账和故障门 |
| AR-5 | R4/R6 | 后端和前端功能域模块化（可靠性基础之后） |
| AR-6 | R7/R8 | HA、质量、恢复、灰度切换和清理 |
| SK-0 至 SK-5 | R0/R1/R2/R4/R5/R6/R7/R8 | 当前最高优先级核心域；格式、安全、平台、Storage、运行时、前端、质量和旧能力退出 |

现有 `1-6` 只代表基础切片已完成。工作包 `11` 必须随 AR 阶段优先执行并通过 `SKILL-GATE`；产品工作包 `7-10` 的依赖统一追加 `SKILL-GATE + ARCH-GATE`，不因任何基础切片部分完成而提前解锁。

## 8. 变更记录要求

架构重写真正开始实施时，每个 `AR-*` 和 `SK-*` 阶段必须在 `project_changes/<日期-主题>/` 创建：

- `plan.md`：目标、范围、非目标、入口条件、风险和回滚。
- `change-log.md`：实际代码、migration、配置和文档改动。
- `test-record.md`：命令、结果、数据校验、恢复演练和未覆盖风险。

本次仅更新计划文档和对应计划记录，不表示任何 `AR-*`/`SK-*` 阶段已经执行，也不连接或修改现有 MySQL。当前下一实施项是与 AR-0 同步的 `SK-0`。
