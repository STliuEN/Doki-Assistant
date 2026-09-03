# E4/AR-3/S3 业务数据迁移与唯一写权威

日期：2026-09-02  
最近更新：2026-09-03（暂停后恢复准备）  
状态：实施中  
负责人：Codex  
审阅/批准人：用户  
用户确认：2026-09-02，用户完成 E4 grilling 并确认按本计划实施；授权包含分批 inventory、导入、停写窗口内切换和 FastAPI 唯一业务写权威，不授权删除旧输入。

## 执行授权与确认纪律

- **执行确认（已收到）**：用户对本计划作完整审阅后，以本轮 Q1-Q43 答案一次性授权 E4 计划内的开发、只读盘点、隔离演练、分批导入、停写和 FastAPI 切换。授权不覆盖未列入 allowlist 的资源、未知 server UUID、未知密钥版本、删除旧输入或后续 E5/E6/E7/E8 阶段。
- **验收确认（尚未发生）**：实现和证据完成后，本批只能先标为 `待验证`；用户第二次审阅并明确验收后，才可标为 `已关闭`。
- 分批 gate、checkpoint、暂停/恢复和回滚记录属于执行证据，不增加用户确认次数。
- 用户要求 Q41 由本执行者接手；Q42 确认按文档执行；Q43 要求参照 E0-E3 的状态机、证据、恢复和清理方式。

## 暂停/恢复记录

- 2026-09-03：按用户要求结束上一轮执行并记录收口；本轮收到“继续执行 E4 准备”后恢复，仅处理离线代码/文档证据。
- 恢复范围：修正 `E4Target` 已解析 tuple/list 的逐项校验，重跑 E4 守卫、inventory、路由回归和静态门禁，并把本地 v3 manifest 纳入证据索引。
- 恢复限制：不调用子智能体；不连接 MySQL、Django、Redis、Chroma 或未知 `mysqld.exe`；不执行 DDL、`migration_maps` 写入、停写、切换、删除或 GC。

## 0. 执行边界

本批对应 `E4 = S3 = AR-3`。E2/AR-1 与 E3/AR-2 已关闭，用户已确认本计划并授权进入实施。当前先执行文档回写、路由修复、受控 preflight、只读 inventory 和隔离演练；真实 source/target/restore 资源必须先通过独立 allowlist、身份核验和批次 gate。不得从默认端口、`.env` 或未知进程推断目标，不得在 allowlist 之外连接或写入业务资源。

本计划以以下文档为准：

- [架构重写计划](../../docs/architecture_rewrite_plan.md)
- [架构重构执行交接手册](../../docs/architecture-execution-handoff-2026-08-26.md)
- [最终重构蓝图](../../docs/architecture-target-blueprint-2026-08-26.md)
- [E2 Schema Ownership](../2026-08-28-e2-ar1-sql-foundation/schema-map.md)
- [E3 关闭记录](../2026-08-31-e3-ar2-fastapi-auth/plan.md)

## 1. 目标

- 建立受控的业务 source inventory，覆盖 MySQL 旧表、FastAPI 现有业务表、Django/媒体输入、Chroma SQLite/collection、MD5 sidecar、图片目录和 Skill Storage。
- 固定 `ShortUUID/legacy id -> canonical lowercase UUID` 的 `migration_maps` 规则，先发现 unknown、orphan、duplicate 和 digest conflict，再允许导入。
- 对聊天、笔记、记忆、知识源、图片、模型配置、Skill 及其关联对象设计 additive/shadow 过渡；保留旧输入，避免原地重写 populated 主键。
- 设计 FastAPI 唯一业务写权威的 shadow、短暂停写、切换、审计和恢复步骤；事务提交后才产生派生 job，Redis/文件/Chroma 不构成业务成功依据。
- 为迁移后重复/乱序、租约过期、kill/restart、超时、取消、异常和孤儿 job 建立可重复的隔离验证矩阵。

## 2. 非目标

