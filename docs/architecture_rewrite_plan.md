# 架构重写计划

状态：当前停留在 `AR-0 + SK-0`；P0/P1 阻断未关闭，所有阶段退出门均未通过

最近复核：2026-08-25

适用范围：`ai_document_assistant` 分支

本文件是 AR/SK 状态、依赖、当前队列和四个门禁的唯一事实源。相关文档各自只维护一类信息：

- [当前架构](./project_develop.md)：运行代码与进程事实。
- [标准 Skill 规格](./standard_skill_integration_requirements.md)：package、权限、运行时和验收合同。
- [安全基线](./security_hardening_plan.md)：已实施控制、剩余风险和公网安全条件。
- [产品路线图](./roadmap_next.md)：R0-R8 职责与工作包 `7-10`。
- `project_changes/`：历史或实施证据，不作为活状态源。

## 1. 决策与发布档位

目标是一个代码库、一个关系数据写权威和一个 FastAPI 模块化业务单体，同时保留独立的 API 与 worker 故障域：

```text
Browser -> same-origin entry -> FastAPI modules
                               -> one MySQL authority
                               -> Redis bounded runtime state
                               -> immutable Storage
                               -> rebuildable Chroma projection

                           worker runtime
                               -> durable job/outbox
                               -> bounded model/index work
                               -> isolated process protocol
```

“单体”指代码和数据边界，不指单进程。模型、Embedding、大文件和第三方代码不得与 core API 共用无限资源。

发布能力分开验收：

| 门禁 | 解锁范围 | 不代表 |
|------|----------|--------|
| `SKILL-GATE` | 声明平台上的本地 A/B Prompt/Resources | C 级代码可执行；公网/HA 就绪 |
| `ARCH-GATE` | 本地架构与产品工作包 `7-10` | C 级代码可执行；公网/HA 就绪 |
| `EXEC-SKILL-GATE` | 声明平台上的 C 级 Node/Python 执行 | 公网/HA 就绪 |
| `PUBLIC-HA-GATE` | 公网、多实例、canary、HA/DR | 自动启用 C 级执行 |

当前项目明确为本地开发档位。C 级与公网/HA 是可选后续轨道，不反向冻结已经验收的本地 A/B 产品开发。

本次重写不引入微服务、第二套向量后端或长期 v2/双写；不在无备份、dry-run、对账和恢复证据时迁移或删除数据；不把 Chroma/Redis 变成关系数据主库。

## 2. 当前现实与数据权威

### 2.1 主要差距

| 维度 | 当前 | 目标 |
|------|------|------|
| 入口/身份 | Vite 分流 Django 与 FastAPI；用户权威在 Django MySQL | 同源 FastAPI；统一 users/sessions/roles/audit |
| 关系数据 | 两套 migration；业务 `user_id` 多为字符串且无跨库 FK | 一个逻辑 schema、统一 UUID/FK/删除策略和 Alembic |
| 任务 | 请求内工作、临时 background task 与局部 outbox 并存 | 独立 worker + durable job/UoW/lease/fencing/DLQ/backpressure |
| 文件/索引 | Blob、目录、MD5 JSONL、Chroma 多路状态 | Storage canonical source + MySQL state + Chroma projection |
| 配置 | 环境变量、本地 JSON/YAML 分散 | 部署只读配置与版本化业务配置分层 |
| Skill | 标准 package 主路径和 A/有限 B 切片已形成；旧目录提前删除 | 可恢复的 MySQL/Storage 权威、单包隔离、完整授权审计与可选 runner |
| 发布恢复 | 无统一 generation manifest、canary 或 restore-forward 证据 | 分档位的本地恢复与公网 HA runbook |

### 2.2 权威矩阵

| 数据 | 权威 | 可重建/短期状态 | 失败规则 |
|------|------|-----------------|----------|
| 用户、密码、角色、会话、撤销、审计 | MySQL | Redis auth cache | MySQL 失败即失败；Redis 丢失不得错误放行 |
| 会话、笔记、记忆、模型配置 | MySQL | Redis cache、向量 projection | 事务提交后异步投影 |
| 上传源文件与 Skill package | immutable Storage object | worker staging、解析产物 | checksum/finalize 后才能发布 |
| 文档/索引状态 | MySQL job/source manifest | Chroma collection | 版本化、可 fencing、对账和重建 |
| 限流、短期锁、pending action | Redis | 无永久副本 | 明确 TTL、容量和 fail-open/closed |
| Skill/version/install/policy/grant/RunBinding | MySQL | Registry snapshot/cache | 业务事实与 outbox 同事务；坏包不得清空健康快照 |
| Tool/MCP definition 与 policy | 目标 MySQL 版本化事实 | 本地只读 adapter/cache | RunBinding 固定 digest；实例本地 YAML 不得是最终权威 |

