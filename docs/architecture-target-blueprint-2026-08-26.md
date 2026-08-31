# 2026-08-26 最终重构蓝图（执行交接版）

状态：`E0/S0`、`E1/AR-0/SK-0` 与 `E2/S1/AR-1` 已关闭。E2 关闭不代表 `SKILL-GATE`、`ARCH-GATE` 或任何发布门禁通过。

日期：2026-08-26  
适用分支：`ai_document_assistant`

本文把 q1-q92 的决策收敛为一份可执行蓝图。它描述最终目标、迁移顺序和验收边界，不把已有局部代码切片当作完成证据。具体执行顺序、停线规则、回滚和交接字段见[架构重构执行交接手册](./architecture-execution-handoff-2026-08-26.md)。与当前实现冲突时，以“当前现实”章节说明的过渡状态为准；与旧方案冲突时，以本文和[架构重写计划](./architecture_rewrite_plan.md)为准。

## 1. 已确认的边界

| 决策 | 固化结论 |
|---|---|
| 部署范围 | 仅单机、小范围局域网；不为公网、HA、多实例和高并发设计验收前置。 |
| 最终入口 | 一个 FastAPI 进程直接托管前端构建产物、HTTP/SSE、认证和全部业务模块。 |
| 最终业务库 | 同一个 MySQL 实例、同一个数据库；通过分表过渡，最终由 SQL 处理全部业务数据。 |
| 最终写权威 | FastAPI 是唯一业务写入口。Django、旧脚本和本地文件不得继续写业务事实。 |
| 任务执行 | SQL durable job 加内置 runner；默认并发固定为 1，支持 claim、lease、heartbeat、幂等、重试、取消、DLQ 和重启恢复。 |
| Redis | 仅迁移窗口和开发调试可保留；不参与登录、会话、refresh、撤销或业务正确性。过渡完成后删除。 |
| Django | 仅作临时登录/刷新适配和只读迁移观察层；FastAPI 认证切换稳定后删除运行链路。 |
| 文件系统 | 不再是业务权威。开发期可保留默认开启的本地 debug/import/export/rollback 通道；正式部署可关闭，且不会被业务请求自动 fallback。 |
| RAG | 保留 Chroma 原生向量检索以保证速度；SQL 不保存向量 BLOB，不承担向量检索。Chroma 只保存可重建的派生切片、metadata 和向量。 |
| RAG 故障 | Chroma 故障时从 SQL 原始文档重建；查询请求不同步重建，期间返回结构化 `degraded/503`，登录、会话等核心能力继续工作。 |
| RAG 配置 | 用户可声明式选择切片、检索参数和 embedding 模型；向量空间以 `index_kind + embedding_fingerprint + generation` 隔离。 |
| generation | 只允许短暂 `active + staging`；重建成功后删除旧 generation，不保留旧 generation。 |
| Skill | 兼容 Codex 风格根目录 `SKILL.md`，支持目录和 ZIP；SQL 保存原始包、规范化 manifest、资源清单和版本状态。未知字段原样保存但不解释、不授权。 |
| Skill 执行 | 本阶段只实现本地目录/ZIP 和 A/B 能力；`scripts/`、网络、secret、外部进程、MCP 只保留插口并返回结构化 `unsupported`。Git/URL/Registry 仅预留 adapter。 |
| 旧数据 | 保留核心用户、会话、聊天、笔记、原始知识、Skill 业务数据和必要映射；旧 Chroma、MD5 sidecar、旧 Skill 内部结构作为派生/遗留输入重建，不保留旧内部 generation。 |
| 发布纪律 | 架构收敛、恢复验收和核心回归关闭前，冻结所有新功能发布；用户保留最终架构决策权。 |

### q85-q92 确认记录

