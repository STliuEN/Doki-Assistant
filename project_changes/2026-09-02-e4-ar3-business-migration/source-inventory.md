# E4 Source Inventory（正式执行中的只读记录）

## 2026-09-08 本轮执行结论（优先于下方历史记录）

- 本轮用户明确要求执行完整生命周期、Redis 故障、源停写、旧进程部署和 DSN/流量切换。已完成的是**本机单实例、loopback HTTP 的实际切换**，不是外网 DNS/LB/TLS 或多实例生产部署。
- 源库已于 `2026-09-08T00:50:34Z` 冻结并设置持久 `read_only/super_read_only`；`st@%` 已锁定/撤权。最终 21 表摘要未变，只读客户端零行 UPDATE 返回 1290。管理员仍能显式解除只读，不能宣称无法绕过。
- 三层服务实际运行于 Vite `18080`、FastAPI `18000`、retired Django `18001`。FastAPI 进程内观测确认 `doki_e4_app@%`、`doki_e4`、target UUID `0c0d3e33-a743-11f1-af41-ea47e0ceb469`；前端实际登录、cookie 刷新/注销、笔记写入和 `/jobs` 查询已穿过代理落到 target。
- 两次完整优雅 shutdown 释放 Redis pool 和 MySQL runner lock，重启重新获取锁。Redis 停止时 live/runner 为 200、ready 和依赖限流的业务请求为 503；业务/job/audit 摘要不变，恢复后无需重启应用即可写入。Redis 不可用时冷启动和 SQL runner 处理持久任务也通过。
- Django 实际进程 26 个 GET/POST 探针全部 410；ORM 写、迁移与直接 SQL 零行写入被拒绝。未启动未知旧二进制；在本机原本没有旧应用进程的前提下部署了当前 retired Django。
- 修复全生命周期暴露的 Skill registry bulk UPDATE，改为受追踪行变更并审计；补 Redis 限流 503/健康探针边界和前端 `/jobs` 代理。后端 491 测试、前端 28 测试、前端 build、Ruff、compileall 均通过。
- 最终独立恢复为 **39 表 / 2,539 行**（新增认证、审计、任务证据保留）；SHA-256 `bbcf14de7d4024aadc523d5e923fd73de917ad25c5396cf77c31b6c0d66a1b75`。原 312 业务实体、314 mappings、48 FK 复验通过；测试笔记经审计清理。
- 主证据：`artifacts/e4-full-lifecycle-cutover-20260908.json`；矩阵：`artifacts/e4-cutover-redis-20260908T024931.json`；源冻结：`artifacts/e4-source-freeze-20260908.json`；恢复：`artifacts/e4-restore-20260908T025045.json`。
- 限制：最终 FastAPI 是 `ENV=development` 的本地单实例，显式关闭 DEBUG 并启用限流；没有把本地目录冒称生产共享卷。曾设置 `SKILL_STORAGE_SHARED=true` 的早期尝试不构成共享存储验收，现运行配置为 false。Ollama 不可用降级已观察，未完成真实外部 LLM 成功/故障矩阵；E5/E6 未激活，迁移批仍为 imported，用户验收未发生。
- 安全跟进：早期诊断误输出过凭据，已轮换 target app 密码、approval、JWT signing secret 并验证旧密码失效，重建仅限 E4 target 且保留 volume/UUID；第三方 API key 仍需用户在供应商侧轮换。秘密及原始日志只存私有目录，不复制到公开证据。

日期：2026-09-02  
最近更新：2026-09-08（源已持久冻结，切流前后 21 表摘要均一致）
状态：实施中  
性质：正式执行中的只读 inventory 记录
用途：定义 E4 必须纳入的 source inventory 格式和当前本地观察；本文件不替代 source/target/restore allowlist，也不是在线资源清单。

## 2026-09-07 当前观察

- `chat_history` / `user_service` 同属 server UUID `13e60c20-6874-11f1-8e4a-bcfce7d65b5f`；21 表快照保存在私有 ACL 目录。已创建 `doki_e4_source_ro@localhost`，仅两个源 schema 的 SELECT/SHOW VIEW；最终复查 21 表行摘要未改变。
- 真实隔离目标已重建 2 个 canonical 测试用户、导入 312 条业务（含 62 条 Skill）、写入 314 mappings；48 FK 无孤儿。4 个密文配置已用工程现有 key 实际解密验证并绑定指纹版本，未复制未知密钥版本。
- 6 份 SQL 原件共 455,311 bytes 一致；10 个 Skill zip 的 semantic digest/size 验证并私有备份。另 1 个 sidecar PDF 只有 16 个 Chroma chunks，无 SQL/工程原件；已按用户明确授权记为 excluded，并写入 `migration.source_excluded` SQL 审计（correlation `e6ef6c68-c1e5-51a4-bcb5-80b372285969`）。该原件不再阻塞，未删除其它原件或历史 sidecar/chunks，见 `artifacts/e4-pdf-exclusion-20260907.json`。
- 正式 allowlist 为 `backend/ops/e4/e4_allowlist.json`；target/restore 独立 app/root 凭据，均 39 表，最新 2,407 行恢复全等；临时业务行已清理，测试 auth/job/audit 证据保留，原 312 条导入实体不变。证据：`artifacts/e4-write-authority-20260907.json`、`artifacts/e4-business-reconcile-20260907T042742.json` 和 `artifacts/e4-restore-20260907T042748.json`。
- source 仍可写，未最终停写/冻结；当前快照不自动等于切换输入。下方此前未连接/未捕获/空库内容为历史观察，不代表当前状态。

## 使用规则

正式 inventory 必须由用户批准的只读 source、dump 或脱敏离线副本生成，并保存 source locator、snapshot 时间、server/database 身份、行/文件数量、规范化 digest、访问模式和审阅人。当前执行确认已收到，但未提供这些字段的记录仍只能标为 `not-run` 或“观察结果”，不得用于导入或删除判断。

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

## 初始本地观察摘要（历史，当前执行状态见顶部）

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

## 正式 inventory 生成前的硬门槛（保留原始执行要求）

1. 用户确认 E4 计划及本次 source 范围。
2. 为 source、target、restore 分别建立 allowlist，记录 host/port/database/server UUID、容器/网络和凭证来源；拒绝默认值和隐式 `.env`。
3. 从只读 dump/bundle 生成 manifest；源快照完成后计算规范化行/文件 digest。
4. 冻结 `ShortUUID -> canonical UUID` 和公共/用户 scope 规则，再做 orphan/duplicate/conflict 报告。
5. 同时记录 batch manifest digest、逐表/逐对象 content digest 和文件/归档 digest；dry-run 与实际导入必须引用同一 snapshot manifest digest，任一层漂移都使批次失效并重新备份。

## 初始盘点阶段明确未做（历史，不代表 2026-09-07 状态）

- 未连接或读取现有业务 MySQL、Django 在线数据库、Redis 或 Chroma 服务。
- 未执行 mysqldump、业务导入、DDL、停写、写入 Chroma/MD5/文件、删除或 GC。
- 已按 Q10/Q23/Q24 固定分批、checkpoint、稳定排序和可重放记录要求；批次 gate 不增加用户确认次数。
- 未把本地观察数量当作 source/target 对账结果；正式证据需另行生成并由审阅人确认。
- v3 manifest 已纳入证据索引，但其中的计数、digest 和冲突仍只属于 `observed-only`；正式 source snapshot 必须由批准的 dump/bundle、server identity 和权限证明重新生成。
