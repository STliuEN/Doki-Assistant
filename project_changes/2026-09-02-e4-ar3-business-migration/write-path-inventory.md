# E4 业务写入口盘点（准备版）

日期：2026-09-02  
状态：实施中  
性质：静态审阅  
目的：识别所有可能改变业务事实或派生状态的入口，供唯一写权威切换设计使用。

## 判定规则

- **业务事实**：用户、会话、消息、笔记、记忆、知识源、原始文档/图片、模型配置、Skill 元数据、job、审计和迁移映射。最终只能由 FastAPI -> MySQL 写入。
- **派生投影**：Chroma chunks/metadata/vectors、索引、缓存和临时解析结果。只能由 SQL 事务提交后的 durable job 产生，失败不反写业务成功。
- **显式运维输入/输出**：只读 dump、导入/导出文件、restore bundle、debug 文件；必须显式调用、受开关和审计保护，不能自动 fallback。
- `Redis pending`、内存队列和 SSE 事件只作唤醒/展示提示，不可作为业务正确性、确认或 job 完成依据。

## 当前写入口

| ID | 入口/文件 | 当前写入 | 类别 | E4 风险 | 目标处置 |
|---|---|---|---|---|---|
| `E4-WR-01` | `DjangoUserService/apps/user/views.py`、serializers | Django `user_service` 用户资料/密码/状态，缓存清理 | 业务事实 + 旧缓存 | 旧认证/资料接口仍可写，形成双权威 | E3 已将认证入口切换；E4 期间只读/shadow，最终移除运行写路径 |
| `E4-WR-02` | `DjangoUserService/apps/file/views.py` | 上传文件、用户 avatar 字段、文件目录 | 业务事实 + 文件 | 文件和 SQL 不原子；旧服务可继续写 | 迁移前只读；最终上传先写 MySQL 原文/图片元数据，再由 job 产生派生文件/索引 |
| `E4-WR-03` | `backend/app/services/database_session_manager.py` | `chat_sessions`、`chat_messages`，多处直接 `commit()` | 业务事实 | 旧 `String(64)` owner、整数 message ID、无统一 audit/job 边界 | 迁移到 canonical UUID/FK；所有 create/append/update/delete 经 FastAPI UoW + audit |
| `E4-WR-04` | `backend/app/services/note_service.py` | `notes` 写入/删除/批量操作，直接 `commit()` | 业务事实 | commit 后 `asyncio.create_task` 自动标签/记忆；Chroma 删除/写入分离 | SQL 事务提交 + durable job；外部投影失败不改变 SQL 结果 |
| `E4-WR-05` | `backend/app/services/memory_service.py` | `memory_items` create/update/delete/review，直接 `commit()` | 业务事实 | 用户 ID 无物理 FK；笔记删除与 memory 清理边界不一致 | 统一 owner UUID/FK 和事务；关联删除策略先审阅再 DDL |
| `E4-WR-06` | `backend/app/services/knowledge_document_service.py` | `knowledge_source_documents` upsert/status/delete，直接 `commit()` | 业务事实 | 保存 `content_blob`，与 MD5/文件/Chroma 可能分裂 | 将原文、digest、图片元数据纳入 SQL；解析/embedding 只由 after-commit job |
| `E4-WR-07` | `backend/app/router/knowledge_service.py`、`backend/app/rag/document_handler/processor.py` | 上传切片、临时文件、MD5 sidecar、SSE 队列、Chroma 写入 | 业务事实 + 派生 + 临时 | SSE/线程队列可能先于 SQL 事实；失败/取消难以对账 | API 只提交 SQL/job；SSE 从 SQL/job 读取；临时文件显式清理并留 audit |
| `E4-WR-08` | `backend/app/rag/md5_manager/md5_store.py`、`backend/app/rag/vector_store.py` | `md5_hex_store.txt` 追加/删除 | 派生/遗留输入 | sidecar 可与 SQL 行不一致，删除有破坏性 | 迁移期只读 inventory；SQL digest 成为权威，sidecar 仅保留审计/导出直到批准删除 |
| `E4-WR-09` | `backend/app/utils/image_extractor.py`、`knowledge_image_paths.py` | `extracted_images/<user>/<md5>/` 写入/递归删除 | 派生/文件 | 路径按旧 user/md5；递归删除可能越过恢复边界 | 先生成文件 manifest/孤儿报告；图片元数据/内容进入 SQL 后再由明确运维动作处置 |
| `E4-WR-10` | `backend/app/rag/vector_store.py`、`backend/app/core/background_init.py` | Chroma collection add/delete/rebuild | 派生投影 | Chroma 被误当业务事实或同步重建；旧 generation 删除风险 | E4 只盘点和关联；E5 负责 SQL->Chroma job、generation 与 degraded/503 |
| `E4-WR-11` | `backend/app/skills/storage.py` | Skill Storage staging/object/quarantine 文件写入、替换、清理 | 显式输入 + 派生归档 | 文件对象与 SQL `skill_packages` 可能无 owner/version 对账 | E4 只做 inventory/map；E6 规范化导入与发布前不得 GC/覆盖 |
| `E4-WR-12` | `backend/app/skills/service.py`、`backend/app/skills/seed.py` | Skill SQL 版本、安装、grant、import、registry 事件 | 业务事实 | 多处直接 `commit()`；RunBinding user/session 仍旧 ID 宽度 | owner/run/audit 先映射；E6 统一 package 写入和授权事务 |
| `E4-WR-13` | `backend/app/services/pending_action_store.py`、`backend/app/agent/tool_guard.py` | Redis pending action set/take/delete | 临时状态 | Redis 丢失、TTL 或 take 结果不能证明业务动作完成 | 仅作为唤醒/确认提示；最终 action/job/审计事实写 MySQL，Redis 失效 fail-closed |
| `E4-WR-14` | `backend/app/services/reranker_config_service.py`、`backend/app/agent/routing_calibration.py` | 本地 JSON/calibration 文件写入/删除 | 运维/配置 | 文件可漂移、无 SQL revision/audit | 明确归属：业务配置进 SQL；纯开发 calibration 标记 debug，不得被请求自动当权威 |
| `E4-WR-15` | `backend/app/jobs/repository.py`、`backend/app/jobs/runner.py` | SQL jobs/attempts/audit、lease/fencing/result | 业务事实 | 需确保业务 commit 与 job enqueue 同事务 | 复用 E2 UoW；旧 runner/内存队列不得单独提交结果 |
| `E4-WR-16` | `backend/app/db/db_config.py:get_db`、各 router/service | 请求结束自动 `session.commit()` 或 service 内显式 commit | 事务边界 | 同一请求多次 commit 导致外部副作用不可回滚 | 逐模块改为单一 UoW；提交后只 enqueue durable job；禁止隐式跨资源提交 |
| `E4-WR-17` | `backend/scripts/rotate_model_config_keys.py` | 批量读取并重写 `api_key_encrypted`，按 key 环境变量决定是否 commit | 显式运维写入 | key 版本/来源和审计未绑定迁移批次；误用旧/新 key 会产生不可解密配置 | 迁移前只允许隔离 fixture dry-run；实施时记录 key version、配置 digest、审计和 restore 点，禁止输出明文 |