| 问题 | 已确认决定 |
|---|---|
| q85 | MySQL 最终承载用户、会话、聊天、笔记、原始知识、Skill、图片、MD5/摘要、job、审计和迁移映射；Chroma 只承载派生切片、metadata 和向量。 |
| q86 | 正式局域网部署由 FastAPI 直接托管前端构建产物，不依赖独立前端服务。 |
| q87 | 内置 runner 默认并发固定为 1；不以高并发、HA 或多实例作为本次目标。 |
| q88 | 先完成 FastAPI 认证 schema 和迁移 dry-run，再 shadow 校验并切换 login/refresh/revoke；Django 退为只读适配，稳定后删除。 |
| q89 | 会话、refresh 和撤销全部进入 MySQL；Redis 不参与正确性，过渡完成后移除。 |
| q90 | 保留核心业务数据；旧 Chroma、MD5 sidecar 和旧 Skill 内部结构丢弃并重建，不保留旧 generation。 |
| q91 | 阶段状态固定为 `草案 / 待你确认 / 实施中 / 待验证 / 已关闭 / 阻塞`。 |
| q92 | 架构收敛、恢复验收和核心回归关闭前，全部新功能发布冻结。 |

## 2. 当前现实与最终形态

### 2.1 当前现实（不等于目标）

当前仓库仍有 Django、FastAPI、Redis、文件目录、MD5 sidecar 和 Chroma 并存。用户认证主要由 Django 提供，部分 FastAPI 路径通过 Redis 和 Django 状态校验；知识源同时存在 SQL 原文、文件和 Chroma 派生状态；Skill 仍有提前实现的局部生命周期代码。P0 已完成 Chroma 失败隔离、Skill 发布止血、MCP YAML 权威冻结、离线备份工具和 E1 隔离依赖/恢复证据；用户已确认关闭 AR-0/SK-0，但尚未执行真实数据库 migration，也未通过后续架构或发布门禁。

### 2.2 最终拓扑

```text
局域网浏览器
    |
    v
一个 FastAPI 进程
    |- 静态前端、HTTP/SSE、认证、业务模块
    |- SQL job + 内置 runner（默认并发 1）
    |- RAG 抽象接口 -> Chroma adapter
    |- 本地模型/Embedding/Reranker provider
    v
一个 MySQL 实例 / 一个数据库
    |- users / sessions / revocations / roles / audit
    |- chats / messages / notes / knowledge_sources / skill_packages
    |- jobs / generations / migration_maps / debug_exports

Chroma 持久目录（派生投影，不是业务权威）
    |- chunks + metadata + vectors
    |- active/staging generation
```

开发期的本地 debug/import/export/rollback 通道以虚线理解：它只读写明确的操作文件并留下审计记录，不能在运行时替代 SQL，也不能因为 SQL/Chroma 故障自动接管业务。

### 2.3 权威矩阵

| 对象 | 最终权威 | 派生/临时状态 | 失败语义 |
|---|---|---|---|
| 用户、密码、角色、会话、refresh、撤销 | MySQL | 可选内存缓存；Redis 不参与正确性 | SQL 不可用即 fail-closed；不得因缓存丢失放行。 |
| 聊天、消息、笔记、知识源、原始文档、图片、MD5/摘要 | MySQL | 本地导出文件仅作显式运维产物 | 事务提交后才产生派生任务；文件副本不构成写入成功。 |
| Skill 原始包、manifest、资源清单、版本、安装状态、grant、RunBinding | MySQL | 本地目录/ZIP 输入、只读 catalog cache | digest、权限或版本不一致时拒绝发布；新导入固定 `installed_disabled`。 |
| job、重试、lease、DLQ、generation 指针、迁移映射、审计 | MySQL | 进程内队列只作唤醒提示 | 进程重启后由 SQL 恢复；不能以内存状态当事实。 |
| Chroma chunks/metadata/vectors | Chroma projection | `active + staging`，可从 SQL 重建 | Chroma 不可用时 RAG `degraded/503`；不在查询内同步重建。 |
| 本地 debug/import/export/rollback | 明确的操作文件 + SQL 审计记录 | 仅开发期默认开启 | 不自动 fallback；正式部署可关闭。 |

## 3. RAG 最终合同

### 3.1 写入和重建

```text
原始文档/笔记写入 MySQL
    -> SQL job（parse/split/embed/index）
    -> 读取用户声明式切片和 embedding 配置
    -> Chroma staging generation
    -> manifest/digest/数量校验
    -> 原子激活 active generation
    -> 成功后删除旧 generation
```