## 3. 依赖、状态与当前队列

### 3.1 固定依赖

```text
AR-0 + SK-0 containment/contracts
  -> real MySQL/Redis/Storage/Chroma integration baseline
  -> AR-1 generic durable jobs/UoW/process protocol + SK-1
  -> Skill import/validation/publish as first worker consumer
  -> AR-2 identity/roles/audit
  -> AR-3 authoritative relational schema
  -> AR-4 Storage/projection + SK-2
  -> AR-5 skills/tools/mcp first + SK-3
  -> SK-5 A/B reconciliation/recovery
  -> SKILL-GATE -> ARCH-GATE -> local product queue

optional C track after AR-1/AR-2/AR-4/SK-3
  -> SK-4 -> EXEC-SKILL-GATE

optional public track after ARCH-GATE and deployment decision
  -> AR-6 -> PUBLIC-HA-GATE
```

AR-1 只交付语言无关的隔离进程协议和恶意测试桩；Node/Python adapter 属于 SK-4。这样避免 AR-1 与 SK-4 循环依赖。

### 3.2 当前状态

状态只使用“未开始 / 实现中 / 证据不全 / 退出门通过”。提前切片不改变阶段入口。

| 阶段 | 状态 | 已有切片 | 主要阻断 |
|------|------|----------|----------|
| AR-0 + SK-0 | 实现中，证据不全 | 工作包 `1-6` 的安全/认证/migration/API-SSE 基线 | Chroma reset、发布安全、真实依赖环境、readiness、威胁模型、inventory、characterization |
| AR-1 + SK-1 | 未开始，有提前切片 | parser、Skill domain、revision/outbox | 无通用 job/worker/UoW/lease-fencing；import 仍在请求内 |
| AR-2 | 未开始，有保护切片 | access/refresh、token version、部分 grant 数据结构 | 身份未收敛；无角色分离、grant revoke 和完整审计 |
| AR-3 | 未开始，有 migration 切片 | Alembic baseline、Skill tables | 无统一 UUID/FK schema；Skill provenance 与 Tool/MCP policy 未成权威 |
| AR-4 + SK-2 | 未开始，有提前切片 | content-addressed Skill Storage、API/UI 生命周期 | 无 staging TTL/GC、激活重验、orphan 对账和恢复证据 |
| AR-5 + SK-3 | 未开始，有提前切片 | A/有限 B、资源编辑、RunBinding 数据面 | 无 per-user、累计预算、真实 A/B E2E、通用迁移器和影子对账 |
| SK-4 | 未开始 | 只保存 `scripts/`，C 包禁用 | 无 adapter、沙箱、lock/profile 和声明平台证据 |
| SK-5 | 未开始，有提前清理切片 | 旧运行目录删除与静态禁回归、固定 seed | 删除早于 inventory/迁移/观察/回滚；无自定义 Skill 零数据证明 |
| AR-6 | 未开始 | 无可用生产拓扑 | 无公网部署、canary、PITR/HA、监控和 DR 证据 |

### 3.3 当前执行队列

1. 建立 R7 最小测试入口：失败回归、真实依赖启动方式、证据模板和 scoped diff check。
2. 关闭 AR-0/SK-0 P0：禁止 Chroma 破坏性 reset；冻结不安全的 Skill publish/activate/rollback；坏包不得发布 ready、ack outbox、清空全 Registry 或以同 revision degraded 继续运行。
3. 固定新导入为服务端 `installed_disabled`；修正 import `409/413`、ZIP media type、`Idempotency-Key` CORS 和 OpenAPI 错误合同；冻结角色分离、grant revoke、完整审计与 Tool/MCP digest 合同，关闭现有绕过。
4. 补 package threat model、legacy checksum inventory、API/UI/Prompt/route characterization，并建立隔离的真实 MySQL/Redis/Storage/Chroma 基线。
5. AR-0/SK-0 退出后实施通用 AR-1 worker/UoW/process protocol，以 Skill import/validation/publish 为首个 consumer。
6. 按 AR-2/3 -> AR-4/5 -> SK-5 顺序完成身份/schema、Storage 生命周期、per-user/预算、真实 A/B E2E 和迁移对账，再执行本地两门。