## 读入口与事实展示

| 入口 | 当前行为 | E4 要求 |
|---|---|---|
| API 查询 | 多数直接读业务表，部分读取 Chroma/Redis | 业务状态、job 状态和审计以 SQL 为准；Chroma 只返回 projection generation/status；Redis 缺失不改变正确性 |
| SSE/polling | 知识切片和 agent 运行使用内存队列/事件 | 事件必须带 job/correlation ID；断线重连从 SQL 事实重放，不能把队列丢失当成功 |
| runner | E2 durable runner 已有 lease/fencing/retry | E4 业务 handler 必须在同一 SQL UoW 记录结果；旧 token/过期 lease 拒绝提交 |
| debug/import/export | 文件和脚本可直接处理内容 | 显式命令、allowlist、snapshot digest、审计和 dry-run；业务请求不可自动调用 |

## 已发现并处置的阻塞缺陷

- `backend/app/router/note_template_router.py` 曾先注册通用 `PUT /note-template/{template_id}`，导致 `reorder` 被当作 `template_id`；已将具体路由前移，并以 `backend/tests/test_note_template_route_matching.py` 回归验证。该修复只证明路由匹配，不证明业务写权威切换。

## 唯一写权威切换顺序（已授权，按 gate 执行）

1. 记录现有写入口、进程、端口、依赖和 active schema revision；建立 E4 source/target/restore allowlist。
2. 对每个入口增加只读/shadow 观测和 correlation ID，确认 SQL 事实与外部投影差异；不同时开启长期双写。
3. 完成 source snapshot、identity map、目标 additive/shadow 列和回填 dry-run；发现 mismatch 即停止。
4. 在批准停写窗口内关闭 Django/旧脚本/文件业务写入，保留显式导入/导出命令；FastAPI 统一经 UoW 写 SQL。
5. 事务提交后 enqueue 解析/索引/通知 job；SSE/polling 从 SQL job 状态读取，Redis 仅作唤醒。
6. 抽样验证重复、乱序、租约过期、kill/restart、超时、取消、异常和孤儿 job；通过后才进入 E5/E6。

## 必须阻断的情形

- 仍有未登记的 Django、脚本、文件或 service 直接写业务事实。
- SQL commit 成功后 API 依赖 Chroma/Redis/文件成功才能返回业务成功。
- SSE/Redis pending 被当作确认、job 完成或正确性来源。
- 外部副作用没有 correlation/job/audit，无法按 source/target digest 对账。
- 旧 fencing token、过期 lease 或重复请求能提交结果。
- 切换前没有可验证快照，或 restore-forward 只能覆盖原库/删除旧输入。

## 明确未做

- 未禁用、修改或删除任何当前写入口。
- 未执行停写、数据库/文件/Chroma/Redis 写入、迁移或回滚。
- 按 Q35 不增加针对 3306 的特殊保护；仍执行通用资源身份、server UUID、数据库和 allowlist 核验，未知监听不得视为目标。
- 按 Q41 当前执行者接手；按 Q42/Q43 复用 E0-E3 的记录、恢复和最终统一清理规则。
- 本盘点基于静态代码和本地目录观察；不证明在线流量、进程或外部资源没有其他写入。