SQL 保存原文、业务 metadata、切片配置、embedding fingerprint、当前 generation、job 状态和错误信息；不保存向量 BLOB。旧 Chroma 或旧 MD5 文件不能作为最终恢复来源，恢复必须从 SQL 原文重新解析和 embedding。

### 3.2 查询

```text
query
  -> RAG port
  -> HyDE（启用时）
  -> Chroma vector retrieval
  -> 按需构建 BM25 候选
  -> Chroma 笔记检索
  -> CrossEncoder rerank
  -> LLM context/answer
```

RAG core 只依赖抽象 port，Chroma 是默认 adapter。adapter 统一返回 `documents`、`scores`、`source_ids`、`generation`、`status` 和 `degraded_reason`。Chroma 初始化、collection 缺失、权限、版本或重建失败时，返回稳定的 `degraded/503`；不得删除原目录、覆盖健康 generation 或在请求线程中长时间重建。

### 3.3 collection 和用户自定义策略

collection 身份由下列三元组决定：

```text
index_kind + embedding_fingerprint + generation
```

同一配置可共享 collection，通过 `user_id` metadata 过滤；不同 embedding 空间不得混用。切片器、top-k、过滤、rerank 和 embedding 模型使用声明式配置，配置变化创建 staging generation。最多短暂保留 `active + staging`，切换成功立即清理旧 generation；不保留历史 generation。

## 4. 认证、授权与审计合同

AR-0 已关闭，但其范围只冻结合同和失败语义，不代表授权闭环已经实现。AR-2 必须完成：

- FastAPI users、sessions、refresh、revocations、roles 和 audit 全部进入 MySQL；Redis 丢失不影响正确性。
- 内容/Skill 管理员与安全管理员角色分离；内容准备、`grant approve`、`grant revoke` 和紧急例外不得由同一审批动作自动完成。
- 每个授权、撤销、策略变更、运行绑定和恢复动作记录 actor、actor role、scope/owner、source/package/version、policy/tool-provider digest、before/after revision、grant diff、reason、effective/expiry、result/error code、correlation ID 以及关联 run/job/import ID。
- grant revoke、过期、拒绝、回滚、digest 漂移和 worker 重启必须使新 Run、排队 job 和延迟确认 fail-closed，并记录受影响对象和传播结果。
- API、worker、重启恢复和本地 debug 通道使用同一审计事实，能够按 correlation ID 对账；缺字段、过期授权和未知 revision 一律拒绝。

## 5. 分阶段执行计划

阶段状态固定为：`草案`、`待你确认`、`实施中`、`待验证`、`已关闭`、`阻塞`。每阶段只能有一个当前实施阶段；未满足退出条件不得跳阶段。

