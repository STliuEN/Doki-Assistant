# 架构重写计划

状态：`AR-0 + SK-0`、E2、E3、E4 已关闭；E5/S4/AR-4 已关闭（2026-09-14）：C1–C6/V01–V09 通过，后端 529、前端 29/build 通过，真实模型、恢复、故障及浏览器证据齐全；用户已授权收口并在测试后核定 8 条来源。E6/E7 已于 2026-09-15 联合关闭（本机 SQL 权威、A/有限 B 范围），SKILL-GATE/ARCH-GATE/产品工作包 7–10 仍冻结。

最近复核：2026-09-14
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
| AR-1：统一 SQL 基础与运行时合同 | `已关闭` | E1/AR-0/SK-0 已关闭；E2 批次计划、schema map、隔离边界、真实 MySQL/runner/recovery 证据已完成；用户于 2026-08-28 批准关闭 | 统一 schema、备份/restore、UoW、SQL job、单并发 runner、lease/fencing/retry/cancel/DLQ/backpressure 已验证；真实业务迁移仍延后。 |
| AR-2：FastAPI 身份、角色与审计 | `已关闭` | FastAPI SQL 认证、会话/撤销、角色分离、四眼授权审计、迁移对账和浏览器/API 验证已完成；用户于 2026-09-01 明确回复 `批准关闭 E3` | E3 退出条件已通过；关闭不代表生产发布，也不解冻未获确认的后续阶段。 |
| AR-3：业务数据与迁移权威收敛 | `已关闭` | E4 本机迁移、唯一写权威、对账、恢复和故障矩阵已完成；用户于 2026-09-10 明确批准关闭，依据见 E4 批次关闭记录 | 关闭仅覆盖本机单实例；中间材料和旧输入继续保留，后续阶段未自动启动。 |
| AR-4：RAG/Chroma projection | `已关闭` | Q1–Q7、执行/收口授权及来源核定已收到；全量重建、持久配置、隔离/恢复/故障/质量与浏览器验收通过 | 本机单实例范围，无剩余 E5 阻塞；HyDE 7/8 达冻结阈值，历史 6 个 enrichment 死信和执行偏差保留；E6/E7 已于 2026-09-15 联合关闭（本机 SQL 权威、A/有限 B 范围）。 |
| AR-5 + SK-1..3：E6/E7 联合批次 | `已关闭` | 用户持续授权完成剩余缺口并指定新建安全管理员；10 包迁移、8 授权启用、JV01–JV09、后端 539/前端 29 通过 | SQL 包/媒体/授权与业务接入联合验收完成；2 个外部 MCP Skill 保持 unsupported/disabled，原输入保留，E8 未启动。 |
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

每一阶段必须先形成文档草案，由用户确认后实施；测试/迁移证据与关闭授权均具备才标已关闭。AR-0、E2、E3、E4 的历史关闭依据保留。E5 已获持续执行/收口授权，2026-09-14 完成全部退出条件，用户补齐来源核定后正式记录已关闭；没有豁免门槛。E6/E7 已于 2026-09-15 联合关闭（本机 SQL 权威、A/有限 B 范围），业务删除和产品工作包 `7-10` 仍冻结。

交接批次 `E0-E8` 和蓝图批次 `S0-S8` 只是执行别名，不是第二套状态机；规范对照与每批责任边界见[执行交接手册的映射表](./architecture-execution-handoff-2026-08-26.md)。其中 `E2=S1=AR-1` 必须先完成 SQL schema/UoW/job/runner，`E3=S2=AR-2` 才能做认证审计，`E4=S3=AR-3` 才能迁移业务数据。

## 4. 权威和失败边界

| 数据/能力 | 最终权威 | 失败规则 |
|---|---|---|
| 用户、会话、refresh、撤销、角色、审计、聊天、笔记、知识源、原始文档/图片、Skill、job、generation、迁移映射 | 一个 MySQL 数据库 | SQL 不可用即 fail-closed；内存、Redis、文件不能放行或确认写入。 |
| RAG chunks、metadata、vectors | Chroma projection | 可由 SQL 原文和配置重建；异常时 RAG `degraded/503`，不在查询请求内重建。 |
| 本地 debug/import/export/rollback | 显式操作文件 + SQL 审计 | 开发期默认开启，正式部署可关闭；不得自动 fallback 或成为第二写权威。 |
| Redis、Django、旧目录、MD5 sidecar | 迁移期临时输入/适配层 | 完成切换、对账和恢复后删除；任何残留不得被描述为最终权威。 |

