# E4 业务写入口盘点（实施中）

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

### 本轮补充写入口

- `SkillService.consume_registry_events` 不再 bulk UPDATE：使用 `mutate_rows` 行锁读取、ORM 变更、事务提交；新增 E4 BusinessSession 回归证明一次审计和重复消费无新审计。
- Redis 限流异常不会进入业务路由：中间件/依赖分别返回 503；live/ready/runner 不被全局限流挡住，ready 自身在 Redis 不可用时仍返回 503。
- `/jobs` 已纳入 Vite proxy。前端实际 owner polling 与跨用户 404 已验证，不能把先前 SPA fallback 的 HTTP 200 当作任务 API。
- 当前进程写权威和本地持久配置已切 E4；这不封禁有管理员权限的人工 SQL 客户端，也不等于 E5/E6 写路径验收。

日期：2026-09-02  
状态：实施中  
性质：静态审阅与局部 live 验证
目的：识别所有可能改变业务事实或派生状态的入口，供唯一写权威切换设计使用。

## 2026-09-07 执行差异

- 证据：`artifacts/e4-write-authority-20260907.json`。已导入 312 条业务、314 mappings，幂等重放无新增；日常写入另以真实 MySQL API 和 runner 验证，不拿迁移事务代替业务验证。
- E4 `BusinessSession` 为新业务设置 canonical owner/entity/parent、digest 和加密 key version，验证用户/父级归属及身份不可变；业务、audit、durable job 同事务提交或回滚。ORM bulk DML/未追踪 SQL 写入被拒绝，service 批量操作改为受追踪行变更。
- 笔记自动/手动 enrich 改为 SQL job；handler 校验 lease/fencing，笔记/记忆变更和 job 成功同事务。实际自动/手动两次 enrich 仅生成一条复习记忆，tagger 为确定性 fixture，不是外部 LLM 测试。
- 知识原件/配置先写 SQL 和 job，不同步依赖 Chroma；流式上传在 SQL commit 后才发 accepted。`GET /jobs`、`GET /jobs/{job_id}` 按 owner 读取真实 SQL 状态，跨用户不可见。
- 默认 E4 runner 仅领取已注册的 enrich 任务；`e4.note.project`、`e4.knowledge.project`、`e4.embedding.rebuild` 等 E5 投影未注册，保持 queued，不耗尽重试或伪造成功。此次 smoke 的临时实体清理后，9 个新任务中 2 个 succeeded、其余 7 个显式 cancelled，证据保留。
- E4 HTTP 旧 tools/MCP、MD5/reranker 变更入口返回 410；Django 旧 user/file/admin 路由和普通 ORM 写入在代码层封闭，旧密钥轮换 apply 拒绝。Django 自身 venv 的 14 次路由请求全部拒绝且未调用 view；未重启旧在线进程或统一撤销其数据库写权限。
- 全量 488 项测试通过；真实 runner kill/restart、lease 回收、进程锁排他和旧 fencing 拒绝已有证据。完整 main 生命周期、Redis 故障及全部业务故障矩阵仍未验证。
- 缺失测试 PDF 已明确授权 excluded 并写 SQL 审计，不再阻塞。永久 DSN/流量未切换，源未停写，Chroma generation 未激活，E4 尚未关闭。

## 判定规则

- **业务事实**：用户、会话、消息、笔记、记忆、知识源、原始文档/图片、模型配置、Skill 元数据、job、审计和迁移映射。最终只能由 FastAPI -> MySQL 写入。
- **派生投影**：Chroma chunks/metadata/vectors、索引、缓存和临时解析结果。只能由 SQL 事务提交后的 durable job 产生，失败不反写业务成功。
- **显式运维输入/输出**：只读 dump、导入/导出文件、restore bundle、debug 文件；必须显式调用、受开关和审计保护，不能自动 fallback。
- `Redis pending`、内存队列和 SSE 事件只作唤醒/展示提示，不可作为业务正确性、确认或 job 完成依据。

## 当前写入口

