# 2026-08-26 架构重构执行交接手册

状态：`E0/S0`、`E1/AR-0/SK-0`、`E2/S1/AR-1` 与 `E3/S2/AR-2` 已关闭；E4/S3/AR-3 当前实施中
交接对象：下一位实施负责人、阶段审阅人和恢复操作人  
最终批准人：用户

本手册是交接执行入口。它把[架构重写计划](./architecture_rewrite_plan.md)的阶段顺序和[最终重构蓝图](./architecture-target-blueprint-2026-08-26.md)的目标转换为可执行的工作规则。它不授权跳过门禁、迁移/删除真实数据或发布新功能。

## 1. 交接时只认这三份文档

1. [架构重写计划](./architecture_rewrite_plan.md)：唯一的阶段状态、依赖、门禁和当前队列事实源。
2. [最终重构蓝图](./architecture-target-blueprint-2026-08-26.md)：最终目标、权威边界和阶段交付内容。
3. [阶段执行记录模板](./stage-execution-record-template-2026-08-26.md)：每阶段必须提交的 `plan.md`、`change-log.md`、`test-record.md` 格式。

历史运行说明、专项规格、评审报告和 P0 证据在 `docs/archive/2026-08-26/`，只用于追溯。归档文档与当前计划冲突时，以以上三份文档为准。

## 2. 当前交接结论

- S0 文档和决策收束已完成，q85-q92 已固化。
- P0-0 至 P0-6 和 E1 范围证据已完成；用户于 2026-08-27 明确确认关闭 E1/AR-0/SK-0，历史失败和隔离事故仍保留在证据包中。
- E2/S1/AR-1 已是最近完成阶段；用户已于 2026-08-28 确认批次边界、实施授权并批准关闭，真实隔离验证已完成。该授权只覆盖批准的 E2 隔离拓扑、代码和合成数据，不把 E1/E2 证据当作现有数据 migration 授权。
- 新功能、工作包 `7-10`、C 级 Skill、公网和 HA 全部冻结。
- E2 代码、本地合同和真实 MySQL/container/migration/dump/restore/kill-restart 已按 preflight 和证据矩阵完成并关闭；E1 证据及资源继续只读保护，E2 容器已停止但 volume、network 和证据保留。
- E3/AR-2 已完成本地 FastAPI 认证接管、2 个测试用户迁移、隔离 MySQL restore-forward、角色/审计和浏览器验证；用户于 2026-09-01 明确回复 `批准关闭 E3`，批次已关闭。用户于 2026-09-02 完成 E4 Q1-Q43 grilling 并授权按计划实施；E4 进入实施中，删除旧输入仍未授权。

## 3. 最终目标边界

```text
局域网浏览器
    -> 一个 FastAPI 进程（前端静态文件、认证、业务、SSE、SQL runner）
       -> 一个 MySQL 实例 / 一个数据库（全部业务事实和唯一写权威）
       -> Chroma adapter（只保存可重建 RAG chunks/metadata/vectors）
       -> 本地模型、Embedding、Reranker
```

固定规则：

- 默认单机、低并发；SQL runner 默认并发固定为 1。
- MySQL 保存用户、会话、refresh、撤销、角色、审计、聊天、笔记、原始知识、图片、Skill、job、generation 和迁移映射。
- Chroma 不承担业务权威，不向 SQL 写向量 BLOB；Chroma 故障时从 SQL 原文异步重建，查询期间返回结构化 `degraded/503`。
- Redis 只允许作为迁移期/开发期临时状态，不能参与登录、会话、refresh、撤销或任何正确性判定，完成过渡后删除。
- Django 只允许作为临时登录/刷新适配和只读观察层，FastAPI 切换稳定后删除运行链路。
- 本地 debug/import/export/rollback 通道开发期默认开启、正式部署可关闭；必须显式调用、写审计、不可自动 fallback。
- Skill 只支持根目录 `SKILL.md` 的目录/ZIP 导入和 A/B 能力；C 级、`scripts/`、网络、secret、外部进程和 MCP 只保留接口并返回结构化 `unsupported`。
- 未经对账、备份、停写和用户批准，不得删除旧表、旧文件、MD5 sidecar、Django、Redis 或旧 Chroma generation。

## 4. 唯一执行路径

本手册使用 `E` 作为交接批次编号；主计划使用 `AR/SK`，蓝图使用 `S`。以下是唯一允许使用的对照，阶段状态只在主计划中更新一次：

