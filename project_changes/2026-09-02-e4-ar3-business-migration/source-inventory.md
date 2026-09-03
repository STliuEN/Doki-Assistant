# E4 Source Inventory（准备版）

日期：2026-09-02  
最近更新：2026-09-03（暂停后恢复准备）  
状态：实施中  
性质：只读准备  
用途：定义 E4 必须纳入的 source inventory 格式和当前本地观察；本文件不替代 source/target/restore allowlist，也不是在线资源清单。

## 使用规则

正式 inventory 必须由用户批准的只读 dump 或脱敏离线副本生成，并保存 source locator、snapshot 时间、server/database 身份、行/文件数量、规范化 digest、访问模式和审阅人。当前执行确认已收到，但未提供这些字段的记录仍只能标为 `not-run` 或“观察结果”，不得用于导入或删除判断。

禁止从 `.env`、默认端口或正在运行的服务推断目标。E4 target、restore、网络、凭证和迁移开关必须另建 allowlist，不能复用 E1/E2/E3 资源。

## Inventory 记录格式

| 字段 | 要求 |
|---|---|
| `inventory_id` | `E4-SRC-<NN>`，同一快照重跑保持稳定 |
| `source_system` / `entity_type` | 例如 `django/user`、`fastapi/chat_message`、`filesystem/md5`、`chroma/embedding` |
| `source_locator` | 脱敏路径或 dump/bundle ID；不得写入 secret、完整 token 或未脱敏 PII |
| `snapshot_ref` / `captured_at` | 只读快照 manifest 和 UTC 时间 |
| `identity_key` | 原系统主键/用户标识及其规范化规则 |
| `row_or_file_count` | 原始计数；空值不得默认为零 |
| `batch_manifest_digest` | 本次 source snapshot/bundle manifest 的 SHA-256；与逐对象 digest 分开记录 |
| `content_digest` | 规范化行/文件内容 SHA-256；说明排序、字段和时区规则；不得代替 batch manifest digest |
| `target_entity` / `target_uuid` | 目标表/映射候选；dry-run 前不得填入事实 UUID |
| `status` / `disposition` | 正式迁移处置使用 `pending`、`mapped`、`conflict`、`orphan`、`excluded`；准备阶段可暂记 `observed-only` 或 `not-run`，但必须附原因、限制和审阅记录，且不得解释为迁移完成 |

## Source 范围与当前观察