| ID | 入口/文件 | 当前写入 | 类别 | E4 风险 | 目标处置 |
|---|---|---|---|---|---|
| `E4-WR-01` | `DjangoUserService/apps/user/views.py`、`legacy_boundary.py` | 旧用户/管理路由由首个 middleware 返回 410；ORM write router 拒绝 | 旧业务事实 | 代码防护不影响未重启旧进程或直接 SQL 客户端 | 部署重启并验证旧进程停写；最终撤销旧写凭据 |
| `E4-WR-02` | `DjangoUserService/apps/file/views.py`、`legacy_boundary.py` | 旧文件路由在 view 前返回 410，不触发上传/头像改写 | 旧业务事实 + 文件 | 旧运行进程仍须停写验证 | 保留历史源，不再通过旧 HTTP 上传；新文件业务需受审计 SQL/job 路径 |
| `E4-WR-03` | `backend/app/services/database_session_manager.py` | 会话及成对消息共用 `SqlUnitOfWork`，经受追踪写入设置 canonical owner/parent/digest/audit | 业务事实 | legacy ID 列仍作为迁移兼容字段保留 | 已验证消息失败不会单独提交空父会话；最终切流 gate 尚未执行 |
| `E4-WR-04` | `backend/app/services/note_service.py` | 笔记行、audit、enrich/project jobs 同事务；E4 抑制旧外部回调 | 业务事实 | E5 投影尚未提供，不等于向量已更新 | SQL 成功与投影状态分离；enrich 有 fencing，project 保持 queued |
| `E4-WR-05` | `backend/app/services/memory_service.py` | create/update/delete/review 经请求或 UoW 受追踪写入，设置 canonical owner/audit | 业务事实 | 来源笔记归属/清理必须原子一致 | 已校验 source note 归属并追踪批量行变更；SQL 外键与事务验证通过 |
| `E4-WR-06` | `backend/app/services/knowledge_document_service.py` | 原文 BLOB、digest、owner/audit/project job 同事务 | 业务事实 | 接收原文不等于解析或索引已完成 | SQL 为原件权威；异步解析/embedding 属 E5 worker |
| `E4-WR-07` | `backend/app/router/knowledge_service.py`、`knowledge_router.py` | E4 有界读取上传内容，SQL/job 接收；accepted SSE 在 commit 后发送 | 业务事实 + 任务展示 | 旧非 E4 上传仍有文件/内存队列路径 | E4 不调用旧同步 Chroma 管线；SQL polling 可查，完整断线重连矩阵待验证 |
| `E4-WR-08` | `backend/app/rag/md5_manager/md5_store.py`、`backend/app/rag/vector_store.py` | 遗留 sidecar 仍保留；E4 HTTP MD5 写入口 410 | 派生/遗留输入 | 直接脚本或旧进程仍可能绕过 HTTP | SQL digest 为权威；历史 sidecar 留待 E5/E7，当前不删除 |
| `E4-WR-09` | `backend/app/utils/image_extractor.py`、`knowledge_image_paths.py` | `extracted_images/<user>/<md5>/` 写入/递归删除 | 派生/文件 | 路径按旧 user/md5；递归删除可能越过恢复边界 | 先生成文件 manifest/孤儿报告；图片元数据/内容进入 SQL 后再由明确运维动作处置 |
| `E4-WR-10` | `backend/app/rag/vector_store.py`、`backend/app/core/background_init.py` | Chroma collection add/delete/rebuild | 派生投影 | Chroma 被误当业务事实或同步重建；旧 generation 删除风险 | E4 只盘点和关联；E5 负责 SQL->Chroma job、generation 与 degraded/503 |
| `E4-WR-11` | `backend/app/skills/storage.py` | Skill Storage staging/object/quarantine 文件写入、替换、清理 | 显式输入 + 派生归档 | 文件对象与 SQL `skill_packages` 可能无 owner/version 对账 | E4 只做 inventory/map；E6 规范化导入与发布前不得 GC/覆盖 |
| `E4-WR-12` | `backend/app/skills/service.py`、`backend/app/skills/seed.py` | 受管理事务 flush；E4 Skill SQL 变更有 audit，RunBinding canonical owner/session 校验；启动 seed 跳过 | 业务事实 | package/storage 生命周期及 registry 发布不是 E4 已解决事项 | E4 只完成必要 identity/audit；E6 统一规范化 package 和发布 |
| `E4-WR-13` | `backend/app/services/pending_action_store.py`、`backend/app/agent/tool_guard.py` | Redis pending action set/take/delete | 临时状态 | Redis 丢失、TTL 或 take 结果不能证明业务动作完成 | 仅作为唤醒/确认提示；最终 action/job/审计事实写 MySQL，Redis 失效 fail-closed |
| `E4-WR-14` | `backend/app/services/reranker_config_service.py`、`backend/app/agent/routing_calibration.py` | E4 reranker switch/旧 tools/MCP 维护变更 HTTP 410；开发 calibration 仍保留 | 运维/配置 | 文件与独立脚本不由 HTTP middleware 全局隔离 | 不将文件当新 SQL 业务权威；最终停写另查直接客户端 |
| `E4-WR-15` | `backend/app/jobs/repository.py`、`backend/app/jobs/runner.py`、`business_handlers.py` | SQL jobs/attempts/audit、lease/fencing；enrich 业务结果与 job 完成同 UoW | 业务事实 | 不得领取未实现的投影 job 或用过期 lease 写业务 | 已按注册类型 claim/recover 并验证 fenced 结果；E5 handler 保持未注册 |
| `E4-WR-16` | `backend/app/db/db_config.py:get_db`、`business_authority.py`、各 router/service | E4 BusinessSession 在响应前 owning commit；service flush；business/audit/job 原子写入 | 事务边界 | 返回成功不可先于 commit，后台调用需独立受管理事务 | 已测试 commit 失败不返回成功、raw/bulk 绕过拒绝；E4 抑制 legacy after-commit 回调 |
| `E4-WR-17` | `backend/scripts/rotate_model_config_keys.py` | E4 模式直接拒绝旧 `--apply`，不允许绕过 key version/digest/audit | 显式运维写入 | 非 E4 模式/直接数据库客户端仍需最终停写治理 | 新轮换须走显式受保护且有备份/审计的迁移，不输出明文 |

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
5. 在业务事务内 enqueue 解析/索引/通知 job 并写 audit，和业务行一起 commit；只有提交后 runner 才可领取执行，Redis 仅作唤醒。SSE/polling 从 SQL job 状态读取，不以事件证明完成。
6. 抽样验证重复、乱序、租约过期、kill/restart、超时、取消、异常和孤儿 job；通过后才进入 E5/E6。

