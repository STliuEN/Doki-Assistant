# E2 目标 Schema Ownership 草案

日期：2026-08-28  
状态：待你确认  
性质：设计草案，不是 Alembic revision，不授权 DDL 或数据迁移

## 目的

本草案消除 `sessions`、`generations`、`migration_map` 等命名和阶段归属歧义。E2 只负责目标结构、约束骨架、UoW/job/runner 与恢复；后续阶段才导入真实数据并切换行为。

## 全局约定

| 项目 | 提案 | E2 验证 |
|---|---|---|
| 业务主键 | canonical lowercase UUID，MySQL `CHAR(36)`；不把旧 ID 原地改写 | model/migration parity、格式约束、重复拒绝 |
| legacy identity | 统一写 `migration_maps`，使用 source system/entity/source ID -> target UUID | 唯一约束、digest、幂等重放 |
| 时间 | UTC `DATETIME(6)`、非空；租约以数据库时间为权威 | 时区/精度、DB clock lease 测试 |
| revision/token | 单调 `BIGINT`；fencing/revision 只由 SQL transaction 增长 | 并发 claim/CAS |
| digest | SHA-256 lowercase hex，`CHAR(64)` | payload/content mismatch fail-closed |
| JSON | 带 `schema_version` 和大小上限；不存任意可执行对象 | schema/size validation |
| 删除 | 默认 `RESTRICT`；仅真正 owned child `CASCADE`；审计引用优先 `SET NULL`/保留快照 | FK/on-delete contract |
| 审计关联 | 全链路 `correlation_id`，并可关联 run/job/import/migration ID | 索引、查询和恢复对账 |
| 向量 | SQL 不保存 embedding/vector BLOB | 静态 schema contract |

这些类型是待确认目标。旧 `String(36/64)`、Django 22 字符 ShortUUID、整数 message ID 和 nullable timestamp 在 E2 不做 populated-row 改写。

## Canonical 表名与 owner

| 表 | E2 结构责任 | 行为/数据 owner | E2 边界 |
|---|---|---|---|
| `users` | 建立空结构和唯一约束骨架 | E3 导入用户并切换认证 | E2 不写真实用户/密码 |
| `auth_sessions` | 建立空结构；明确不是 `chat_sessions` | E3 session 行为 | 不接 Django/Redis session |
| `refresh_tokens` | 建立 family/rotation/revocation 结构 | E3 refresh 行为 | 不签发或导入 token |
| `token_revocations` | 建立撤销事实结构 | E3 fail-closed 传播 | 不替换当前 Redis 路径 |
| `roles`、`role_bindings` | 建立角色与 binding 骨架 | E3 分权和审批 | 不授予真实权限 |
| `audit_events` | 建立通用 append-only 结构 | E3 起写授权审计；E4-E8 复用 | E2 仅写 runner/运维合成审计 |
| `jobs`、`job_attempts` | 完整结构、repository 和状态机 | E2 | 只接 deterministic/noop E2 handler |
| `migration_maps` | 建立稳定映射结构 | E3 用户、E4 业务、E6 Legacy Skill | E2 只验证合成映射 |
| `rag_generations` | 建立 generation/config/status 指针骨架 | E5 激活/rebuild/cleanup | E2 不连接 Chroma |
| `skill_packages` | 建立 raw package/digest/manifest 目标骨架 | E6 导入/发布/授权 | E2 不迁移 Storage 对象 |
| 现有 Skill 表 | 盘点并保持兼容 | E6 完成 package/grant 语义 | E2 不宣称现有 outbox 是通用 job |
| 现有 chat/note/knowledge/memory/config 表 | 盘点目标 UUID/FK/时间/delete 差异 | E4 迁移和唯一写权威 | E2 不改 populated keys/rows |

## 拟议基础列

以下是 schema review 的最小列集；精确 SQL 类型、索引名和长度在 E2-01 审阅后冻结。

### `jobs`

- identity：`id`、`job_type`、`owner_scope`、`correlation_id`。
- input/idempotency：`idempotency_key`、`payload_digest`、`payload_json`、`payload_schema_version`。
- scheduling：`status`、`priority`、`available_at`、`attempt_count`、`max_attempts`。
- lease/fencing：`lease_owner`、`lease_expires_at`、`heartbeat_at`、`fencing_token`。
- cancellation：`cancel_requested_at`、`cancel_reason`、`cancelled_at`。
- outcome：`result_json`、`error_code`、`error_detail`、`completed_at`。
- audit time：`created_at`、`updated_at`。