| ID | Source / 范围 | 访问模式 | 当前只读观察 | 正式纳入条件 | 当前状态 |
|---|---|---|---|---|---|
| `E4-SRC-01` | E3 canonical MySQL：`users`、`auth_sessions`、`migration_maps`、`audit_events` | 仅批准 snapshot/dump；不连接在线库 | E3 关闭记录显示 2 个测试用户已完成 E3 mapping；旧业务对象未随 E3 导入 | E4 独立 dump、server UUID、revision 和 manifest | pending |
| `E4-SRC-02` | Django `user_service` 及相关迁移表 | 只读 dump/脱敏副本 | `User` 模型为 ShortUUID 主键；文件 app 当前没有业务字段模型 | 用户批准的 dump；邮箱/电话/hash/时间规范化规则已审阅 | pending |
| `E4-SRC-03` | FastAPI 业务 SQL：`chat_sessions`、`chat_messages`、`notes`、`memory_items`、`note_templates`、`knowledge_source_documents`、`user_model_configs`、`user_embedding_configs` | 仅目标/源 snapshot；不运行在线 inventory | 当前模型存在旧 ID 宽度、整数 message ID、无 canonical user FK 等差异 | 目标表/源表身份、行数、digest、约束和 orphan 报告 | pending |
| `E4-SRC-04` | 聊天/笔记关联写路径和 API/SSE/polling | 静态代码审阅；后续隔离 smoke | 多个 service 直接 `commit()`；派生 Chroma/记忆副作用在 SQL commit 外执行 | 写入口矩阵、correlation ID 和 after-commit job 证据 | observed-only |
| `E4-SRC-05` | `backend/data/chromadb/chroma.sqlite3` 及 collection metadata | 本地文件只读；不写、不重建、不删除 | 4 collections：`rag_collection` 16 embeddings、`rag_e5efbb90a85fadbf` 65、`notes_e5efbb90a85fadbf` 7、`notes_collection` 0；其中 65/7 条 metadata 的 `user_id` 为旧 ShortUUID `j6BVY9AHmHPQEbwoZabRMq`，与 collection 名称后缀 `e5efbb90a85fadbf` 不一致；RAG metadata 还包含本机临时绝对路径，需脱敏 | 文件 digest、collection/generation 解释、用户映射、临时路径脱敏和 SQL source 对账；不一致在解决前标记 `scope_conflict` | observed-only |
| `E4-SRC-06` | `backend/data/md5_hex_store/user_md5/*/md5_hex_store.txt` | 本地文件只读；不追加/清理 | 观察到 1 个用户目录、7 条 JSON 记录、7 个 MD5；用户目录使用旧 ShortUUID（永久记录须脱敏） | 每条记录与 knowledge source、文件内容和 user mapping 对账 | observed-only |
| `E4-SRC-07` | `backend/data/extracted_images/` | 本地目录只读；不删除 | 当前统计为 0 个文件；空目录不等于没有历史图片或没有待导入引用 | 目录 manifest、孤儿引用扫描、媒体快照 | observed-only |
| `E4-SRC-08` | `backend/data/skill_packages/objects/` | 本地对象只读；不 GC/覆盖 | 观察到 10 个对象，总大小约 5,627 bytes；SQL package/legacy identity 尚未对账 | object key/digest、manifest、owner、版本和 SQL 关联 | observed-only |
| `E4-SRC-09` | Django `MEDIA_ROOT`、上传目录及旧文件路径 | 只读目录快照 | 当前仓库未证明完整 MEDIA_ROOT；不能把空/不存在路径记为零数据 | 明确根路径、权限、快照和文件 digest | not-run |
| `E4-SRC-10` | Redis keys/pending/cache | 禁止连接；只允许批准的隔离 fixture | 本准备阶段未读取 Redis；Redis 不得作为业务事实或迁移输入唯一来源 | 若需要只读观察，先单独审批、allowlist 和脱敏导出 | not-run |
| `E4-SRC-11` | 旧 Chroma generation/备份目录 | 只读 manifest；不直接作为业务恢复源 | E1 历史证据存在旧 generation，但 E4 不把其向量当作原文权威 | 仅用于派生对照，最终从 SQL 原文重建；`excluded` 仅表示排除业务权威，不表示删除或清理 | excluded |
| `E4-SRC-12` | `backend/data/reranker_config.json` | 本地文件只读；不自动加载或修改 | 可见为本地 reranker 配置候选；尚无 SQL owner、revision、digest 或环境归属证明 | 明确配置是业务事实还是开发调参；若属业务配置，迁入有版本/审计的 SQL；否则标记 debug-only 并排除迁移 | observed-only |
| `E4-SRC-13` | `backend/data/routing_calibration/` | 本地文件只读；不自动加载或删除 | 存在本地 routing calibration 派生文件；当前没有 source snapshot、owner 或发布 revision | 明确是否为可重建 debug 产物；不得被请求路径或迁移器当作权威 | observed-only |
| `E4-SRC-14` | FastAPI SQL Skill 元数据候选：`skills`、`skill_aliases`、`skill_versions`、`skill_installations`、`skill_capability_grants`、`skill_imports`、`skill_run_bindings` | 仅批准 snapshot/dump；不执行在线 import/publish | 代码中同时存在目标模型骨架与可能的旧业务行；模型定义本身不是 source 数据。E4 只需迁移已确认的 owner/run/审计关联；规范化发布仍属 E6 | 逐表确认 source/target 身份、owner/scope、legacy map、package/storage digest 和 E6 边界；不得把 Storage 对象或空 schema 计作 SQL 行 | pending |

## 当前本地观察摘要