## 必须阻断的情形

- 仍有未登记的 Django、脚本、文件或 service 直接写业务事实。
- SQL commit 成功后 API 依赖 Chroma/Redis/文件成功才能返回业务成功。
- SSE/Redis pending 被当作确认、job 完成或正确性来源。
- 外部副作用没有 correlation/job/audit，无法按 source/target digest 对账。
- 旧 fencing token、过期 lease 或重复请求能提交结果。
- 切换前没有可验证快照，或 restore-forward 只能覆盖原库/删除旧输入。

## 当前边界与明确未做

- 已实现隔离 E4 日常业务 SQL 写权威及旧入口代码防护，已实际写入、回滚、执行 enrich、审计、清理临时业务实体并备份恢复；不是仅静态盘点。
- 未停止源写入、未重启旧运行进程、未统一撤销旧数据库客户端权限，未修改永久 DSN 或切换流量；不能声明全局唯一写权威已上线。
- 未运行完整应用 main 生命周期或 Redis outage/全部业务故障矩阵；Agent pending confirmation 与外部动作完整持久化仍待验证。
- E5 投影未激活；E6 Skill package/storage 发布未重新设计；历史文件、sidecar、Chroma 未清理。
- 按 Q35 使用通用资源身份/server UUID/allowlist 核验，不因端口是 3306 特设例外；未知监听不得视为目标。按 Q41-Q43 保留既有执行者、恢复和统一清理规则。
- 当前验证不证明旧在线流量、任意直接 SQL 客户端或其它外部进程没有写入；E4 关闭仍需最终停写、部署切换及用户验收。
