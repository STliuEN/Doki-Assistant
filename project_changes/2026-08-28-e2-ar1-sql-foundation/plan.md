# E2/AR-1/S1 统一 SQL 基础与 durable runner

日期：2026-08-28  
状态：待你确认  
负责人：Codex 架构重构协作代理  
审阅/批准人：用户  
用户确认：2026-08-28 用户授权审阅执行计划并准备下一批 execution；该授权仅覆盖文档、静态代码盘点和只读环境核对。E2 实施、容器创建、AR-1 代码/schema 变更、migration 和任何数据库写入仍为 pending。

## 审阅结论

E1/AR-0/SK-0 已于 2026-08-27 经用户确认关闭，证据位于 `project_changes/2026-08-27-e1-ar0-evidence/`。E2 是唯一下一阶段，但在本计划获单独确认前不得从 `待你确认` 转为 `实施中`。

现行总体计划方向正确，但实施前必须补齐以下约束：

1. E2 只创建和验证加法式目标结构、UoW、SQL job 与 runner，不迁移现有用户或业务数据，不切换认证和业务写权威。
2. “快照库”默认只能是 E2 合成数据或经用户另行批准的脱敏离线副本；不得读取 `backend/.env` 后连接本机 `3306` 或任何现有业务库。
3. job 语义固定为 at-least-once claim 加 fenced/idempotent commit，不宣称 exactly-once。
4. MySQL DDL 回滚以备份和 restore-forward 为准；Alembic downgrade 只允许在 E2 空库/合成库验证，不作为已填充数据库的恢复手段。
5. E1 移交的真实业务 UI E2E 不属于 E2：登录/认证在 E3，业务写路径在 E4，RAG 成功流在 E5。E2 只验证 schema bootstrap/revision gate、UoW、runner 和恢复。

## 目标

- 冻结一个无命名漂移的目标 schema map，覆盖 `users`、认证会话/refresh/revocation、角色、审计、durable jobs、现有 domain、Skill、RAG generation 和 legacy identity mapping。
- 提供加法式 Alembic revision 和空库 bootstrap；启动只校验 revision，绝不自动执行 DDL。
- 提供明确事务边界的 UoW，使业务事实与 job enqueue 能在同一 SQL transaction 中提交或一起回滚。
- 实现 SQL job repository 与内置 runner，默认并发固定为 1，覆盖 claim、lease、heartbeat、fencing、幂等、retry、cancel、DLQ 和 backpressure。
- 提供 dry-run、只读 schema inventory、SQL dump manifest、恢复、结构/行数/digest/约束对账和 kill/restart 证据。
- 为 E3/E4 提供稳定的结构和迁移接口，但不提前接管认证或迁移业务数据。

## 非目标

- 不连接、读取、迁移、修改或删除现有 MySQL、Django user DB、Redis、Storage、文件/MD5 sidecar 或 Chroma。
- 不把 E1 容器、volume、network 或证据资源复用为 E2 写入目标，也不清理这些资源。
- 不切换 FastAPI/Django 认证，不导入真实用户/session/refresh/revocation，不改变当前 API/UI 业务行为。
- 不迁移现有聊天、笔记、知识、图片、Skill 或 Chroma 数据，不建立长期双写。
- 不实现 AR-2 审批/撤销闭环、AR-3 唯一业务写权威、AR-4 RAG generation 行为或 AR-5 Skill 回接。
- 不实现多实例、HA、公网、C 级 Skill 或并发大于 1 的 runner。
- 不以 Alembic downgrade、测试 fixture 或绿色单测替代备份恢复和真实隔离 MySQL 证据。

## 依赖与入口条件

- 上一阶段关闭证据：E1 `plan.md`、`test-record.md`、`change-log.md` 均为 `已关闭`；权威计划和交接手册一致。
- 固定准备基线：分支 `ai_document_assistant`，HEAD `33a8054dedd62745fb9fe0528efa2880a5fcc8a8`；准备开始时工作树干净。
- E1 保护资源：`doki-e1-20260827-mysql*` 容器保持 stopped，两个 E1 volume 和 `doki-e1-20260827-net` 保留；E2 禁止复用、启动、修改或清理。
- 拟议 E2 隔离拓扑（待批准后才创建）：

| 用途 | 拟议资源 | 端口/数据库 | 写入边界 |
|---|---|---|---|
| schema/runner 源库 | `doki-e2-20260828-mysql` + `doki-e2-20260828-mysql-data` | `127.0.0.1:33317` / `doki_e2` | 只允许 E2 合成数据 |
| 恢复验证库 | `doki-e2-20260828-mysql-restore` + `doki-e2-20260828-mysql-restore-data` | `127.0.0.1:33318` / `doki_e2` | 只接受已校验 E2 bundle |
| 隔离网络 | `doki-e2-20260828-net` | Docker bridge | 只连接上述两个容器 |
| 证据/备份 | `project_changes/2026-08-28-e2-ar1-sql-foundation/artifacts/` | 仓库内 E2 合成证据 | 不存 secret，不含现有业务数据 |