## 4. 阶段合同

### AR-0：可靠性与 P0 containment

- 交付：批准的本地 SLO/RPO/RTO/容量、依赖故障矩阵、generation manifest、只读数据盘点、分层 readiness、Chroma quarantine、Skill 发布止血、SK-0 威胁/inventory/characterization。
- 退出：真实依赖故障/恢复抽样通过；Chroma 不删除持久目录；缺失/损坏 package 不暴露半发布状态；导入禁用与 API 合同准确。
- 回滚：只允许报告、测试和保护性开关；任一 P0 未关即停留本阶段。

### AR-1：运行时、持久任务与共享合同

- 入口：AR-0/SK-0 全部退出证据通过。
- 交付：独立 API/worker；通用 job 状态、claim/lease/heartbeat/fencing/retry/cancel/DLQ/backpressure；application UoW；Storage/Vector ports；SSE replay；隔离进程协议与测试桩；Skill import worker consumer。
- 退出：kill/restart、过期租约、重复/乱序、毒任务、回滚、背压和 SSE 断线都有确定结果；API 在 worker/模型不可用时保持 core readiness。

### AR-2：身份、角色与审计

- 入口：AR-1 任务/UoW/Redis/SSE 合同通过，用户迁移 dry-run 和 change capture 就绪。
- 交付：FastAPI users/sessions/revocations/roles/audit；UUID/hash/token 兼容迁移；写入栅栏与 restore-forward；Skill 管理员/安全管理员分权；grant 独立 approve/revoke；全写操作审计与查询。
- 退出：身份/权限/hash/审计逐项一致；Redis 丢失不错误放行；切换中断可续跑；业务不再运行时查询 Django 用户状态。

### AR-3：关系数据权威

- 入口：AR-2 观察期通过，空库 migration、snapshot 和增量重放已演练。
- 交付：统一 UUID/FK/唯一约束/删除策略；checkpoint migration；N/N-1 schema；Skill upstream/source/parent/derived digest；Tool/MCP version/policy authority 与 RunBinding digest。
- 退出：计数、摘要、孤儿、权限隔离一致；迁移可暂停/重放，差异超阈值自动停止；空库和 snapshot 可恢复。

### AR-4：canonical Storage 与 projection

- 入口：AR-1 ports/jobs 和 AR-3 schema 已通过。
- 交付：staged key + TTL + checksum + finalize + 引用感知 GC；DB/final object orphan reconciliation；版本化 Chroma pointer/fencing/rebuild；Skill package 作为 SK-2 首个 consumer。
- 退出：publish/activate/rollback 在切换 pointer 前重验 Storage；部分失败不产生无法解释的孤儿；跨存储恢复与 checksum 对账通过。

### AR-5：业务域模块化

- 入口：AR-2 至 AR-4 退出；目标域有合同和性能基线。
- 顺序：后端 `skills/tools/mcp -> notes/memory -> chat/sessions -> models -> knowledge`；前端 `auth/shared -> skills/tools -> chat -> knowledge -> notes -> remaining`。
- Skill 首域退出：per-user scope、累计资源预算、真实 MySQL/API/第三方 A/B E2E、通用离线 `LegacySkillMigrator`、catalog/Prompt/route 影子对账和无 Git 写入全部通过。

### SK-4：可选 C 级执行

- 入口：AR-1 通用协议、AR-2 权限、AR-4 Storage、SK-3 A/B/影子对账通过，并明确支持的 OS/runtime。
- 交付：Node/Python adapters、digest-locked environment、RuntimeBinding、只读挂载、默认断网、CPU/内存/PID/磁盘/输出/secret 限制和进程树终止。
- 退出：每个声明平台的真实 Node/Python 与恶意 package E2E 通过。当前 Windows-only lock/CI 不得证明 Linux/macOS。

### SK-5：A/B 迁移、恢复与单轨收口

- 入口：SK-3 真实 A/B E2E/影子对账和 AR-4 恢复工具通过；SK-4 不是前置。
- 交付：从只读 Git artifact/备份/导出盘点 legacy 输入；通用迁移器；逐项或零数据报告；Registry/Storage rebuild、clean install、active pointer rollback 和观察期。
- 退出：所有可发现 legacy 输入已迁移或显式处置；固定 seed 不充当自定义 Skill 迁移证明；旧 runtime 不恢复。