- 不执行真实业务数据库迁移、在线 dump、停写窗口、生产/局域网切换或任何删除。
- 不修改现有 populated 表的主键、`user_id` 类型、FK、删除策略、时间字段或内容存储，直到逐表 dry-run、备份、对账和用户授权完成。
- 不在本批激活或清理 Chroma generation；RAG port、generation 重建和旧 generation 处置属于 E5/AR-4。
- 不完成 Skill package 规范化发布、C 级执行或旧 Skill runtime 清理；E4 只盘点并迁移必要业务关联，规范化属于 E6/AR-5。
- 不删除 Django、Redis、MD5 sidecar、旧文件目录、旧 Chroma 或 Skill Storage；删除属于 E7/E8 且需要单独清单和确认。
- 不以 E3 的两个测试用户、E2 合成快照、SQLite/mock 或现有局部 service commit 证明 E4 已完成。

## 3. 入口条件与依赖

- E2/AR-1 已关闭：统一 schema、UoW、SQL job/runner、备份/restore 证据可审阅；E2 只使用合成/隔离数据，未迁移现有业务数据。
- E3/AR-2 已关闭：`users`、`auth_sessions`、角色、审计和 `migration_maps` 的认证上下文可用；旧 session/refresh token 不在 E3 迁移范围。
- 当前应用要求精确 Alembic head `20260901_0007_e3_auth`；E4 目标 revision、allowlist、target/restore 拓扑尚未建立。
- 真实 source 只能来自用户批准的只读 dump 或脱敏离线副本；不得从 `.env` 猜测目标，也不得复用 E1/E2/E3 容器、volume、network 或凭证。
- 在进入实施前必须补齐 owner/approver、目标 MySQL server UUID/数据库、备份位置、停写窗口、迁移开关、restore-forward 负责人和允许的源输入清单。

## 4. 业务范围与过渡方向

| 领域 | 当前输入/风险 | E4 目标方向 | 后续阶段边界 |
|---|---|---|---|
| 用户关联上下文 | canonical `users` 已有；业务表仍使用 `String(36/64)` 或旧 ShortUUID | 先建立身份映射和 shadow UUID 列/映射视图，再加 FK | E3 认证已关闭；不迁移旧 token |
| 聊天/会话/消息 | `chat_sessions.user_id` 无物理用户 FK；`chat_messages.id` 为整数 | 保留旧行，生成 canonical session/message UUID 和 parent FK，记录旧 ID 映射 | API/SSE 回接需通过 FastAPI 事务 |
| 笔记/记忆/模板 | 用户 ID 无 canonical FK；笔记写入后另起异步 Chroma/记忆副作用 | 先对账原文/metadata，再以 SQL 事务和 durable job 接管 | RAG projection 激活留 E5 |
| 知识源/图片/MD5 | `content_blob` 与文件、MD5 sidecar、Chroma metadata 可能分裂 | SQL 保存原始文档/摘要/图片元数据；sidecar 只作为可追溯输入 | 文件清理留 E7/E8 |
| 模型/embedding 配置 | 用户 ID 类型不一致，配置影响 RAG generation | 固定 owner UUID、配置 digest/revision 和迁移关联 | generation 构建留 E5 |
| Skill | SQL Skill 表与 content-addressed Storage 并存，RunBinding 仍有旧 ID 宽度 | 迁移必要 owner/run/audit 关联和 legacy map，不宣称 package 发布完成 | 规范化导入/发布留 E6 |
| Chroma | `chroma.sqlite3` 是派生投影，collection 与旧用户标识并存 | 只读 inventory、建立 source-to-target 关联；不把向量当业务事实 | 重建/切换/删除留 E5 |
| Django/Redis/文件 | 仍可能存在旧写入口或 pending/cache 状态 | 先盘点并封闭写入口，保留只读/debug 显式通道 | 删除/下线留 E7/E8 |

## 5. 任务清单