RAG 每用户/index_kind 独立 generation 和 collection，由 `index_kind + embedding_fingerprint + generation` 隔离并强制 user_id 校验；最多短暂 `active + staging`，新 generation 成功后删除旧 generation。索引配置变化重建，top-k/查询过滤/HyDE/rerank 只更新查询配置版本。首次 E5 从 SQL 全量重建，期间相关 RAG 为 degraded/503，不维持旧访问。Q4–Q7 已确认：只在 E5 应用层暂停当前用户相关写入；知识/笔记全部成功后成组开放，任一纳入源失败阻断，日常索引重建同样 503。禁止 MySQL 全局只读、全库锁、停主机服务或改变 new-api 连接/权限。以上合同已按 E5 C1–C6 验收通过，后续继续遵守。SQL 不承担向量检索，也不保存向量 BLOB。

## 5. 授权与审计合同（AR-0 冻结，AR-2/S2 已关闭）

E3/AR-2 已完成实现、验证并经用户批准关闭，以下不可绕过的 fail-closed 合同仍是当前边界；E4 已另行实施并关闭，E5 及其他后续工作按各自阶段确认：

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
2. E2/S1/AR-1 已关闭；[E2 批次记录](../project_changes/2026-08-28-e2-ar1-sql-foundation/)已记录授权、代码切片、真实隔离 MySQL、恢复、runner、kill-restart 证据和关闭确认。
3. E3 已关闭；[E4 批次](../project_changes/2026-09-02-e4-ar3-business-migration/plan.md)和 [E4 关闭证据](../project_changes/2026-09-02-e4-ar3-business-migration/artifacts/e4-closure-20260910.json)记录 2026-09-10 关闭。E5 已于 2026-09-14 完成全量执行及全部关闭验收；E6/E7 已于 2026-09-15 联合关闭（本机 SQL 权威、A/有限 B 范围），后续阶段按各自计划确认。
4. 0826 与 E1 批次继续作为 P0/AR-0 证据，不把 E1 关闭误报为 AR-1、`SKILL-GATE` 或 `ARCH-GATE` 完成。
5. 新功能、工作包 `7-10`、C 级 Skill、公网和 HA 在 `ARCH-GATE` 或其独立门禁前保持冻结。
6. [E5 执行计划](../project_changes/2026-09-10-e5-ar4-rag-projection/plan.md)与[最终收口判定](../project_changes/2026-09-10-e5-ar4-rag-projection/closure-review.md)记录已关闭及 C1–C6 证据。8 条标签测试前冻结、用户测试后确认；HyDE 7/8、其他及独立 BM25 8/8。保留小样本/历史执行偏差边界，不将质量通过扩大为生产或后续阶段通过。

## 9. 重要限制

- 不连接、迁移、删除或覆盖现有 MySQL、Redis、文件和 Chroma 数据，除非对应阶段完成备份、dry-run、对账、停写和恢复批准。
- 绿色 unit test、生成文件、固定 seed、删除旧目录或已有局部 API 不等于门禁通过。
- 发现代码事实与蓝图冲突时，停留当前阶段并更新差异/回滚记录，由用户决定是否修改蓝图。

## 10. 2026-09-14 联合批次确认

用户明确“关闭e5,执行e6-e7的准备，两个伴生，一起执行”。E5 明确关闭确认另存[关闭追加记录](../project_changes/2026-09-10-e5-ar4-rag-projection/artifacts/user-closure-confirmation-20260914.json)。[E6/E7 联合计划](../project_changes/2026-09-14-e6-e7-ar5-joint/plan.md)是当前执行入口；两阶段同属 AR-5，共享基础先行，E6 导入/授权与 E7 业务接入可重叠实施，联合退出验收，不设“E6 整阶段关闭后才开发 E7”的新授权步骤。准备记录为历史入口；2026-09-15 已完成迁移、授权启用及联合退出验收，见[最终关闭判定](../project_changes/2026-09-14-e6-e7-ar5-joint/closure-review.md)。旧 E5 哈希是关闭时快照，后续主文档变更归本联合批次，原封存输入 ZIP 可核验。