### AR-6：可选公网/HA 发布

- 入口：本地 `ARCH-GATE` 通过且有明确部署拓扑、容量目标和运维责任人；公网启用 C 时还需 `EXEC-SKILL-GATE`。
- 交付：TLS/反向代理、canary/abort、connection drain、MySQL failover/PITR、Redis/Storage 耐久性、监控值班、组合故障与 restore-forward。
- 退出：生产等价环境的 install/migrate/start/test/rollback、SLO/RPO/RTO、告警与 DR 演练通过。

## 5. 门禁

### SKILL-GATE：本地 A/B

必须满足：

- SK-0/1/2/3/5 证据完整，C package 保持不可启用且不可绕过。
- active package 全部来自统一 validator/MySQL/Storage；前端新建/编辑/导出可无损重导入。
- publish/activate/rollback 原子切换并重验 checksum；坏包隔离且保留其他 Skill/上一健康快照。
- 新导入固定禁用；upstream version/digest 冲突、`409/413`、ZIP/CORS/OpenAPI 合同稳定。
- 角色分离、grant revoke、完整审计和 Tool/MCP policy digest 固定通过；Redis 丢失可恢复。
- legacy 迁移/零数据、回滚、clean install、worker kill 和声明平台 A/B conformance 通过。

### ARCH-GATE：本地产品解锁

要求 AR-0 至 AR-5 和 `SKILL-GATE` 通过，并证明：单一身份/关系/Storage 权威；API/worker 隔离；durable job/SSE replay；Chroma 可 fencing/rebuild；本地真实依赖恢复和应用/worker 回滚可执行。通过后才选择工作包 `7-10`。

### EXEC-SKILL-GATE：C 级执行

要求 SK-4 在每个声明平台通过真实 Node/Python 构建/执行、供应链、资源限制、网络/文件/secret 拒绝、取消、恢复和进程树终止。未通过时不影响 A/B，但 C 必须保持禁用。

### PUBLIC-HA-GATE：公网与 HA

要求 AR-6 的生产等价拓扑、TLS/egress、canary、容量、监控、PITR、组合故障和 DR 证据。公网只提供 A/B 时不依赖 C 门；公网启用 C 时两门都必须通过。

### 5.1 阶段证据最低集

| 阶段 | 最低证据 |
|------|----------|
| AR-0/SK-0 | SLO/RPO/RTO、inventory、备份抽样、Chroma/Skill P0 回归、故障矩阵、readiness、威胁/characterization |
| AR-1/SK-1 | API/worker、job kill/restart、lease/fencing/DLQ/backpressure、UoW rollback、import worker、SSE replay、进程树测试桩 |
| AR-2 | snapshot/change capture、身份/权限/审计对账、key rotation、grant revoke、增量重放和 restore-forward |
| AR-3 | checkpoint migration、差异 abort、FK/唯一约束、孤儿/tombstone、N/N-1、Skill/Tool/MCP provenance digest |
| AR-4/SK-2 | staging/TTL/finalize/checksum、orphan/GC、激活重验、projection fencing/rebuild、跨存储恢复 |
| AR-5/SK-3 | per-user/预算、真实 A/B E2E、通用迁移器/影子对账、模块边界、权限/失败/取消/性能 |
| SK-4 | 声明平台 lock/CI、Node/Python/恶意 package、资源/网络/文件/secret/进程树和产物 |
| SK-5 | legacy inventory/零数据、幂等迁移、单包隔离、Registry/Storage rebuild、clean install、观察期 |
| AR-6 | canary/abort、drain、failover/PITR、监控值班、组合故障、restore-forward |

## 6. 执行规则

- 每个阶段在 `project_changes/<日期-主题>/` 维护 `plan.md`、`change-log.md`、`test-record.md`；测试记录注明真实依赖或替身、基线和未覆盖风险。
- 真实 MySQL 迁移必须先有备份、dry-run、审批和隔离恢复；本计划本身不授权连接或修改当前数据库。
- 切换后优先 restore-forward；不得把恢复旧备份、切回代理或生产 downgrade 冒充零数据回滚。
- 任一退出条件缺失即停留本阶段；已有代码、绿色 unit test、生成文件 current、目录删除或表结构存在都不是通过证据。
- 工作包 `7-10` 在本地两门前暂停；允许的变更仅限 P0、安全/数据完整性、启动阻断、门禁底座和标准 A/B Skill 首域。