- [x] `E4-PREP-01`：审阅权威文档、E2/E3 关闭证据和阶段模板，冻结状态/授权/退出规则。
- [x] `E4-PREP-02`：静态盘点当前 SQLAlchemy/Django 模型、业务 service commit、文件/MD5/Chroma/Skill 写入口，登记差异。
- [x] `E4-PREP-03`：只读观察仓库内 `backend/data` 的 Chroma collection、MD5 sidecar、图片目录和 Skill Storage，结果只作为待核验 source inventory。
- [x] `E4-PREP-04`：盘点 Django、FastAPI service、文件/MD5/Chroma/Skill、Redis 和 job/runner 写入口，登记唯一写权威差异。
- [x] `E4-PREP-05`：建立停写、备份、隔离演练和 restore-forward runbook，保持真实参数为空。
- [x] `E4-PREP-06`：复核本地派生数据身份/范围冲突和临时路径泄露，将未决项登记为阻断或待确认，不修改运行代码。
- [x] `E4-PREP-07`：复核 API 写入口路由，并补齐 batch/entity/artifact digest、加密配置 key、媒体 SQL 表和 reranker/calibration 权威归属的准备约束。
- [x] `E4-PREP-08`：将 E4 流程状态与现有 `migration_maps` 三态约束对照，登记 schema 兼容门槛和禁止越界写入规则。
- [x] `E4-PREP-09`：暂停后恢复 E4 准备；修正 allowlist dataclass 快速路径校验，重跑回归/静态门禁，并登记脱敏本地 manifest v3 及其 digest。
- [ ] `E4-01`：在已批准且通过 allowlist 的 source 副本上生成完整 inventory manifest（表/列/行数/源 digest/时间窗/权限证明）。当前先完成本地非业务资源的只读 manifest，在线/外部 source 仍需独立身份核验。
- [ ] `E4-02`：执行身份映射 dry-run；对 unknown/orphan/duplicate/identity conflict 全量 fail-closed，生成 `migration_maps` 候选和冲突报告。
- [ ] `E4-03`：逐表完成 additive/shadow schema 设计、唯一约束/FK/on-delete/时间和内容 digest 评审；不得原地改变 populated 主键。
- [ ] `E4-04`：建立独立 E4 target/restore allowlist 和备份 preflight；在合成/脱敏 fixture 完成迁移器幂等、重放和差异处置。
- [ ] `E4-05`：在用户批准停写窗口后，执行源只读、短暂停写、目标导入、行数/digest/约束/审计对账；失败只走 restore-forward。
- [ ] `E4-06`：分领域切换 FastAPI 唯一业务写入口；Django/旧脚本/文件改为只读或显式运维操作，禁止长期双写。
- [ ] `E4-07`：验证 API、SSE/polling、runner、重复/乱序、租约、kill/restart、超时、取消、异常和孤儿 job；SQL 事实必须可按 correlation ID 对账。
- [ ] `E4-08`：实现者提交 `待验证`，审阅人核对证据；用户第二次验收确认后才可将 E4 标为 `已关闭`。

## 6. 当前静态发现

- `chat_sessions` 使用 `String(64)` 的 `user_id` 且没有到 `users` 的 FK；`chat_messages.id` 仍是整数，不能直接当作 canonical UUID。
- `knowledge_source_documents` 使用 `String(64)` 的 `user_id`，保存 `content_blob`，只有 `(user_id, md5)` 本地唯一约束，没有用户 FK。
- `notes`、`memory_items`、`note_templates` 的用户 ID 为 `String(36)`，`user_model_configs`/`user_embedding_configs` 为 `String(64)`，均未形成 canonical `users.id` 的物理 FK。
- `SkillRunBinding.user_id/session_id` 为 `String(64)`；Skill 领域写入和旧 Storage/目录输入仍需逐项映射。
- `note_service.py`、`knowledge_document_service.py`、`database_session_manager.py` 等服务直接 `commit()`；笔记/知识写入与 Chroma、图片/MD5、自动标签/记忆等副作用不在同一 SQL 事务内，需在 E4 设计 after-commit job 边界。
- 本地只读观察到一个用户旧 ShortUUID `j6BVY9AHmHPQEbwoZabRMq` 出现在 MD5/Chroma metadata；这不是已批准的身份映射，也不能直接写入目标。
- Chroma 用户作用域 collection 名称后缀 `e5efbb90a85fadbf` 与 metadata/sidecar 的旧用户 ID 不一致，且 RAG metadata 含本机临时绝对路径；在 source manifest 证明前按 `scope_conflict` 和敏感路径脱敏问题处理。
- Legacy 32 位 MD5 只保留为历史内容标识，不能代替 `migration_maps.source_digest` 的 64 位小写 SHA-256；正式 inventory 必须同时记录两种 digest。
- `backend/data/reranker_config.json` 与 `backend/data/routing_calibration/` 目前只有本地配置/派生候选身份，未证明为 SQL 业务权威；不得由请求路径或迁移器隐式加载。
- `note_template_router.py` 的具体 `PUT /note-template/reorder` 路由注册在通用 `PUT /note-template/{template_id}` 之后，静态路由解析会优先命中通用路径；该缺陷必须在 E4 写权威切换前修复并回归验证。
- 当前 E3 `migration_maps` schema 只允许 `mapped/conflict/error`，而 E4 流程还需要 candidate/validated/imported/reconciled/orphan/excluded；必须先决定受控状态字段/旁表或 inventory-only 状态，不能直接写入未支持的值。