| 交接批次 | 蓝图/前置标识 | 主计划阶段 | 责任边界 |
|---|---|---|---|
| E0 | S0 | 文档收束（无 AR 实施） | 文档、决策和冻结；已关闭 |
| E1 | AR-0/SK-0（S0 之后的前置证据） | AR-0 + SK-0 | 真实依赖、故障注入、备份恢复和 characterization；已关闭 |
| E2 | S1 | AR-1 | 统一 MySQL schema、UoW、SQL durable job、单并发 runner、备份/恢复和迁移工具；已关闭，真实证据已收口，不迁移现有业务数据 |
| E3 | S2 | AR-2 | FastAPI 认证、会话、撤销、角色分离和完整授权审计；已关闭 |
| E4 | S3 | AR-3 | 业务源数据迁移、稳定 ID/FK、FastAPI 唯一写权威和旧输入对账；实施中 |
| E5 | S4 | AR-4 | SQL 原文 + Chroma RAG projection、generation、重建和降级合同 |
| E6 | S5 | AR-5 / SK-1..3 | Codex Skill 目录/ZIP、规范化 manifest、授权发布和 Legacy 对账 |
| E7 | S6 | AR-5 | 知识、笔记、聊天回接和文件/sidecar 权威清理 |
| E8 | S7-S8 | AR-6 | 删除过渡依赖、单机部署、恢复验收和最终证据 |

`E2` 必须在 `E3` 之前交付 SQL job/UoW/runner；`E4` 才执行业务数据迁移。`E6` 与 `E7` 都属于 AR-5 的不同交付面，不能被解释为两个独立的授权或写权威阶段。

```text
E0 文档交接与冻结（已关闭）
  -> E1 AR-0/SK-0 真实依赖与恢复证据（已关闭）
  -> E2/AR-1/S1 单 MySQL schema + SQL job/UoW/runner（已关闭，真实证据已收口，并发 1）
  -> E3/AR-2/S2 FastAPI 认证、会话、撤销和角色审计（已关闭）
  -> E4/AR-3/S3 业务数据迁移与唯一写权威（实施中）
  -> E5/AR-4/S4 SQL 原文 + Chroma RAG projection 收敛
  -> E6/AR-5/S5 Codex Skill 标准化、授权和发布
  -> E7/AR-5/S6 知识、笔记、聊天回接与文件权威清理
  -> E8/AR-6/S7-S8 删除过渡依赖、单机部署、恢复验收
  -> SKILL-GATE -> ARCH-GATE -> 解冻产品工作包
```

不得并行推进两个有数据写入或权威切换的阶段。测试、盘点、文档和隔离 fixture 可以并行，但只能由当前阶段负责人合并结论。每阶段状态必须按 `草案 -> 待你确认 -> 实施中 -> 待验证 -> 已关闭` 流转；出现外部阻塞使用 `阻塞`，解除后回到 `待你确认`。

## 5. 阶段执行细则

### E0/S0：文档交接与冻结（已关闭）

交付：本手册、蓝图、主计划、模板、归档索引和 q85-q92 决策记录。  
未做：任何代码、迁移、删除、部署切换。  
交接结果：E1 批次目录、owner/approver、隔离环境、备份和恢复证据已建立，并于 2026-08-27 经用户确认关闭。

### E1：AR-0/SK-0 真实依赖与恢复证据（已关闭）

入口：E0 文档交接完成；现有 P0 fixture 可复跑。  
任务：

1. 准备用户批准的隔离 MySQL、Chroma 持久目录、模型/Embedding 和当前 FastAPI + 观测/测试桩拓扑；记录版本、端口、路径和责任人。不得在本阶段实现或启用 durable runner。
2. 复跑 P0-1 至 P0-5；执行 Chroma 损坏、权限错误、版本不兼容、collection 缺失、进程重启五类故障注入。
3. 证明原 Chroma 目录不变、健康 generation 不被覆盖、恢复通过 staging 和 manifest/digest 校验；失败时 RAG 返回 `degraded/503`。
4. 对隔离 MySQL、Chroma 和所有受保护输入各做一次备份、恢复、完整性校验和 restore-forward 演练。
5. 补齐威胁模型、API/UI/Prompt/route characterization、跨平台限制和负责人/批准人字段。

禁止：连接或修改现有业务数据库；执行迁移；删除旧目录；实现 AR-1 worker；以 fixture 或绿色 unit test 代替真实等价证据。  
退出：真实依赖、故障注入、备份恢复和证据表齐全，用户确认后关闭 `AR-0 + SK-0`，才可进入 E2。