- Chroma 文件中可见的用户 metadata 使用旧 ShortUUID；同一旧用户出现在 RAG 和 notes collection。该标识只能进入 `migration_maps` dry-run，不能直接写入 canonical FK。
- Chroma collection 名称后缀 `e5efbb90a85fadbf` 与 metadata/MD5 sidecar 中的旧用户 ID `j6BVY9AHmHPQEbwoZabRMq` 不一致；在 SQL 源行或经批准的 manifest 证明前，按 `scope_conflict` 处理，不得猜测二者等价。metadata 中的临时绝对路径也不得进入长期证据。
- MD5 sidecar 保存 `md5`、文件名和上传时间，但不保存可证明的 SQL 主键/内容快照；sidecar 只能作为候选输入，必须与原始文件或 SQL BLOB 对账。
- Legacy 32 位 `md5` 不能代替 `migration_maps.source_digest` 要求的 64 位小写 SHA-256；正式 inventory 必须同时保留历史 MD5 和独立规范化 SHA-256。
- `extracted_images` 当前无文件，不能据此声明图片迁移完成或历史图片不存在。
- Skill Storage 对象是 content-addressed 文件，不等于 `skill_packages` SQL 行；需要 digest、manifest、owner 和版本关联后才可纳入迁移。
- `reranker_config.json` 与 `routing_calibration/` 是本地配置/派生候选，尚未证明为业务事实；必须先确定 SQL 权威、revision、owner 和审计归属，不能由迁移器隐式读取。
- 现有 E3 `migration_maps` 只接受 `mapped/conflict/error`；E4 的候选、孤儿和对账状态需留在 inventory 或通过单独的受控 schema 表达，不能直接写入未定义状态。
- Redis、在线 MySQL、Django 在线服务和未明确的 MEDIA_ROOT 均未被本阶段读取。
- 本机只读进程观察到两个 `mysqld.exe`，其命令行/拓扑身份无法确认；按未知现有资源保护，未探测端口、未连接、未复用，不能将其视为 E4 target/restore。

## 2026-09-03 本地 manifest 追加记录

已在不读取 `.env`、不创建 Chroma client、不开网络/数据库连接的条件下，生成脱敏离线 manifest：[local-inventory-v3.json](artifacts/local-inventory-v3.json)。采集时间为 `2026-09-03T01:07:41.099399+00:00`；计数为 4 collections、88 embeddings、MD5 7 records/7 values、图片 0 files、Skill Storage 10 objects；发现 2 个脱敏 `scope_conflict`。

- 工具 canonical manifest digest：`7566814bfc0e4a16a9c61988d41074e2c486982840563853ded176f3e8ddb0ac`。
- JSON 封装文件 SHA-256：`8c018624c28192a7e84000ca6b1f455d08ee57d172a6c81792d9cf7058bf7faf`。
- canonical digest 按 `e4_inventory` 定义排除 `captured_at` 和自身摘要字段；文件 SHA-256 包含完整 JSON 封装，因此两者不可互换。
- 该 manifest 是本地非业务资源的只读证据，不是用户批准的正式业务 source inventory；不改变 `E4-01` 在线/正式业务部分的 `not-run` 状态，也不授权映射、导入、停写、切换或清理。

## 正式 inventory 生成前的硬门槛

1. 用户确认 E4 计划及本次 source 范围。
2. 为 source、target、restore 分别建立 allowlist，记录 host/port/database/server UUID、容器/网络和凭证来源；拒绝默认值和隐式 `.env`。
3. 从只读 dump/bundle 生成 manifest；源快照完成后计算规范化行/文件 digest。
4. 冻结 `ShortUUID -> canonical UUID` 和公共/用户 scope 规则，再做 orphan/duplicate/conflict 报告。
5. 同时记录 batch manifest digest、逐表/逐对象 content digest 和文件/归档 digest；dry-run 与实际导入必须引用同一 snapshot manifest digest，任一层漂移都使批次失效并重新备份。

## 明确未做

- 未连接或读取现有业务 MySQL、Django 在线数据库、Redis 或 Chroma 服务。
- 未执行 mysqldump、业务导入、DDL、停写、写入 Chroma/MD5/文件、删除或 GC。
- 已按 Q10/Q23/Q24 固定分批、checkpoint、稳定排序和可重放记录要求；批次 gate 不增加用户确认次数。
- 未把本地观察数量当作 source/target 对账结果；正式证据需另行生成并由审阅人确认。
- v3 manifest 已纳入证据索引，但其中的计数、digest 和冲突仍只属于 `observed-only`；正式 source snapshot 必须由批准的 dump/bundle、server identity 和权限证明重新生成。