| 阶段 | 目标与任务 | 依赖 | 主要产物 | 退出条件/回滚 |
|---|---|---|---|---|
| S0 文档与决策冻结 | 固化本蓝图、权威矩阵、迁移顺序、状态枚举、冻结新功能；盘点当前表、文件、Chroma、Skill 和认证入口。 | 用户确认文档；已于 E0/S0 关闭。 | ADR/蓝图、差异清单、阶段记录目录、批准边界。 | 用户确认后关闭；若发现事实冲突，只改文档并回到 `草案`，不改业务代码。 |
| S1/AR-1 SQL 基础与 durable runner | 设计统一 UUID/FK/约束、users/sessions/jobs/domain/skill/rag generation/audit/migration_map 表；提供 UoW、备份、restore、dry-run、对账和短暂停写工具；SQL job 实现 claim/lease/heartbeat/idempotency/retry/cancel/DLQ/backpressure，runner 默认并发 1。 | E1/AR-0/SK-0 已关闭；E2 批次、owner/approver 和专用隔离拓扑已获用户批准。 | Alembic migration、schema map、job/UoW/runner、备份 manifest、恢复 runbook、迁移报告；实现与真实隔离证据已记录，用户于 2026-08-28 批准关闭。 | 结构/计数/digest/约束和 kill/restart/重复/DLQ 对账已通过；E2 已关闭，S2 仍需单独计划和授权，失败保留旧表只读并恢复备份。 |
| S2/AR-2 FastAPI 认证接管 | 导入用户/hash/refresh/token version；FastAPI 成为写权威；先 shadow 校验，再切 login/refresh/revoke；Django 变只读适配；完成角色分离和授权审计。 | S1、认证迁移 dry-run 和回滚点。 | auth API、会话/撤销表、切换开关、审计查询、Django read-only adapter。 | 双路径抽样一致、撤销传播、授权审批和中断续跑通过；失败切回 Django 只读适配，不产生双写。 |
| S3/AR-3 业务数据迁移与唯一写权威 | 在同一 MySQL 实例/数据库内完成业务分表过渡；稳定 UUID/FK；源文档/图片/Skill/聊天/笔记对账；FastAPI 成为唯一业务写入口。 | S1、S2、迁移 dry-run、备份和停写批准。 | 迁移报告、稳定 ID/FK、业务表、legacy identity map、旧输入处置清单。 | 行数/digest/约束/审计和唯一写权威抽样通过；失败恢复迁移前快照，不删除旧输入。 |
| S4/AR-4 RAG/Chroma 收敛 | SQL 成为原文和配置源；RAG port + Chroma adapter；active/staging generation、重建、对账、degraded/503；用户自定义切片/检索声明式配置。 | S1、S3，Chroma 隔离目录。 | source/chunk config、generation 表、rebuild job、adapter 合同、RAG E2E。 | 正常查询、配置切换、Chroma 故障重建和旧 generation 删除通过；失败只降级 RAG，不影响登录/会话。 |
| S5/AR-5/SK-1..3 Codex Skill 重构 | 目录/ZIP 导入、`SKILL.md` frontmatter、manifest/resources/raw package SQL 化；规范化单一表示；新导入 `installed_disabled`；保留 A/B 插口，C 结构化 `unsupported`。 | S3、S4、统一授权审计合同。 | parser/validator、版本/digest、安装/发布 API、legacy_identity_map、Skill 迁移报告。 | 恶意包、digest、重复、权限、grant/revoke 和重启恢复通过；失败保留旧健康版本，禁止 ready。 |
| S6 核心业务回接与文件清理 | 回接知识、笔记、聊天；原始文档/图片/MD5 进入 SQL；清除文件权威和旧 Skill/Chroma 内部依赖；保留显式本地运维通道。 | S2-S5 退出条件。 | domain service、数据对账、旧输入处置清单、debug 通道开关。 | 核心回归、用户隔离、审计和恢复通过；失败恢复 SQL 快照，禁止删除未对账输入。 |
| S7 删除过渡依赖与单机部署 | 移除 Django 运行链路、Redis 正确性依赖、旧 YAML/Registry/MD5/目录适配器；FastAPI 直接托管前端构建产物。 | S6、用户批准删除清单。 | 单机启动/停止/升级/回滚 runbook、依赖清单、部署 smoke。 | 空库/恢复库安装、启动、核心流程和关闭本地通道通过；回滚到删除前备份。 |
| S8 恢复验收与发布解冻 | 真实等价 MySQL/Chroma 单机演练；验证备份恢复、RPO/RTO、核心 API/UI/RAG 回归和文档一致性。 | S1-S7、批准环境和负责人。 | 最终证据包、恢复日志、风险接受记录、发布解冻决定。 | 用户确认关闭后才解冻新功能；任一关键证据缺失保持 `阻塞`。 |

### 5.1 每阶段必须记录的字段

每个阶段在 `project_changes/<date>-<topic>/` 下维护 `plan.md`、`change-log.md` 和 `test-record.md`，并同步更新本主计划：