关闭：2026-08-27，用户明确确认 E1 关闭；证据位于 [`project_changes/2026-08-27-e1-ar0-evidence/`](../project_changes/2026-08-27-e1-ar0-evidence/)。关闭不代表真实模型质量、后续 AR 阶段或发布门禁通过。

### E2：AR-1/S1 单 MySQL schema、UoW、durable job 与内置 runner（已关闭）

入口：E1 已关闭；E2 批次范围、owner/approver、专用隔离 MySQL、备份位置和回滚边界已获用户批准。代码、本地合同和真实隔离证据已完成，用户于 2026-08-28 批准关闭；这些证据仍不授权 E3/E4 业务 migration。
任务：

1. 设计同一实例/同一数据库的统一表：`users`、`sessions`、`revocations`、`roles`、`audit`、`jobs`、聊天/笔记/知识源、`skill_packages`、`skill_versions`、`rag_generations`、`migration_maps` 等。
2. 统一稳定 UUID、FK、唯一约束、删除策略、时间字段、revision/digest 字段和审计关联 ID。
3. 提供 Alembic migration、空库初始化、现有表只读盘点、dry-run、行数/digest 对账和暂停/重放工具；启动只校验 revision，不自动 DDL，且不迁移现有业务数据。
4. 将 job 状态、幂等键、claim、lease、heartbeat、fencing、retry、cancel、DLQ、backpressure 全部落 SQL；内置 runner 默认并发固定为 1，进程重启后以 SQL 为准恢复。
5. 把 SQL dump、恢复、manifest 校验、差异报告、runner kill/restart 测试和回滚命令写入本阶段记录。

禁止：在未备份和未批准的现有库运行 migration；双写长期化；让文件、Redis、Chroma 或 Registry 成为表外权威。  
退出：空库、快照库和恢复库的结构/行数/digest/约束对账通过；runner 的重复、租约、fencing、kill/restart、重试和 DLQ 证据通过；失败保留旧表只读并恢复快照。

关闭：2026-08-28，用户明确回复 `批准关闭 E2`；两个 E2 容器已停止，volume、network 和全部证据保留。关闭不授权 E3/E4 业务 migration。

### E3：AR-2/S2 FastAPI 认证、会话、撤销和角色审计（已关闭）

入口：E2 schema 和恢复证据关闭。  
任务：

1. 将用户、密码 hash、refresh、token version、session、revocation 和角色导入 MySQL；FastAPI 成为唯一写入口。
2. 先 shadow 校验旧 Django 结果，再切换 login/refresh/logout/revoke；切换窗口保留只读 Django adapter，不产生双写。
3. 实现内容/Skill 管理员与安全管理员分离；`grant approve` 与 `grant revoke` 不得由同一审批动作自动完成。
4. 每个授权、撤销、策略、RunBinding、恢复和本地运维操作记录 actor/role、scope/owner、版本/digest、before/after revision、grant diff、reason、effective/expiry、result/error、correlation ID 和关联 job/run/import ID。
5. 撤销、过期、digest/revision 漂移、重放、延迟确认和 worker 重启必须对新 Run、排队 job 和确认动作 fail-closed。

退出：登录/刷新/注销/撤销双路径抽样一致；Redis 丢失不放行；API、runner、恢复和审计可按 correlation ID 对账。失败只切回已批准的只读适配，不恢复双写。

当前批次记录：E3 本地实现、测试用户迁移、角色/审计、浏览器验证和 restore-forward 已完成；用户于 2026-09-01 明确回复 `批准关闭 E3`，批次已关闭。证据位于 [`project_changes/2026-08-31-e3-ar2-fastapi-auth/`](../project_changes/2026-08-31-e3-ar2-fastapi-auth/)。本次关闭不授权或启动 E4。

### E4：AR-3/S3 业务数据迁移与唯一写权威

入口：E2 schema/UoW/runner 和 E3 user/session context 均关闭；用户于 2026-09-02 完成 E4 计划审阅并授权实施。当前按独立 allowlist、preflight、backup 和分批 gate 推进；不授权删除旧输入。
任务：

