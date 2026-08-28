# 架构重写计划

状态：`AR-0 + SK-0` 已关闭；下一阶段 `E2/S1/AR-1` 为 `待你确认`，尚未授权实施。

最近复核：2026-08-28
适用分支：`ai_document_assistant`

本文是 AR/SK 阶段、门禁、当前队列和关闭条件的唯一事实源。执行交接细则见[架构重构执行交接手册](./architecture-execution-handoff-2026-08-26.md)；最终架构和逐阶段任务见[最终重构蓝图](./architecture-target-blueprint-2026-08-26.md)；运行代码事实见[当前架构归档](./archive/2026-08-26/project_develop.md)；P0 证据见[0826 执行计划归档](./archive/2026-08-26/change-route-execution-plan-2026-08-26.md)和[P0 收口报告归档](./archive/2026-08-26/p0-completion-report-2026-08-26.md)。`project_changes/` 只保存批次证据，不覆盖本文的状态判断。

## 1. 最终目标

本项目只面向单机、小范围局域网和低并发。最终运行形态是一个 FastAPI 进程直接托管前端构建产物和全部业务 API/SSE，使用同一个 MySQL 实例中的一个数据库保存全部业务事实；SQL job 加内置 runner 默认并发为 1。Chroma 保留为独立、可重建的 RAG 向量投影，不承担业务写权威；不保存向量 BLOB 到 SQL。

```text
局域网浏览器
    -> 一个 FastAPI 进程（静态前端、认证、业务、SQL runner）
       -> 一个 MySQL 实例/数据库（唯一业务写权威）
       -> Chroma adapter（可重建 RAG projection）
       -> 本地模型/Embedding/Reranker
```

最终不引入微服务、第二套向量后端、长期双写、Redis 正确性依赖或独立业务数据库。Django、Redis、文件/MD5 sidecar 和旧 Skill 内部结构只在迁移/调试窗口保留，完成对账和恢复验证后删除。

## 2. 当前状态

阶段状态只能使用：`草案`、`待你确认`、`实施中`、`待验证`、`已关闭`、`阻塞`。提前存在的代码切片不改变阶段入口，也不能代替退出证据。

| 阶段 | 当前状态 | 已有事实 | 未收口/入口条件 |
|---|---|---|---|
| AR-0 + SK-0：P0 containment 与证据收口 | `已关闭` | Chroma 失败隔离、Skill 发布止血、MCP YAML 权威冻结、离线备份工具、当前环境 R7、E1 隔离 MySQL/Chroma 故障与恢复证据已记录；隔离完整 pytest `284 passed`，offline benchmark smoke `4/4`、regression `117/117`；用户于 2026-08-27 确认关闭 | E1 范围无剩余阻塞。真实模型质量和 AR-2 审计实现不属于 E1；原生 Linux/macOS 为 `out-of-scope/frozen`；本状态不表示后续门禁通过。 |
| AR-1：统一 SQL 基础与运行时合同 | `待你确认` | 局部 Alembic、局部 outbox 和 API/SSE 合同存在；E1/AR-0/SK-0 已关闭；E2 批次边界和静态代码盘点已提交 | 实施前必须单独确认[E2 批次计划](../project_changes/2026-08-28-e2-ar1-sql-foundation/plan.md)、隔离 MySQL、owner/approver、备份与回滚边界；统一 schema、备份/restore、UoW、SQL job、单并发 runner、lease/fencing/retry/cancel/DLQ/backpressure 尚未交付。 |
| AR-2：FastAPI 身份、角色与审计 | `草案` | access/refresh/token-version 和部分 grant 数据结构存在 | users/sessions/refresh/revocation 全部 SQL 化、角色分离、approve/revoke 传播和完整审计未完成。 |
| AR-3：业务数据与迁移权威收敛 | `草案` | 当前 Django/FastAPI 分表和文件/Chroma 事实已盘点 | 同库分表过渡、稳定 UUID/FK、源文档/图片/MD5 入 SQL、旧输入对账和唯一写入口未完成。 |
| AR-4：RAG/Chroma projection | `草案` | Chroma 失败隔离、staging/rebuild fixture 已有 | RAG port、generation 表、用户声明式切片/检索、SQL 重建和真实 Chroma E2E 未完成。 |
| AR-5 + SK-1..3：Skill 与核心业务回接 | `草案` | Codex 风格 A/有限 B 切片和 `installed_disabled` 已有 | SQL manifest/raw package、标准目录/ZIP、授权闭环、知识/笔记/聊天回接和旧结构清理未完成。 |
| SK-4：C 级执行 | `阻塞`（本次不做） | 仅保留 `unsupported` 插口 | 只有用户改变范围并明确启用 C 级后才启动；不阻塞本地 A/B。 |
| AR-6：删除过渡依赖与单机部署/恢复 | `草案` | 当前三进程开发拓扑有说明 | 删除 Django/Redis/旧 adapter、FastAPI 直接托管前端、单机升级/恢复和核心回归未完成。 |

