# E2 当前 SQL 与运行时盘点

日期：2026-08-28  
性质：只读准备证据；不代表 E2 已实施

## 当前结构

| 范围 | 当前事实 | E2 处理 |
|---|---|---|
| Alembic | `20260817_0001_baseline` -> `20260824_0002_skill_domain`；启动要求精确 head，不自动 DDL | 保留 fail-closed revision gate；增加加法式 E2 revision 和 head/model parity |
| FastAPI schema | 18 张表：8 张聊天/知识/笔记/记忆/模型配置表，10 张 Skill/Registry 表 | 形成唯一 schema map；不在 E2 改写 populated legacy rows |
| Django identity | `user_service` 独立数据库/ORM，22 字符 ShortUUID，含 username/email/telephone/password/status/token_version 等 | E2 设计目标 auth 表；真实用户迁移和认证切换归 E3 |
| ID/FK | `String(36)`、`String(64)`、整数消息 ID 混用；跨服务 user_id 无物理 FK | 冻结目标 UUID/FK；旧 ID 通过后续 legacy map 对账 |
| transaction | `get_db()` 自动 commit/rollback，但大量 service/tool 直接创建 session 或内部 commit | E2 提供 UoW 和迁移清单；先覆盖新 job 路径，业务回接归 E3/E4 |
| outbox | `skill_registry_events` 有 revision/processed_at 和轮询 reconciler | 仅作局部 characterization；没有 claim/lease/heartbeat/fencing/retry/cancel/DLQ |
| durable job | 无通用 jobs/job_attempts、repository、state machine 或 runner | E2 新增 SQL-only 实现，并发固定为 1 |
| backup | `backup_restore.py` 能封装/校验 offline mysql dump、Storage tree、Chroma projection | 复用 manifest/tamper 基础；补 mysqldump/import、DB 语义对账和 restore-forward |
| readiness | FastAPI lifespan 校验 schema 后初始化 Skill、Redis、模型/Chroma；没有 runner 生命周期 | E2 接入 runner 但分离 runner liveness 与 API readiness |

## 现有 FastAPI 表

`20260817_0001`：

- `chat_sessions`、`chat_messages`
- `knowledge_source_documents`
- `memory_items`
- `notes`、`note_templates`
- `user_embedding_configs`、`user_model_configs`

`20260824_0002`：

- `skills`、`skill_aliases`、`skill_versions`
- `skill_installations`、`skill_capability_grants`、`skill_imports`
- `skill_audit_events`
- `skill_registry_state`、`skill_registry_events`
- `skill_run_bindings`

## 可复用切片

- Alembic 环境和 exact-revision startup check 已存在。
- SQLAlchemy async engine/sessionmaker 和 dependency 已存在。
- Skill transaction tests、idempotency key、revision/outbox 可作为语义参考。
- offline backup bundle 已有 SHA-256 manifest、路径穿越/符号链接/篡改拒绝和原子恢复。
- E1 已证明隔离 MySQL 8.4 dump/restore/restore-forward 的操作可行，但 E2 必须生成自己的 schema/runner 证据。

## 不能直接复用为完成证据

- `skill_registry_events.processed_at` 不是通用 job claim，也没有 lease、heartbeat、fencing、retry、cancel、DLQ 或 backpressure。
- `get_db()` 加 service 内部 `commit()` 不是可组合 UoW；外层无法保证 domain write 与 enqueue 原子。
- `backup_restore.py` 不运行 mysqldump/import，也不核对数据库表、行、约束或 canonical row digest。
- SQLite 单测无法证明 MySQL `FOR UPDATE SKIP LOCKED`、数据库时钟租约和 crash recovery。
- Django migration 与 FastAPI Alembic 属于两个数据库历史，不能直接 stamp 为统一 schema。

## E2 后续阶段归属

| 内容 | 阶段 |
|---|---|
| 目标 auth/domain/job/rag/skill 表结构和加法式空库 schema | E2 |
| UoW、SQL durable job、单并发 runner、备份恢复 | E2 |
| 用户/session/refresh/revocation 数据导入及认证切换 | E3 |
| 聊天/笔记/知识/图片/Skill 等真实业务数据迁移和唯一写入口 | E4 |
| RAG port、Chroma generation/rebuild 和真实 RAG E2E | E5 |
| Skill 发布授权闭环和核心业务回接 | E6/E7 |

## 需要在 E2-01 冻结的决策

1. UUID 数据库表示、legacy ID 映射格式和 physical FK 激活阶段。
2. UTC 时间精度、数据库时钟表达式、revision/fencing/digest 类型。
3. jobs/job_attempts/audit_events 的逐列 schema、索引和保留策略。
4. claim 查询、lease/heartbeat 时长、backoff、最大 attempts、cancel checkpoint 和 backpressure 阈值。
5. additive migration 与 E3/E4 deferred DDL 的分界。
6. UoW repository API、事务所有权和现有内部 commit 的迁移顺序。
7. runner readiness/liveness、shutdown deadline 和 crash fault points。
8. dump 一致性参数、canonical row digest 算法、restore-forward 与 evidence retention。