1. 在同一 MySQL 实例/数据库内完成业务分表过渡：用户、会话、聊天、笔记、知识源、图片、Skill 和迁移映射使用稳定 UUID/FK/审计关联。
2. 先对只读旧输入执行 dry-run、行数/digest/唯一约束对账和差异处置；所有迁移命令、停写窗口、备份位置和批准人写入阶段记录。
3. 分阶段切换 FastAPI 为唯一业务写入口；Django、旧脚本和文件只读或显式 debug/import/export，不产生长期双写。
4. 迁移后的 API、SSE/polling 和 runner 只展示/提交 SQL 事实；Redis pending 状态不得替代 job 或业务正确性。
5. 对 kill/restart、租约过期、重复/乱序、超时、取消、异常和孤儿 job 做迁移后回归；旧 fencing token 不得提交结果。

退出：迁移后业务行数/digest/约束/审计对账通过，FastAPI 单一写权威抽样通过，重复执行幂等，失败进入可重试或 DLQ，API 核心 readiness 不受 runner 崩溃影响；失败恢复迁移前快照，不删除旧输入。

### E5：AR-4/S4 SQL 原文与 Chroma RAG projection 收敛

入口：E2 schema/runner、E3 user/session context、E4 业务源数据和隔离 Chroma。  
任务：

1. SQL 保存原始知识/笔记、业务 metadata、切片配置、embedding fingerprint、当前 generation、job 和错误信息；不保存向量 BLOB。
2. RAG core 只依赖抽象 port；Chroma adapter 统一返回 `documents`、`scores`、`source_ids`、`generation`、`status`、`degraded_reason`。
3. collection 按 `index_kind + embedding_fingerprint + generation` 隔离；同配置可按 `user_id` metadata 过滤，不同向量空间不得混用。
4. 参数或 embedding 变化创建 staging generation；校验通过后原子激活并立即删除旧 generation，不保留历史 generation。
5. Chroma 故障只触发 SQL job 重建；查询请求不做同步重建，期间返回结构化 `degraded/503`，登录和会话继续工作。

退出：正常向量查询、HyDE/BM25/笔记检索、重排、用户自定义切片/检索配置、故障重建、对账和旧 generation 清理通过。失败不得删除原目录或覆盖健康 generation。

### E6：AR-5/S5/SK-1..3 Codex Skill 标准化、授权和发布

入口：E3 授权审计、E4 业务写权威、E5 RAG 合同和 SQL runner 均关闭。  
任务：

1. 统一目录/ZIP 导入；根目录必须有 `SKILL.md`，frontmatter 至少有 `name`、`description`；未知字段原样保存但不解释、不授权。
2. SQL 保存 raw package、规范化 manifest、资源清单、版本、digest、安装状态、policy、grant、RunBinding 和审计；内部只保留一个规范化表示。
3. 新导入固定 `installed_disabled`；publish/activate/rollback 前重新校验 package digest、manifest、metadata、capabilities 和 revision。
4. 同 digest 导入幂等；同版本不同 digest 拒绝并要求人工决策；坏包不得 READY、ack 未完成事件或覆盖健康快照。
5. 保留 A/B 插口；C 级执行、网络、secret、外部进程、MCP 和 `scripts/` 返回结构化 `unsupported`，不在 API 进程执行 package 代码。
6. 从只读 Git/artifact/备份输入运行一次性 Legacy migrator，使用稳定 UUID 和永久 `legacy_identity_map`；不恢复旧 runtime，不保留旧 generation。

退出：目录/ZIP、恶意包、digest、重复、授权越权、approve/revoke、重启恢复、单包隔离、legacy 对账和导出重导入通过；失败保留旧健康版本。

### E7：AR-5/S6 知识、笔记、聊天回接与文件权威清理

入口：E3-E6 全部关闭。  
任务：

1. 回接知识、笔记、聊天和会话，使所有业务写入经 FastAPI -> MySQL。
2. 将原始文档、图片和必要 MD5/摘要纳入 SQL 业务表；文件系统只保留显式 debug/import/export 操作文件。
3. 做用户隔离、权限、审计、RAG generation、job 和历史数据逐项对账；旧文件和 sidecar 在处置清单中逐项标记保留/迁移/丢弃。
4. 本地 debug 通道默认开启但显式受开关控制；正式部署关闭后，业务路径不能因 SQL/Chroma 故障自动使用文件。

退出：核心 API/UI/RAG 回归、用户隔离、审计和恢复通过；任何未对账输入都禁止删除。

### E8：AR-6/S7-S8 删除过渡依赖、单机部署与恢复验收

入口：E7 关闭，用户批准删除清单。  
任务：