- 允许的数据库目标必须同时满足资源名、loopback 端口和数据库名 allowlist；`localhost:3306`、`127.0.0.1:3306`、E1 端口/volume、`backend/.env`、`DjangoUserService/.env` 以及未列出的 DSN 全部 deny。
- 实施前需用户明确确认：本计划、owner/approver、MySQL `8.4.x`、上述资源名/端口、备份位置、恢复目标、禁止资源和显式 migration 开关。

## 冻结合同

### Schema 边界

- `schema-map.md` 将成为 E2 的逐表/逐列评审产物，名称统一使用 `auth_sessions`、`refresh_tokens`、`token_revocations`、`roles`、`role_bindings`、`audit_events`、`jobs`、`job_attempts`、`rag_generations` 和 `migration_maps`；不得再混用 `sessions`/`migration_map`/`generations` 等含糊别名。
- 所有新主键使用 UUID 字符串的统一数据库表示；旧 `String(36/64)`、整数 ID 和 Django ID 只在后续映射表中记录，不在 E2 改写真实数据。
- 时间语义统一为 UTC、微秒精度；租约判断使用数据库时间，不使用 worker 本机时钟作为权威。
- digest 固定为 SHA-256；revision/fencing token 单调递增；JSON 字段必须有版本字段和大小边界。
- E2 migration 对现有表默认只允许兼容性的加法变更。会改变 populated legacy rows、类型、主键、FK 或删除策略的 DDL 只写入 schema map，延后到 E3/E4 的备份、dry-run 和停写窗口。

### UoW 原子边界

- 一个 UoW 拥有一个 `AsyncSession` 和一个明确 transaction；repository/service 不得在 UoW 内自行 `commit()`。
- domain write、audit/outbox/job enqueue 必须同事务成功或同事务回滚；外部文件、Chroma、模型和 Redis 不得参与提交判定。
- E2 先让新 job 路径完整使用 UoW，并生成现有内部 `commit()` 调用的迁移清单；把所有既有业务服务改写为 UoW 属于 E3/E4 回接，不在 E2 偷渡业务行为变更。
- post-commit 唤醒只是优化；进程重启后必须仅凭 SQL 找回工作。

### Job/runner 不变量

- 状态机：`queued -> leased -> running -> succeeded`；可恢复分支为 `retry_wait -> queued`，取消为 `cancel_requested -> cancelled`，耗尽重试或不可重试失败进入 `dead_letter`。终态不得重新 claim。
- claim、lease owner、lease expiry 和 fencing token 在同一 SQL transaction 更新；每次重新 claim 必须提高 fencing token。
- heartbeat 只能由匹配 `job_id + lease_owner + fencing_token` 的 runner 延长；过期 owner 的结果提交必须影响 0 行并记录拒绝。
- 同一 job type/owner 范围内的 idempotency key 唯一；相同 key 与相同 payload digest 返回同一 job，不执行第二次副作用；相同 key 但 digest 不同必须冲突拒绝。
- retry 使用有上限的确定性 backoff；最大尝试次数耗尽后进入 DLQ。DLQ replay 必须显式创建新的 attempt/revision 并保留来源关联。
- cancel 对 queued job 直接终止，对 running job 设置请求并由 cooperative checkpoint 确认；旧 worker 不能在取消或重新 claim 后提交结果。
- backpressure 依据 SQL 中可执行/租约 job 数量和配置阈值 fail-closed；不得以进程内队列长度为权威。
- runner 并发固定为 1；API readiness 与 runner liveness 分离，runner 崩溃不得伪造 API 写入成功。

## 任务清单

- [x] `E2-00` 核对 E1 关闭状态、Git 基线、E1 资源保护和 E2 禁止边界；产物为本批三份记录与 `current-sql-inventory.md`。
- [ ] `E2-01` 审阅并冻结已提交的 `schema-map.md` 草案：现有/目标表、列、ID/FK、唯一约束、删除策略、revision/digest、owner 阶段和 deferred DDL；完成判据为用户确认且无命名/阶段归属漂移。
- [ ] `E2-02` 增加加法式 SQLAlchemy models/Alembic revision、空库 bootstrap、head/model parity 和 unknown-revision fail-closed；不更新任何现有业务库。
- [ ] `E2-03` 实现 UoW/session ownership、transactional repository 和原子 job enqueue；新增 rollback/cancellation/constraint 测试。
- [ ] `E2-04` 实现 job schema/repository/state machine、数据库时钟 lease、heartbeat、fencing、idempotency、retry、cancel、DLQ 和 backpressure。
- [ ] `E2-05` 实现 FastAPI lifespan 内置单并发 runner、graceful shutdown、kill/restart 恢复和独立 liveness/readiness 观测；不接业务/RAG handler。
- [ ] `E2-06` 扩展运维脚本：只读 schema inventory/dry-run、`mysqldump --single-transaction`、manifest、空目标 restore、schema/row/digest/constraint diff 和显式 restore-forward。
- [ ] `E2-07` 在批准的 E2 源库、合成快照库和恢复库运行 migration/runner/恢复矩阵；记录每个故障点、阈值、实际结果和原始日志。
- [ ] `E2-08` 跑隔离完整 pytest、Ruff、OpenAPI、`uv lock --check`、文档检查和 scoped diff；实现者只提交 `待验证`，由用户确认后关闭。