## 7. 风险与保护

- **误连或越权**：任何未列入 E4 allowlist 的 host/port/database/server UUID、Django 在线写路径或 Redis/Chroma 写操作，立即停止并标 `阻塞`。
- **身份错配**：未知 ShortUUID、重复邮箱/电话、同源 ID 多 digest、跨用户 MD5 冲突或孤儿外键不得自动合并、覆盖或猜测。
- **数据漂移**：source digest 在 dry-run 与导入间变化，或停写窗口外仍有写入，必须重新备份并从头对账。
- **摘要混用**：把 MD5、batch manifest digest、entity content digest 或 archive digest 混写到同一字段会破坏幂等和恢复判定，必须分层记录并逐层核对。
- **事务分裂**：SQL commit 成功而文件/Chroma 失败时，业务响应只能依据 SQL；派生任务进入 durable job，不能回写“成功”或依赖 Redis pending。
- **主键/FK 破坏**：不得在 populated 表上直接 downgrade、缩短/扩大类型或级联删除；先 additive/shadow、回填、校验、切换，再另行申请清理。
- **恢复失效**：备份 manifest、revision、行数、digest、audit 或 restore-forward 任一项无法验证，停止切换并保留旧输入只读。
- **密文不可恢复**：`api_key_encrypted` 未绑定 key version 或无法在隔离 fixture 解密时，不得盲目复制密文；必须先完成重加密/轮换和失败处置设计。
- **媒体表示缺失**：没有明确图片/媒体 SQL 表、字段、digest 和删除策略时，不得把文件路径或空目录当作已迁移媒体。
- **路由写入口冲突**：具体业务写路由被通用路径吞掉时，切换验证立即阻断，禁止以错误成功响应计入写权威证据。
- **映射状态越界**：E4 流程状态若超出当前 `migration_maps` check constraint，必须在隔离 schema 设计中显式处理；禁止绕过约束、改写 E3 既有数据或把状态塞进未定义文本字段。

## 8. 退出条件

- [ ] 业务 source/target/restore inventory、源 digest、行数、唯一约束、FK、时间和 audit correlation 对账通过。
- [ ] 所有业务用户/会话/对象均有唯一、可重放的 `migration_maps`；unknown/orphan/duplicate 已处置并有审阅记录。
- [ ] FastAPI 唯一业务写入口抽样通过；Django、旧脚本和文件无未登记业务写入，长期双写为零。
- [ ] API/SSE/polling/runner 只提交和展示 SQL 事实；Redis 丢失不影响正确性，核心 readiness 不依赖 runner 存活。
- [ ] 重复执行幂等；租约过期、旧 fencing token、kill/restart、超时、取消、异常和孤儿 job 均按预期 fail-closed/重试/DLQ。
- [ ] 失败恢复到迁移前健康快照的 restore-forward 已实际演练；旧输入仍保留，未授权删除为零。
- [ ] 实现者提交 `待验证`，审阅人完成证据检查，用户明确确认关闭。

## 9. 回滚方案

实施阶段才允许使用真实命令，并须把实际命令、时间、负责人和证据 ID 写入 `test-record.md`。预定顺序如下：

1. 停止 E4 runner 和所有目标写入，保留服务日志、active revision、migration batch、job/attempt/audit 快照。
2. 校验迁移前 dump/bundle manifest、SHA-256、目标 server UUID 和 schema revision；禁止覆盖源库或健康快照。
3. 将快照恢复到独立 restore-forward 目标，重新核对表/行数/content digest/唯一约束/FK/audit/correlation/migration map。
4. 保留故障目标只读供审阅；由用户决定修复后重试或回退。不得通过 populated downgrade 或删除旧输入“修复”。
5. 只有 E4 证据完整、用户另行批准后，才允许进入后续 RAG/Skill/文件处置阶段。