1. 先停写、备份、记录 active revision/generation，再删除 Django 运行链路、Redis 正确性依赖、旧 YAML/Registry/MD5/目录 adapter 和旧 Chroma generation。
2. FastAPI 直接托管前端构建产物；提供单机 install/start/stop/upgrade/rollback/recover runbook。
3. 在空库、恢复库和现有迁移后库分别执行启动、登录、会话、Skill、RAG、聊天、笔记和导出回归。
4. 记录单机 RPO/RTO、停写窗口、恢复后 digest/行数/generation/audit 对账和失败处理。

退出：`SKILL-GATE` 和 `ARCH-GATE` 所需证据齐全，用户确认后才解冻产品工作包和新功能。C 级、公网、HA 仍保持独立门禁。

E8 提交证据不等于门禁自动通过：实现者只能标 `待验证`，由审阅人核对证据，最终由用户分别确认 `SKILL-GATE` 和 `ARCH-GATE`。

## 6. 每阶段交付协议

每阶段必须创建 `project_changes/YYYY-MM-DD-<stage>-<topic>/`，包含：

- `plan.md`：目标、非目标、入口条件、任务、影响面、风险、退出条件、回滚、阻塞和用户确认。
- `change-log.md`：时间、commit/文件/schema、原因、影响、回滚点、负责人、证据路径；明确列出未做事项。
- `test-record.md`：平台/版本/拓扑、真实依赖或 fixture、命令、阈值、实际结果、日志、数据对账、负向测试、恢复、owner、approver 和限制。

证据 ID 使用 `<STAGE>-<NN>-<slug>`；状态只用 `verified-local`、`verified-live`、`blocked`、`not-run`。fixture、mock、历史日志和生成文件必须明确写出不能证明的内容。

## 7. 变更、评审和发布规则

1. 一个阶段只能有一个 `实施中`；没有上阶段用户关闭确认，下一阶段只能是 `草案`或`待你确认`。
2. 任何代码、schema、配置、迁移或删除变更先写计划，再实施；每个 commit 必须能回到一个阶段和一个证据 ID。
3. 未经用户批准，不得执行真实数据库 migration、表删除、文件删除、Chroma generation 删除、Django/Redis 下线或权限模型切换。
4. 每个写入阶段先做 dry-run 和备份，再做短暂停写切换；切换期间旧输入只读，目标表对账完成后才允许继续。
5. 发现 fail-open、未知 revision、digest 漂移、审计缺字段、孤儿无法解释、健康快照被覆盖、Chroma 原目录被删除或回滚不可执行时，立即停线并标 `阻塞`。
6. 回滚优先 restore-forward：停止写入、保存日志和快照、恢复最近健康快照、校验行数/digest/revision/generation/audit，再由用户决定重试或回退。
7. 禁止 `git reset --hard`、`git checkout --`、无目标的递归删除和用生成文件覆盖事实源；历史用户改动必须保留并在批次中归属。
8. 交接人不能自行把自己的阶段标为 `已关闭`；实现者提交 `待验证`，审阅人完成证据检查，用户确认后才关闭。

## 8. E2 执行与关闭审阅清单

审阅人按以下顺序核对，所有真实依赖操作已保留 preflight 和原始日志：

1. 保留已关闭的[E1 证据包](../project_changes/2026-08-27-e1-ar0-evidence/)、历史失败、事故记录、停止的容器、volume 和 network；不得清理或重写。
2. 依据[阶段执行记录模板](./stage-execution-record-template-2026-08-26.md)保留 E2 批次边界、owner/approver、专用隔离 MySQL、备份位置、回滚点、禁止连接的现有资源和 migration 开关。
3. 核对显式 `issue-preflight` 已验证 container/network/port/database/server UUID，且所有目标都在批准 allowlist。
4. 核对 E2 源库 dump/inventory/备份、空库 migration、runner 故障矩阵和恢复库 restore-forward 证据；确认未连接或迁移现有业务数据。
5. 继续保持产品功能、C 级 Skill、公网和 HA 冻结；E2 已由审阅人和用户收口，后续阶段仍须单独授权。

## 9. 交接完成判据

当前交接完成判据是 E1 关闭证据可追溯，E2 实现与 live 验证证据可审阅，并知道何时必须停止。判据为：

- 唯一入口、目标拓扑、数据权威、RAG/Skill 合同和阶段顺序已固定。
- 每阶段的输入、产物、测试、回滚、删除顺序和关闭责任已写明。
- 后续未收口项（E3-E8）和冻结范围未被 E2 完成声明覆盖。
- 归档文档不再出现在 `docs/` 一级目录。
- 文档链接和格式检查通过。