## 3. 固定依赖与顺序

```text
AR-0/SK-0 文档确认、P0 证据和真实依赖基线
  -> AR-1 统一 MySQL schema + SQL job/UoW/runner
  -> AR-2 FastAPI 用户/会话/撤销/角色/审计
  -> AR-3 业务源数据迁移与唯一写权威
  -> AR-4 RAG port + Chroma generation/rebuild
  -> AR-5 Skill 标准化与知识/笔记/聊天回接
  -> AR-6 删除过渡依赖、单机部署和恢复验收
  -> SKILL-GATE -> ARCH-GATE
```

每一阶段必须先形成文档草案，由用户确认后才实施；实现完成先标 `待验证`，测试和迁移证据齐全且用户确认后才标 `已关闭`。AR-0 已于 2026-08-27 关闭，但 E2/AR-1 尚未获得实施确认；确认前不创建或执行 migration，不迁移/删除现有业务数据，也不解冻产品工作包 `7-10`。

交接批次 `E0-E8` 和蓝图批次 `S0-S8` 只是执行别名，不是第二套状态机；规范对照与每批责任边界见[执行交接手册的映射表](./architecture-execution-handoff-2026-08-26.md)。其中 `E2=S1=AR-1` 必须先完成 SQL schema/UoW/job/runner，`E3=S2=AR-2` 才能做认证审计，`E4=S3=AR-3` 才能迁移业务数据。

## 4. 权威和失败边界

| 数据/能力 | 最终权威 | 失败规则 |
|---|---|---|
| 用户、会话、refresh、撤销、角色、审计、聊天、笔记、知识源、原始文档/图片、Skill、job、generation、迁移映射 | 一个 MySQL 数据库 | SQL 不可用即 fail-closed；内存、Redis、文件不能放行或确认写入。 |
| RAG chunks、metadata、vectors | Chroma projection | 可由 SQL 原文和配置重建；异常时 RAG `degraded/503`，不在查询请求内重建。 |
| 本地 debug/import/export/rollback | 显式操作文件 + SQL 审计 | 开发期默认开启，正式部署可关闭；不得自动 fallback 或成为第二写权威。 |
| Redis、Django、旧目录、MD5 sidecar | 迁移期临时输入/适配层 | 完成切换、对账和恢复后删除；任何残留不得被描述为最终权威。 |

RAG 的 collection 由 `index_kind + embedding_fingerprint + generation` 隔离；最多短暂 `active + staging`，新 generation 成功后删除旧 generation。SQL 不承担向量检索，也不保存向量 BLOB。

## 5. 授权与审计合同（AR-0 冻结，AR-2/S2 实现）

当前只冻结不可绕过的 fail-closed 语义，不能以局部 CapabilityGrant 或单一管理员名单宣称闭环完成。AR-2 必须同时交付：