## 10. 未完成与阻塞

- 用户确认：执行确认已收到；真实 E4 target、在线业务源、停写和切换仍须各自通过本计划的 allowlist/preflight/backup/gate，验收确认尚未发生。
- E4 allowlist/topology：未建立；不能复用 E1/E2/E3 资源或凭证。
- source snapshot：未提供用户批准的只读 dump/脱敏离线副本；本地 `backend/data` 只能做静态观察。
- 本地准备 manifest：已生成脱敏、离线只读 `artifacts/local-inventory-v3.json`；它只证明本地文件观察，不替代批准的业务 source inventory，也不改变 `E4-01` 的 `not-run` 状态。
- identity policy：已确认关键 orphan/重复/跨域冲突 fail-closed，非关键问题可 quarantine；逐表处置仍是执行 gate。
- schema policy：最终数据库 additive/shadow 方向已确认；shadow 列/映射表、message ID、content digest、媒体 SQL 表和 on-delete 仍须逐表 gate。
- digest/配置 policy：三层 digest 分离、用户/Embedding 入 SQL、reranker 版本化配置和 key-version 未确认不迁移密文均已确认；具体字段承载和重加密验证仍是 gate。
- migration map schema：采用 additive 扩展或受控旁表，保留 E3 既有三态兼容；具体 DDL 和审计关联仍是 E4-03 gate。
- known code blocker：`PUT /note-template/reorder` 路由冲突已修复并通过 `E4-ROUTE-01`；业务写权威切换仍需后续 gate。
- owner/approver/runbook：执行者接手已确认；停写实际开始/结束、备份位置、restore-forward 负责人和验收人随批次 runbook 填写。

## 11. 用户确认记录（2026-09-02）

本轮用户确认摘要：Q1 完整授权；Q2/Q9 采用在线只读并直接建立最终数据库 canonical shadow；Q4 纳入聊天/会话、笔记/模板、记忆、知识源/原始字节、图片/媒体、MD5、模型/Embedding 配置及必要 Skill 关联，Skill 完整发布交 E6；Q5 固定 UUID/UUIDv5 并复用 E3 `users.id`；Q6/Q11 关键身份、FK、内容、权限、唯一约束、审计和跨域引用 fail-closed，非关键问题可 quarantine；Q7 FastAPI 唯一业务写入口，Django/旧脚本/文件只读；Q10 分批执行并记录文档和过程；Q12/Q27 原始文档和媒体进入 SQL，字节级一致；Q13/Q37 用户/Embedding 入 SQL、reranker 保持版本化配置、key-version 未确认不迁移密文；Q14/Q32/Q36 冻结完整 Skill 输入接口，E6 不重构输入接口；Q18/Q29 修复 reorder 路由；Q19/Q28 additive 扩展 `migration_maps`；Q20 Chroma 作用域冲突交 E5；Q23-Q25 快照、checkpoint、稳定排序和幂等批次；Q26 密文问题仅 quarantine 配置域；Q30 每项先更新计划并关联证据/回滚点；Q31/Q33/Q40 仅两次确认；Q34/Q43 所有 E 阶段结束验收后统一清理中间材料；Q35 不增加 3306 特殊保护但执行通用身份核验；Q38/Q42 不设固定停写时长，记录实际开始/结束并以 gate 失败阻断；Q39 批次大小由 inventory 决定；Q41 当前执行者接手。

执行确认语义：`批准 E4 计划并按已确认范围实施（含导入、停写和 FastAPI 切换；不删除旧输入）`。验收确认尚未发生。

## 12. 当前清理策略

阶段内保留成功、失败、无效和历史测试体及恢复现场，不提前清理。所有 E 编号完成并通过最终验收后，按 E0-E3 记录执行统一清理：移除原始敏感 source、临时 fixture、可重建中间体和完整环境快照；保留脱敏 manifest/inventory、审计、摘要、错误报告、备份、restore-forward 和回滚证据。该策略不授权删除旧输入、未对账源、健康快照或 E1-E3 保护资源。