核心唯一约束为 `(job_type, owner_scope, idempotency_key)`；同 key 不同 `payload_digest` 必须冲突拒绝。claim 索引至少覆盖 `(status, available_at, priority, created_at)`。所有完成/失败/heartbeat/cancel transition 必须以 `id + status + lease_owner + fencing_token` 做 CAS。

### `job_attempts`

- `id`、`job_id`、`attempt_number`、`lease_owner`、`fencing_token`。
- `started_at`、`heartbeat_at`、`finished_at`、`outcome`。
- `error_code`、`error_detail`、`worker_metadata_json`。

`(job_id, attempt_number)` 唯一；attempt 不覆盖旧记录。`dead_letter` 是 job 终态，历史由 attempts/audit 保留，不另建会漂移的第二份 DLQ 权威表。

### `audit_events`

- actor：`actor_type`、`actor_id`、`actor_role`。
- action/target：`action`、`target_type`、`target_id`、`scope_type`、`scope_id`。
- binding：`policy_revision`、`subject_revision`、`content_digest`。
- diff/reason：`before_json`、`after_json`、`grant_diff_json`、`reason`。
- timing/result：`effective_at`、`expires_at`、`result`、`error_code`、`created_at`。
- correlation：`correlation_id`、`run_id`、`job_id`、`import_id`、`migration_id`。

E2 只证明表、append/query 和 runner/restore correlation；完整角色与授权字段填充属于 E3。

### `migration_maps`

- `id`、`migration_batch_id`、`source_system`、`entity_type`、`source_id`。
- `target_uuid`、`source_digest`、`status`、`error_detail`、`created_at`、`updated_at`。

`(source_system, entity_type, source_id)` 唯一；重复 dry-run 必须得到同一 target UUID 或明确 digest conflict。

### `rag_generations`

- `id`、`owner_scope`、`index_kind`、`embedding_fingerprint`、`generation`。
- `status`、`config_json`、`source_revision`、`job_id`、`error_detail`。
- `created_at`、`activated_at`、`retired_at`。

E2 只建立不含向量的 SQL 骨架；`active + staging`、Chroma collection 和切换/清理语义在 E5 实现。

### `skill_packages`

- `id`、`package_digest`、`size_bytes`、`media_type`、`raw_package`。
- `manifest_json`、`manifest_schema_version`、`created_by`、`created_at`。

`package_digest` 唯一；E2 只验证空结构/合成小包约束，真实 package 导入、Storage 对账和发布在 E6。

## Additive 与 Deferred DDL

### E2 可实施（批准后）

- 新建 canonical auth/audit/job/migration/RAG/Skill package 空结构。
- 新建 UoW/job repository 所需索引、FK 和唯一约束。
- 对新表运行空库、合成快照库、恢复库 migration/对账。
- 只在 E2 隔离库更新 Alembic head 并验证应用 startup revision gate。

### E3/E4/E5/E6 延后

- 修改现有 populated 表的主键类型、user_id 长度、FK、on-delete、nullable 或 timestamp。
- 导入 Django user/session/refresh/revocation，签发 token 或切换认证。
- 导入/改写聊天、笔记、知识、图片、模型配置、Skill 或文件/Chroma 数据。
- 激活 RAG generation、写 Chroma、删除旧 generation。
- 将 raw Skill package 从 Storage/Legacy 输入写入 SQL 并切换发布权威。

## 待确认决策

1. `CHAR(36)` UUID 与排序规则，是否采用 UUIDv7 生成但保持通用 UUID 格式。
2. `audit_events` 是否只 append，以及 payload/diff 的保留和大小上限。
3. job payload/result 的大小上限与大对象外置规则。
4. lease duration、heartbeat interval、retry backoff、max attempts、backpressure 阈值。
5. auth/RAG/Skill 空结构是否全部在一个 E2 revision，或拆为可独立审阅的多个线性 revision。
6. E2 隔离 schema 验证通过后，何时允许对后续批准环境升级 head；默认不自动推广。