- 内容/Skill 管理员与安全管理员角色分离；内容准备、`grant approve`、`grant revoke` 和紧急例外不能由同一审批动作自动完成。
- 每次授权、撤销、策略变更、RunBinding、恢复和本地运维动作记录 actor/role、scope/owner、版本与 digest、before/after revision、grant diff、reason、effective/expiry、result/error、correlation ID 和关联 run/job/import ID。
- revoke、过期、拒绝、回滚、digest/revision 漂移和 worker 重启使新 Run、排队 job、延迟确认 fail-closed，并记录传播结果。
- API、runner、重启恢复和审计查询能够按 correlation ID 对账；缺字段或未知 revision 一律拒绝。

## 6. 门禁

### `SKILL-GATE`：本地 A/B

必须证明标准目录/ZIP Skill、SQL manifest/raw package、`installed_disabled`、单机 SQL runner、授权撤销、Chroma generation 重建、旧输入对账和恢复可执行。只要求单实例；C 级、多实例收敛、公网和 HA 不属于本门。

### `ARCH-GATE`：本地架构解锁

要求 AR-0 至 AR-6（不含可选 SK-4）和 `SKILL-GATE` 通过，并证明单一 MySQL 业务权威、FastAPI 唯一写入、Django/Redis/文件权威退出、Chroma 可重建、单机部署和恢复回滚可执行。通过后才可解冻产品工作包 `7-10`。

### `EXEC-SKILL-GATE`：可选 C 级

仅当用户改变范围并启用 `scripts/` 等可执行 Skill 时，验证隔离进程、Node/Python、资源/网络/secret 限制、取消和进程树终止。未启用时保持 `unsupported`，不阻塞本次目标。

### `PUBLIC-HA-GATE`：未来范围

仅当用户将范围扩展到公网、HA 或多实例时，另行验证 TLS、反向代理、容量、PITR、canary、监控和值班。本次局域网目标不依赖该门。

## 7. 证据与阶段记录

每阶段在 `project_changes/<date>-<topic>/` 维护 `plan.md`、`change-log.md`、`test-record.md`，至少记录：

1. 状态、用户确认范围、owner/approver 和未决事项。
2. 目标、非目标、依赖、环境、版本、拓扑和迁移开关。
3. 每个文件/commit/schema 变更、原因、影响、回滚点和关联证据。
4. 命令、阈值、实际结果、日志路径、fixture/真实依赖和替身限制。
5. 数据行数、digest、generation、审计事件、对账差异和处理结果。
6. 可执行的备份、停写、恢复、校验和回滚步骤。
7. 未执行项保持 `未验证/阻塞`，不能写进完成摘要；用户关闭确认单独记录。

## 8. 当前队列

1. E1 批次已关闭；保留[E1 证据目录](../project_changes/2026-08-27-e1-ar0-evidence/)、停止的容器、volume 和 network，未获单独确认不得清理。
2. E2/S1/AR-1 是唯一下一阶段，当前为 `待你确认`；[E2 批次计划与静态盘点](../project_changes/2026-08-28-e2-ar1-sql-foundation/)已准备，需先确认其中的隔离环境、owner/approver、备份、回滚和 runner 合同，再实施代码或 schema 变更。
3. 未确认 E2 前不创建或执行 migration，不连接/迁移现有业务数据；后续仍严格按 E2 -> E3 -> E4 -> E5 -> E6 -> E7 -> E8 推进。
4. 0826 与 E1 批次继续作为 P0/AR-0 证据，不把 E1 关闭误报为 AR-1、`SKILL-GATE` 或 `ARCH-GATE` 完成。
5. 新功能、工作包 `7-10`、C 级 Skill、公网和 HA 在 `ARCH-GATE` 或其独立门禁前保持冻结。

## 9. 重要限制

- 不连接、迁移、删除或覆盖现有 MySQL、Redis、文件和 Chroma 数据，除非对应阶段完成备份、dry-run、对账、停写和恢复批准。
- 绿色 unit test、生成文件、固定 seed、删除旧目录或已有局部 API 不等于门禁通过。
- 发现代码事实与蓝图冲突时，停留当前阶段并更新差异/回滚记录，由用户决定是否修改蓝图。