## 预期代码与证据影响面

| 范围 | 预期路径 | 边界 |
|---|---|---|
| schema/models | `backend/app/models/`、`backend/alembic/versions/`、`backend/app/db/db_config.py` | 加法式；不自动 DDL，不迁移真实数据 |
| UoW/job | 拟新增 `backend/app/db/uow.py`、`backend/app/jobs/` | 只依赖 SQL；不依赖 Redis/Chroma/文件 |
| runner lifecycle | `backend/main.py` 及配置 | 并发 1；API readiness 与 runner 状态分离 |
| ops | `backend/scripts/` | allowlist、dry-run、manifest、restore-forward |
| tests | `backend/tests/` | SQLite 只作快速合同；MySQL 8.4 是最终 SQL 证据 |
| evidence | 本批 `artifacts/`、三份记录、schema map | 只含 E2 合成/批准离线数据 |

## 风险与保护

- 最大风险是再次读取 `.env` 误连现有资源。所有 E2 命令必须显式设置完整 DSN，并先运行 denylist/allowlist preflight；发现未列入目标立即停止。
- MySQL DDL 非完全事务化。每次 migration 前必须有可验证 dump，目标只允许 E2 隔离库；失败时停止写入并恢复到新的 restore 库，不覆盖原库。
- 当前两条 Alembic revision 只覆盖 FastAPI 18 张表，Django user 表在另一数据库；现有 ID 长度、FK 和 commit 边界不统一。E2 先形成兼容结构，不以一次大改消除差异。
- 当前 `skill_registry_events` 是局部 outbox，不具备通用 claim/lease/fencing/DLQ；不得直接把它宣称为 durable runner。
- `backend/scripts/backup_restore.py` 只封装和校验离线 dump 文件，不负责调用 mysqldump、导入或数据库语义对账；E2 必须补齐这些显式步骤。
- 任何 fail-open、自动 DDL、unknown revision、digest 漂移、孤儿 job、旧 fencing token 成功提交、审计缺字段、E1/现有资源被访问或恢复不可执行，立即标 `阻塞`。

## 退出条件

- [ ] `schema-map.md`、SQLAlchemy models 和 Alembic head 对应一致；空库、合成快照库和恢复库的结构/约束对账通过。
- [ ] UoW 原子提交/回滚、job enqueue 与 audit/outbox 同事务证据通过。
- [ ] runner 的 claim、lease、heartbeat、fencing、重复 enqueue、retry、cancel、DLQ、backpressure、kill/restart 和 graceful shutdown 均达到冻结阈值。
- [ ] SQL dump bundle、manifest/tamper rejection、恢复、行数/content digest/约束和 restore-forward 对账通过。
- [ ] 启动只校验精确 Alembic head；空库、旧 revision、未知 revision 均 fail-closed 且不执行 DDL。
- [ ] 真实依赖与 fixture/mock 边界明确；SQLite 结果不替代 MySQL 8.4 行锁、`SKIP LOCKED`、lease 或恢复证据。
- [ ] 现有业务资源、E1 容器/volume/network 和业务写路径未被修改；未执行项完整列出。
- [ ] 实现者状态先转为 `待验证`；审阅证据后由用户明确确认关闭。

## 回滚方案

1. 停止 E2 runner 和所有 E2 写入，保留日志、DSN allowlist 结果、active revision、job/attempt 快照和容器。
2. 验证最近 E2 dump bundle 的 manifest/digest；恢复到新的 `doki-e2-20260828-mysql-restore` 目标，不覆盖故障源库。
3. 对比 Alembic revision、表/索引/FK/唯一约束、行数、canonical content digest、job fencing/attempt 和 audit correlation。
4. 若恢复一致，保留故障源库只读供审阅；由用户决定 restore-forward、修复后重试或退回已批准 commit。
5. populated database 不运行破坏性 downgrade；任何容器/volume/证据清理另行申请。

## 当前未完成与待确认

- E2 实施授权：`pending`；需要用户明确回复确认本计划及拟议隔离拓扑。
- schema map：ownership、核心列和 deferred DDL 草案已提交；精确类型/索引/限额和 revision 拆分仍待用户审阅冻结。
- E2 MySQL/restore 容器与 volume：`not-created`。
- AR-1 代码、Alembic revision、UoW、jobs 和 runner：`not-started`。
- migration、dump/restore、kill/restart 和 MySQL 证据：`not-run`。
- 真实业务 UI、认证、业务迁移和 RAG E2E：分别归 E3/E4/E5，不是 E2 阻塞项。