| 字段 | 要求 |
|---|---|
| 状态和确认 | 使用固定状态枚举；记录用户确认日期、确认范围和未决问题。 |
| 目标/范围 | 写明本阶段做什么、明确不做什么，列出受影响模块和表。 |
| 依赖/前置 | 记录上一阶段证据、环境、版本、迁移开关和批准人。 |
| 变更日志 | 每个 commit/文件/迁移/配置变更有原因、owner、回滚点和关联 issue。 |
| 测试证据 | 环境、拓扑、版本、fixture/真实依赖、命令、阈值、实际结果、日志路径。替身测试必须明确不能证明什么。 |
| 数据证据 | 行数、digest、generation、审计事件、对账差异和处理结果。 |
| 回滚 | 明确可执行命令、备份/快照、停写窗口、恢复后校验和负责人。 |
| 未完成项 | 不把未执行、外部阻塞或用户待决事项标成完成；写明下一步和阻断条件。 |
| 关闭确认 | 测试完成后先标 `待验证`，由用户确认后才标 `已关闭`。 |

## 6. 关口与当前未收口项

### 当前已收口

- P0-0 至 P0-6 和 E1/AR-0/SK-0 已完成；用户于 2026-08-27 明确确认关闭 E1。
- Chroma 初始化失败不再删除持久目录；Skill 新导入固定禁用；MCP YAML 已冻结为非权威 adapter/cache。
- E1 隔离 MySQL/Chroma 故障与恢复、manifest 篡改拒绝、characterization、隔离完整 pytest `284 passed` 和 offline benchmark smoke `4/4`、regression `117/117` 已记录；历史失败与误连事故未被覆盖。
- 0826 批次报告、inventory、change-log 和 test-record 已归档。

### 后续未收口

1. 统一角色分离、`grant approve/revoke`、撤销传播、延迟确认失效和完整授权审计仍是 AR-2/S2 前置；当前只有 fail-closed 合同和离线负向测试。
2. FastAPI 认证写权威、业务源数据迁移、Skill 规范化迁移和 RAG generation 表尚未实现。
3. 旧 Django、Redis、文件/MD5 sidecar、旧 Skill 内部结构和旧 Chroma generation 尚未按清单删除；删除前必须完成对账和备份。
4. 真实目标 schema 的核心 API/UI/RAG E2E、单机部署 runbook、生产 RPO/RTO 和最终恢复验收尚未完成；原生 Linux/macOS 已冻结在支持范围外，不设门禁。
5. 以上后续事项关闭前不得发布新功能；真实模型质量、C 级执行、公网和 HA 不在 E2 关闭范围内。

## 7. 门禁映射

| 门禁 | 本次含义 | 不包含 |
|---|---|---|
| `SKILL-GATE` | 本地目录/ZIP、A/B Skill、单机 SQL runner、授权撤销、Chroma 重建和恢复证据。 | C 级脚本执行、多实例收敛、公网 HA。 |
| `ARCH-GATE` | S0-S8 关闭；单一 MySQL 业务权威、FastAPI 唯一写入、Chroma 可重建、单机部署和恢复验收通过。 | 公网/HA、长期扩容能力。 |
| `EXEC-SKILL-GATE` | 仅在未来明确启用 C 级时验证隔离进程、Node/Python、资源/网络/secret 限制。 | 本次 A/B 和单机目标的前置。 |
| `PUBLIC-HA-GATE` | 未来如改变范围，再单独验证 TLS、反向代理、多实例、HA、PITR、canary 和公网运维。 | 当前局域网目标，不得反向扩大本次范围。 |

## 8. 执行纪律

- 文档草案 -> 用户确认 -> 实现 -> 测试/迁移证据 -> 用户确认关闭 -> 下一阶段；没有跳过确认的隐式推进。
- `AR-0 + SK-0` 与 E2/AR-1 已关闭；产品工作包 `7-10`、业务数据迁移/删除和其他后续门禁仍按各自计划冻结。
- 任何本地 debug 通道都必须显式调用、受开关控制、记录审计，不能自动 fallback 或成为第二写权威。
- 发现新事实与蓝图冲突时，先停在当前阶段，更新差异和回滚说明，再由用户决定是否改蓝图；助手不替用户做最终架构决策。

相关事实和证据：[0826 执行计划](./archive/2026-08-26/change-route-execution-plan-2026-08-26.md)、[P0 收口报告](./archive/2026-08-26/p0-completion-report-2026-08-26.md)、[当前架构](./archive/2026-08-26/project_develop.md)、[标准 Skill 规格](./archive/2026-08-26/standard_skill_integration_requirements.md)。
