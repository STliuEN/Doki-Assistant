# E4/AR-3/S3 测试与迁移证据

## 2026-09-10 closure verification addendum

- 浏览器预检使用测试用户完成登录、笔记列表、创建、详情重载、列表持久化回显和删除清理；所有相关 HTTP 请求返回 200，session 已停止。
- SQL 只读复核确认该临时笔记的 `business.created` 和 `business.deleted` 审计事件均有 actor、scope、digest 和 correlation；删除后 `notes` 中剩余 0 行。
- live target 复核：批次 `e4-business-live-20260907` 为 `reconciled`，312 个实体全部 `reconciled`，`migration.reconciled` 审计事件 313 条；源 21 表摘要仍匹配。
- 本记录只补充当前状态，不改写下方历史 checkpoint。用户已于 2026-09-10 明确批准关闭 E4；仅关闭状态，不清理中间材料。

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

## 2026-09-08 验证矩阵

| 范围 | 结果与证据 | 状态 |
|---|---|---|
| main lifespan / 冷重启 | 3 次完整启动、2 次优雅关闭；进程内 DSN、runner 锁及 Redis pool 证据 | verified-live |
| Redis 正常/停止/恢复 | 同一应用进程恢复；依赖限流的登录、jobs、notes、write 返回 503；健康探针仍可观测；SQL 摘要无变化 | verified-live |
| Redis 停止时冷启动 | live/runner 200，ready/jobs 503；真实 runner 将故意非法持久 job 置 dead_letter / invalid_business_job，而非伪造成功 | verified-live |
| 本机前端流量 | 实际 Vite cookie 登录/刷新/注销、笔记 SQL+audit+job 原子提交及 owner-scoped polling | verified-live |
| Django 已部署旧边界 | 26 GET/POST 410；ORM 拒写、迁移 false、raw 零行 UPDATE 1290 | verified-live |
| 源冻结/恢复 | 最终源 21 表摘要无漂移；target 312 实体/314 mapping/48 FK；restore 39 表/2,539 行 | verified-live |
| 自动化回归 | 后端 491、前端 28、前端 build、Ruff、compileall | verified-local |
| 浏览器可视化、真实 LLM 矩阵、生产 DNS/LB/TLS/共享卷 | 不把本机 HTTP 与 development 配置当作生产证据 | not-run |

早期私有 `e4-redis-failure-recovery-20260908.json` 将正常登录新增 audit 行错误计入“业务无变化”，该比较为 false；没有改写成成功。随后正式矩阵以独立业务摘要、故障窗口内无业务/audit 新写核对，证据为 `artifacts/e4-cutover-redis-20260908T024931.json`。早期 HTTP 系统代理 502 和启动配置失败也保留私有日志，不作为应用验收失败或成功的替代证据。

日期：2026-09-10
最近更新：2026-09-10（用户批准关闭 E4）
状态：已关闭
负责人：Codex  
审阅/批准人：用户  
用户确认：2026-09-02 完成 Q1-Q43 执行授权；2026-09-10 完成最终审阅并明确批准关闭 E4，仅关闭状态，不清理中间材料。

本文件只记录 E4 准备和后续迁移证据。证据状态只使用 `verified-local`、`verified-live`、`blocked`、`not-run`；`fixture`、`mock`、`historical`、`observed-only` 是证据类型或限制，不是状态。`verified-local` 只证明仓库/隔离环境中的动作，不证明在线业务数据或生产切换。

## 2026-09-07 执行状态（历史，未执行项已由本轮覆盖）

| 范围 | 实际证据 | 当前限制 | 状态 |
|---|---|---|---|
| E4-01 源发现 | 21 表快照；专用只读账号、正式 allowlist；最终复查源 digest 未变 | PDF 已授权 excluded；未最终停写冻结 | verified-live |
| E4-02 身份 | 2 个 canonical 测试用户重建；314 mappings 已写；0 孤儿 | 仅当前捕获快照；旧 token 未迁移 | verified-live |
| E4-03 schema | target/restore 均 head `20260905_0008_e4_business_shadow`、39 表；48 FK 检查通过 | 未改变旧源 populated PK | verified-live |
| E4-04 批次 | 独立凭据/preflight；312 条导入，0 quarantine；重放 0 imported/312 skipped | 62 条 Skill 为必要输入迁移，不是 E6 发布 | verified-live |
| E4-04 独立恢复 | 最新 39 表/2,407 行 DDL 与行 digest 相同；全部旧备份保留 | 只证明隔离目标到 restore，不是完整应用恢复 | verified-live |
| E4-05 当前快照导入 | 6 原件 455,311 bytes，10 Skill 包和 4 个加密配置 key-version 验证 | 未停写、冻结最终输入或切换 DSN | verified-live |
| E4-06 日常写权威 | canonical owner/parent/digest、audit/job 同事务；实际业务路由/handler/SQL polling/accepted SSE 通过 | 尚未部署切流或重启旧进程；外部 tagger 为确定性 fixture | verified-live |
| E4-07 auth/runner | 2 用户认证链；真实 kill/restart、lease 回收、进程锁和 stale fencing 拒绝；业务 enrich/SQL polling/accepted SSE 追加通过 | 不是完整 main 生命周期、全部业务故障矩阵或 Redis outage | verified-live |
| E4-05 正式切换 / E4-08 验收 | 未执行 | 整体仍为 `实施中`，不可关闭 | not-run |

## 2026-09-07 日常写权威 Checkpoint（最新）

- 证据：`artifacts/e4-write-authority-20260907.json`；PDF 排除审计 `artifacts/e4-pdf-exclusion-20260907.json`。该缺失原件不再阻塞，不改其它历史源。
- 收尾门禁：文档检查 195 files / 178 local links、`git diff --check` 通过；私有目录和文件仅 owner/SYSTEM 可访问，凭据/原始快照/备份 Git ignored。8 个新增秘密值精确扫描 931 个仓库文件，0 命中；最新备份 SHA-256 复核一致。此扫描只覆盖已识别的新增秘密值，不声称仓库全面无历史秘密。
- 全量 `488 passed, 1 warning in 33.41s`；Ruff/compileall 通过。新增回归覆盖原子提交/回滚、业务/任务审计关联、owner/parent、MySQL 时间精度、Skill binding、批量/原生 SQL 绕过、fencing、副作用与结果同事务、聊天成对失败回滚、提交失败不可返回成功、E4 runner gate、Django 静态接线。
- 真实 `artifacts/e4-business-write-smoke-20260907T042611.json`：实际登录后写笔记/模板/记忆/模型/embedding/知识原文/聊天，检查 shadow/digest/audit；SQL 原件上传无 Chroma，accepted SSE 发出前已提交；job list/detail 用户隔离，手动/自动标签 2 次完成但复习记忆只 1 条。tagger 为确定性 stub，不是 LLM 能力测试。
- 旧入口：Django 自身 venv 5.2.6 RequestFactory 检查 14 个 GET/POST 路径全部 410 且 view 零调用；ORM write router 抛错，migration router 返回 False，无数据库连接。FastAPI `/tools`、`/api/mcp`、reranker/MD5 写入口在 E4 模式 410；未声称已重启旧在线进程。
- 失败与修复：初次 live 时间摘要失配来自 MySQL DATETIME 秒精度；失败 target dump `3da6d0e86a737d75dd1f696f141b549349fb2da3f836acad7b7e4d624c4bf8e9` 保留。只删除已记录 synthetic 行，审计/jobs 保留；不回退 source 或已有迁入行。
- 最终恢复 `artifacts/e4-restore-20260907T042748.json`：39 表/2,407 行，dump 2,195,497 bytes，SHA-256 `841b40167d79ee9c6ef940bd26af8db7fdc3b27474846dcdb23eff8b99a03e95`。`artifacts/e4-business-reconcile-20260907T042742.json` 确认原 312 条、314 mappings、48 FK 无漂移/孤儿；source 21 表仍一致。
- 未执行：完整 app lifespan、真实 Redis outage、实际 LLM、最终停写/切流、用户验收。未启用 E5 generation；projection jobs 保留 queued，不消耗重试伪装成功。

## 2026-09-07 较早 Live Checkpoint（历史）

- 汇总：`artifacts/e4-live-execution-20260907.json`。source 业务行和旧用户保持不变；实际新增只读账号及轮换 E4 凭据，重建仅限隔离目标测试用户。E4 容器重建保留原 volume/server UUID，E1-E3 未修改。
- 对账：`artifacts/e4-business-reconcile-20260907T021355.json`；312 条显式业务列、314 mappings、48 FK、6 份原件和 10 个 Skill archive 均通过。
- API：`artifacts/e4-api-smoke-20260907T020231.json`；真实 user router + E4 SQL 的 login/detail/refresh/logout 为 200、撤销后 401，笔记/配置 owner 数量匹配。首次 owner 失败证据 `artifacts/e4-api-smoke-20260907T015603.json` 保留。
- Runner：`artifacts/e4-runner-smoke-20260907T021331.json`；真实子进程强制结束、自然 lease 过期、重启第二次执行成功；attempt 为 abandoned/succeeded，第二 runner 无法获取 MySQL 进程锁、旧 fencing 结果被拒绝、重复 enqueue no-op/冲突拒绝。仅 synthetic handler，不冒充业务 handler 验证。
- 最终恢复：`artifacts/e4-restore-20260907T021401.json`；39 表/2,245 行全等，dump 2,112,079 bytes，SHA-256 `8f68a41cf1520550e65cbdae7baa87e920cf5d59d8ab86cd33a12943305f676e`。包含 API smoke 新 session/audit 和 runner job/attempt；此前 2,202 行证据仍保留为早期 checkpoint。
- 本地门禁：Windows venv `pytest -q` 为 `473 passed, 1 warning in 33.11s`（已有 sqlite datetime adapter deprecation）；`ruff check app tests scripts`、`compileall -q app scripts` 通过。新增 Skill/timestamp 与 owner 回归纳入全量。
- 比较口径：legacy DATETIME 字面值保留，不推断原 `SYSTEM` 为 UTC；JSON 解码比较，包括 JSON null，SQL NULL/JSON null 不宣称存储字节一致。
- 收口检查：`git diff --check` 通过；文档检查 `195 files, 178 local links` 通过；`.runtime/e4` ACL 仅 owner/SYSTEM，私有登录/凭据/备份被 Git 忽略；913 个仓库文件对本轮 9 个私有秘密值的精确匹配扫描为 0 泄漏。此扫描不撤回较早已记录的工具错误敏感输出事件。
- 尚未：缺失 PDF 处置、源停写/最终冻结、永久 DSN 切换、完整写权威、全应用故障矩阵与用户验收。

## 历史环境限制（截至2026-09-05）

- 平台：Windows / PowerShell；分支：`ai_document_assistant`；初始日期：2026-09-02；正式执行：2026-09-05。
- E1/E2/E3 资源和证据保持隔离；本准备阶段没有启动、复用或清理它们。
- 本阶段只读取仓库文档、源代码和被 `.gitignore` 排除的本地 `backend/data` 文件；未读取 `.env` 推断目标。
- 未连接在线 MySQL、Django、Redis 或 Chroma；没有用户批准的 E4 source dump、target/restore allowlist 或停写窗口。
- 其他执行者已启动 `doki-e4-business` 的 target/restore 容器；本轮只读检查 Docker 元数据和各自 `auto.cnf` 的 server UUID，未读取环境变量/凭证、未连接 MySQL、未启动/停止/重建任何容器。
- 只读 OS 观察到两个身份未确认的 `mysqld.exe` 进程；按未知现有资源保护，未探测端口、未连接、未复用，也未将其计入 E4 拓扑。

## 历史证据表（截至2026-09-05；当前状态见上表）

| ID | 环境/版本 | 拓扑 | 证据类型 | 命令/动作 | 阈值 | 实际结果 | 结果/处置 | 日志/文件 | owner | approver | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `E4-PREP-01` | UTF-8 Markdown | 仓库文件 | verified-local | 审阅架构计划、执行交接手册、蓝图、E2 Schema Ownership、E3 关闭记录和阶段模板，并回写 Q1-Q43 确认 | E4=`实施中`；上阶段 E2/E3 已关闭；真实资源仍须 allowlist/preflight | 条件核对；执行确认已收到，验收确认尚未发生 | passed；仅证明授权和阶段边界，不证明业务迁移 | `docs/architecture_rewrite_plan.md`；`docs/architecture-execution-handoff-2026-08-26.md`；本批 `plan.md` | Codex | 用户 | verified-local |
| `E4-PREP-02` | Python source tree | 无外部拓扑 | verified-local | 静态检索 SQLAlchemy/Django 模型、FK/ID 类型和 service `commit()`/文件/Chroma/Redis 写入口 | 记录所有已知业务/派生写点和与目标的差异 | 发现 chat message 整数 ID、业务 owner 无 canonical FK、多处直接 commit 与外部副作用分离 | passed；未修改或调用写入口 | `backend/app/models/`、`DjangoUserService/apps/`、`backend/app/services/`、`backend/app/rag/` | Codex | 用户 | verified-local |
| `E4-PREP-03` | Local filesystem / Chroma SQLite | 只读本地文件 | observed-only | 只读统计 Chroma collections/embeddings、MD5 sidecar、图片目录和 Skill Storage | 观察不得被当作正式 source/target 对账；不写文件 | 4 collections（16/65/7/0 embeddings，用户作用域名称已脱敏）；1 个 MD5 文件 7 条记录；图片 0 文件；Skill Storage 10 对象约 5,627 bytes | 记录为待纳入 inventory 的观察；未建立映射 | `source-inventory.md`；`backend/data/` | Codex | 用户 | verified-local |
| `E4-PREP-04` | Contract review | 仓库文件 | verified-local | 审阅并建立 source key、UUID5、digest、幂等、conflict/orphan 和 scope 合同 | 同 key 同 digest 可重放；digest 变更/碰撞 fail-closed | 合同已写入；尚未运行 dry-run 或写 `migration_maps` | passed；仅设计，不证明实现 | `identity-map-contract.md` | Codex | 用户 | verified-local |
| `E4-PREP-05` | Contract review | 仓库文件 | verified-local | 盘点唯一写入口并草拟停写/restore-forward 顺序 | FastAPI 最终唯一业务写权威；Redis/文件/Chroma 不作事实 | 写入口矩阵和回滚模板已建立；未禁用入口或执行切换 | passed；仅静态准备 | `write-path-inventory.md`、`rollback-runbook.md` | Codex | 用户 | verified-local |
| `E4-PREP-06` | Local Chroma SQLite + source review | 只读本地文件/代码 | verified-local | 查询 collection 名称与 embedding metadata 的 `user_id`/`source`，复核 reranker/calibration 来源，并检查路径是否可脱敏 | 任何 collection/metadata 身份不一致、临时绝对路径或无权威配置必须 fail-closed | `rag_e5efbb90a85fadbf`/`notes_e5efbb90a85fadbf` 的 metadata 用户 ID 为 `j6BVY9AHmHPQEbwoZabRMq`；RAG metadata 含本机临时绝对路径；reranker/calibration 无 SQL owner/revision | scope conflict 与敏感路径待处理；未建立映射、未写回源/目标 | `source-inventory.md`；`identity-map-contract.md`；`backend/data/chromadb/chroma.sqlite3` | Codex | 用户 | verified-local |
| `E4-PREP-07` | FastAPI route/static review | 仓库代码（backend `.venv`，合成 allowlist URL，仅导入路由） | verified-local | 检查并修复 `note_template_router.py` 路由注册顺序，用 `Route.matches` 验证 `PUT /note-template/reorder`；未建立数据库连接 | 具体 reorder 路由必须优先于 `/{template_id}` | 已将具体路由置于通用参数路由前；首个 `FULL` 为 `reorder_templates`，无 `path_params` | passed；代码修复和纯路由回归完成，未调用业务 API | `route-match-evidence.md`；`backend/tests/test_note_template_route_matching.py`；`backend/app/router/note_template_router.py` | Codex | 用户 | verified-local |
| `E4-PREP-08` | E3 model/Alembic schema review | 仓库代码 | verified-local | 对照 `MigrationMap.status` check constraint 与 E4 流程状态机，检查 digest 字段承载（含 legacy MD5 与 SHA-256 区分） | 未定义状态不得写入既有 schema；batch/entity/artifact digest 必须可分别对账 | 现有约束只允许 `mapped/conflict/error`，且仅有一个 `source_digest`；E4 其他状态/digest 层没有持久化承载，32 位 MD5 也不能直接填入 64 位 SHA-256 字段 | 已登记 schema 兼容门槛；未执行 DDL、未写 `migration_maps` | `identity-map-contract.md`；`backend/app/models/identity_domain.py:239-261`；`backend/alembic/versions/20260828_0003_identity_auth.py` | Codex | 用户 | verified-local |
| `E4-01` | 本地只读文件 + 待批准 source snapshot | 仓库/离线副本；在线 source 未连接 | fixture/observed-only | 在批准 source 上生成可重放 inventory manifest；在线部分须有 server identity/权限证明 | 路径 containment；digest/计数可复现；未知资源不连接 | 本地 observed-only v3 manifest 已完成；批准的正式业务 snapshot 尚未交付 | 等待正式 source；本地观察不改变本项状态 | `source-inventory.md`；`artifacts/local-inventory-v3.json` | Codex | 用户 | not-run |
| `E4-02` | E4 offline dry-run | 待批准 source snapshot | fixture/live | 对正式 snapshot 执行 identity-map dry-run、冲突/孤儿和幂等重放 | `conflict=0`、`orphan=0` 或有明确批准处置；报告 digest 可复算 | 离线工具和合成回归已完成；正式 source dry-run 尚未执行 | 等待 E4-01，不写 `migration_maps` | `identity-map-contract.md`；`backend/app/e4/identity.py` | Codex | 用户 | not-run |
| `E4-03` | E4 target schema / SQLite contract fixture | 代码 revision 已建立；live allowlist 未建立 | fixture/live | 实现并核对 additive/shadow schema、唯一约束、FK、on-delete、时间和内容 digest；保留旧主键 | 不原地改 populated 主键；model/migration parity；约束无未解释差异 | revision `20260905_0008_e4_business_shadow`、ORM shadow 字段、E4 批次/实体/媒体表和 check-constraint parity 已实现；最新完整本地 pytest `428 passed, 1 warning`，实现状态仍为 `待验证`，尚未执行 live DDL 或逐表对账 | 继续本地合同门禁；等待 E4-01/E4-02 与正式 allowlist 后再做 live gate | `plan.md`；`identity-map-contract.md`；`backend/alembic/versions/20260905_0008_e4_business_shadow.py`；`backend/tests/test_migration_contract.py` | Codex | 用户 | verified-local |
| `E4-04` | E4 SQLite fixture / target-restore topology | 隔离 fixture 可用；live target/restore 正式 allowlist 缺失 | fixture/live | 验证批次/实体幂等、状态机、mapping target/digest 冲突、UoW rollback、audit correlation、SQL 媒体字节重放和跨批次同源幂等；核对容器、备份和权限 preflight | fixture 重放为 no-op；篡改/漂移 fail-closed；live container/image/network/port/database/server UUID 精确匹配 | 离线 repository/fixture 已实现，包含请求/UoW post-commit 回调边界、提交前/提交后笔记投影、post-commit cancellation、partial finalize 防护、CLI blocked 返回码和会话管理器事务 helper 回归；最新完整本地 pytest `428 passed, 1 warning`；2026-09-05 recheck 显示 target/restore 均 `Exited (255)`、E4 network 无连接、restore 历史账号与当前 compose 不一致，且 formal allowlist/credential/backup/schema 权限事实缺失 | 离线实现状态 `待验证`；live preflight 标 `阻塞`，不连接 MySQL、不重建容器 | `backend/app/e4/repository.py`；`backend/app/e4/importer.py`；`backend/app/db/transaction_context.py`；`backend/app/services/database_session_manager.py`；`backend/scripts/e4_import.py`；`backend/tests/test_e4_repository.py`；`backend/tests/test_e4_importer.py`；`backend/tests/test_e4_cli.py`；`backend/tests/test_database_session_manager_transactions.py`；`backend/tests/test_skill_service_transactions.py`；`backend/tests/test_note_service_transactions.py`；`backend/ops/e4/README.md`；`artifacts/e4-topology-recheck-20260905.json` | Codex | 用户 | blocked |
| `E4-05` | 批准 source -> E4 target | 待停写批次 gate | live | 记录实际停写窗口，执行只读 snapshot、目标导入及行数/digest/约束/审计对账 | source digest 无漂移；零未解释差异；失败只走 restore-forward | 尚未执行停写、导入、备份或 restore-forward | 等待 E4-01 至 E4-04；不增加第三次用户确认 | `rollback-runbook.md` | Codex | 用户 | not-run |
| `E4-06` | FastAPI + legacy write paths | 待 E4-05 对账 | live | 分领域切换 FastAPI 唯一业务写入口；Django/旧脚本/文件改为只读或显式运维操作 | 长期双写为零；业务成功只依据 SQL commit；派生操作使用 durable job | 尚未执行停写或写权威切换 | 等待 E4-05 | `write-path-inventory.md` | Codex | 用户 | not-run |
| `E4-07` | API/SSE/polling/SQL runner | 待 E4-06 切换 | live | 验证 API、SSE/polling、重复/乱序、lease/fencing、kill/restart、timeout/cancel/error/orphan | SQL 事实可按 correlation ID 对账；旧 fencing token fail-closed；Redis/Chroma 不决定业务成功 | 尚未执行 live 行为或故障注入 | 等待 E4-06 | `write-path-inventory.md`；`rollback-runbook.md` | Codex | 用户 | not-run |
| `E4-08` | E4 完整证据包 | 待 E4-01 至 E4-07 | review | 实现者提交 `待验证`，核对三件套、正式证据、失败现场和回滚结果，再交用户第二次验收 | 全部退出条件满足；用户明确验收后才可关闭 | 尚未提交待验证，用户验收确认尚未发生 | 保持 `实施中`；不提前关闭或清理 | `plan.md`；`change-log.md`；`test-record.md` | Codex | 用户 | not-run |
| `E4-PREP-09` | Python 3.12.3；pytest 9.1.0；Ruff 0.15.17 | 当前工作树；无外部拓扑 | verified-local | 修正 `E4Target` tuple/list 快速路径校验；运行 `pytest -q tests/test_e4_guard.py tests/test_e4_inventory.py tests/test_note_template_route_matching.py`、Ruff、`compileall`、`git diff --check`、`scripts/check-docs.ps1` | 22 个定向测试通过；静态/文档门禁 exit 0；不得连接或写入业务资源 | `22 passed`；Ruff/compileall/diff check 通过；文档 `194 files, 178 local links` 通过；未建立网络/数据库连接 | 通过；仅证明本地守卫、inventory 和路由合同；在线业务证据仍 not-run | `backend/app/db/e4_guard.py`；`backend/tests/test_e4_guard.py`；`artifacts/local-inventory-v3.json` | Codex | 用户 | verified-local |
| `E4-PREP-10` | backend `uv` frozen environment | 当前工作树；无外部拓扑 | verified-local | 重跑 E4 guard/identity/inventory/route gate；修正无 source metadata 的既有 target 冲突分类，并确保 canonical UUID 显式拒绝大写 | 30 个定向测试和相关 Ruff 检查全部通过；不得连接或写入业务资源 | `30 passed in 0.75s`；`All checks passed!` | 通过；身份 dry-run 保持 fail-closed；真实 source/target/restore 仍 not-run | `backend/app/e4/identity.py`；`backend/tests/test_e4_identity.py` | Codex | 用户 | verified-local |
| `E4-PREP-11` | Python 3.12 / backend `.venv`；合成快照和 allowlist | 当前工作树；无外部拓扑 | verified-local | 身份/守卫边界回归：标准 UUID 保留、Django ShortUUID 大小写、既有 target UUID 复用、artifact digest 报告、专用账号、DSN query、migration switch、完整拓扑、保护 E1-E3 资源和 database facts | 关键身份和资源 mismatch 必须 fail-closed；报告摘要可复算；不得连接真实资源 | `37 passed`（E4 identity/guard/inventory/route）；身份报告 digest 自洽；未写 `migration_maps`；compose 未启动 | 通过；仅证明离线代码合同和合成 guard，不证明在线资源 | `backend/app/e4/identity.py`；`backend/app/db/e4_guard.py`；对应 E4 测试 | Codex | 用户 | verified-local |
| `E4-PREP-12` | Python 3.12.3；pytest 9.1.0；Ruff 0.15.17 | 当前工作树；无外部拓扑 | verified-local | `pytest -q`、Ruff、Python `compileall`、`git diff --check`、`docker compose config --quiet`、`scripts/check-docs.ps1` | 全量测试通过；静态/Compose/文档门禁 exit 0；不得启动容器或建立数据库/网络连接 | `391 passed`（1 个既有 aiosqlite 弃用警告）；Ruff `All checks passed!`；compileall/diff/Compose config 通过；文档 `195 files, 178 local links` 通过 | 通过；E4-01 至 E4-08 仍未运行，真实 source/target/restore 仍 not-run | 命令输出；本文件；`change-log.md` | Codex | 用户 | verified-local |
| `E4-PREP-13` | Python 3.12；backend `.venv`；合成快照/allowlist | 当前工作树；无外部拓扑 | verified-local | 审阅加固：确定性显式 UUID、source/target/restore purpose 矩阵、精确数据库账号、独立 container inspector、target/restore 分离凭证、immutable image ID、运行时 health drift 和拓扑命名回归；运行 E4 定向测试 | 关键身份、角色用途、账号和容器事实 mismatch 必须 fail-closed；不得连接或写入真实资源 | 过程成功点 `40`、`42`、`43`、`47` passed；移除超出架构要求的 source/server 独立限制后最终 `46 passed in 0.79s`；未启动 Compose，未建立数据库/网络连接；非确定性 UUID、跨角色用途、账号漂移、缺失独立 inspector/image ID 和 unhealthy runtime 均按预期拒绝 | 通过；仅证明离线代码合同；E4-01 至 E4-08 仍 `not-run` | `backend/app/e4/identity.py`；`backend/app/db/e4_guard.py`；`backend/ops/e4/`；对应测试 | Codex | 用户 | verified-local |
| `E4-PREP-14` | Python 3.12.3；pytest 9.1.0；Ruff 0.15.17；Docker Compose config | 当前工作树；无外部拓扑，Compose 未启动 | verified-local | 加固后执行 `uv run pytest -q`、Ruff、`compileall`、`git diff --check`、`docker compose config --quiet`、`scripts/check-docs.ps1`；首次无 Compose 凭证变量的调用按预期拒绝，随后仅在进程环境注入占位值重跑 | 全量/静态/Compose/文档门禁通过；不启动容器、不建立数据库/网络连接；不记录凭证值 | 首轮 `394 passed, 1 warning`；最终门禁首次为 `395 passed, 1 failed`，失败是既有 `test_cancellation_request_prevents_success_commit` 在 1 秒 SQLite lease 下暂留 `cancel_requested`；该单测并行连续 8 次通过，完整复跑最终 `396 passed, 1 warning`（既有 `aiosqlite` 弃用警告）；Ruff、compileall、diff check、文档 `195 files, 178 local links` 通过；Compose 无变量拒绝，临时占位值重跑通过；未启动容器 | 通过并保留瞬时失败；未扩张范围修改 E2 runner；E4-01 至 E4-08 仍 `not-run` | pytest 输出；`backend/ops/e4/docker-compose.yml`；`backend/ops/e4/README.md` | Codex | 用户 | verified-local |
| `E4-PREP-15` | Python 3.12.3；pytest 9.1.0；Ruff 0.15.17；Docker Compose config | 当前工作树；合成 allowlist；已有 E4 容器未参与测试 | verified-local | 复核其他执行者的 E4 改动；将容器事实存在性和 allowlist 一致性检查移到数据库 inspector 前；增加缺失/漂移容器事实时数据库 inspector 零调用断言；重跑定向、全量和静态门禁 | 容器型目标未通过独立拓扑检查前不得发起数据库检查；全量/静态/Compose/文档门禁 exit 0；不得连接真实资源 | E4 定向 `46 passed in 0.77s`；首次全量 `399 passed, 1 failed, 1 warning`，失败是既有 `test_runner_start_and_graceful_stop` 在等待窗内计数仍为 `0`；该单测随后连续 8 次通过；最终完整复跑 `400 passed, 1 warning in 23.10s`；Ruff、compileall、diff check、Compose config 和文档 `195 files, 178 local links` 全部通过；未对已存在容器执行 mutation，未建立数据库连接 | 通过并保留瞬时失败；未修改 E2 runner；E4-01 至 E4-08 仍 `not-run` | `backend/app/db/e4_guard.py`；`backend/tests/test_e4_guard.py`；`backend/ops/e4/README.md`；命令输出 | Codex | 用户 | verified-local |
| `E4-PREP-16` | Docker Engine；MySQL 8.4 image；只读容器文件 | `doki-e4-business` target/restore | verified-live | `docker compose ls/ps`、定向 `docker inspect`、network/volume/image inspect；只读 `docker exec ... grep '^server-uuid=' /var/lib/mysql/auto.cnf` | 仅 E4 专用名称；两个独立 container/server UUID/volume；单一 E4 network；端口只绑定 `127.0.0.1:33427/33428`；running/healthy；不得读取凭证或连接数据库 | target `ab8ece...e6ecc` / server `0c0d3e33-a743-11f1-af41-ea47e0ceb469`；restore `d007b0...2c58b` / server `0bf5339b-a743-11f1-9ab9-febdaaf248fb`；共同 immutable image `mysql@sha256:b3b90a...fd3fb`；network `729648...0c17` 恰含两个 E4 容器；两个独立 E4 volume；均 `RestartCount=0`、healthy | Docker 拓扑观察通过；数据库身份/账号/权限/schema、正式 allowlist/preflight 和业务数据均未验证；E4-04 保持 `not-run` | `artifacts/e4-topology-observation-20260903.json`；文件 SHA-256 `1c96e6355a646edde68a4eabd229043a1332009308a510a10c02f4c7f71ec946` | Codex | 用户 | verified-live |

| `E4-PREP-17` | Python 3.12.3；pytest 9.1.0；Ruff 0.15.17 | 当前工作树；合成 allowlist/preflight；已有 E4 容器未参与测试 | verified-local | 前移 approval token 和 TTL 检查；消费容器型 preflight 时先用记录事实完成静态校验，再调用 live inspector 并二次比对；增加缺 token、TTL 非法、preflight 过期时 container/database inspector 零调用断言 | 所有纯输入错误必须在任何 injected inspector 前 fail-closed；完整和静态门禁通过；不得连接真实数据库 | 定向 `46 passed in 1.05s`；完整 `400 passed, 1 warning in 24.16s`（既有 `aiosqlite` 弃用警告）；Ruff、compileall、diff check、Compose config、文档 `195 files, 178 local links` 全部通过 | 通过；未调用 E4 live inspector 或连接 MySQL；E4-01 至 E4-08 仍 `not-run` | `backend/app/db/e4_guard.py`；`backend/tests/test_e4_guard.py`；命令输出 | Codex | 用户 | verified-local |

| `E4-PREP-18` | Python 3.12.3；pytest 9.1.0；Ruff 0.15.17；Docker 只读元数据/`auto.cnf` | 当前工作树；合成 allowlist/preflight；现有 E4 容器仅做只读复核 | verified-local | 移除 guard 消费接口的静态 `container_facts` 旁路；验证过期/篡改记录在 inspector 前拒绝、缺 inspector 拒绝、旧静态参数不可注入、health 漂移拒绝和健康 facts 成功消费；复核 P16 拓扑 | 容器型 guard 每次消费都必须由显式 inspector 提供当前事实；纯输入错误零 inspector 调用；E4 拓扑不得漂移；不得连接数据库或改变容器 | 定向 `46 passed in 1.10s`；完整 `400 passed, 1 warning in 23.78s`（既有 `aiosqlite` 弃用警告）；`ruff check app tests scripts`、compileall、diff check、Compose config、文档 `195 files, 178 local links` 通过；根范围 `ruff check .` 对 3 个未修改基线文件报告 7 项既有问题；P16 container/image/network/port/volume/health/restart/server UUID 和 artifact SHA-256 均未漂移 | 本批 E4 范围通过；根范围 Ruff 失败不作为绿色证据且未越界修改；未调用 MySQL、未执行 Docker mutation；E4-01 至 E4-08 仍 `not-run` | `backend/app/db/e4_guard.py`；`backend/tests/test_e4_guard.py`；`backend/ops/e4/README.md`；P16 artifact；命令输出 | Codex | 用户 | verified-local |

## 数据对账

- 当前尚未执行 source/target/restore 业务行数对账；本地 Chroma/MD5/图片/Skill 数量仍只是 `observed-only`，不构成迁移证据。
- E4 Docker target/restore 拓扑已在 `E4-PREP-16` 历史观察后于 2026-09-05 只读 recheck；该 recheck 显示容器退出、网络无连接且缺少正式身份/权限事实，不能作为业务对账或通过 preflight 的证据。
- 已生成脱敏离线 `artifacts/local-inventory-v3.json`：canonical manifest digest `7566814bfc0e4a16a9c61988d41074e2c486982840563853ded176f3e8ddb0ac`；文件封装 SHA-256 `8c018624c28192a7e84000ca6b1f455d08ee57d172a6c81792d9cf7058bf7faf`。canonical digest 按工具定义排除 `captured_at` 与自身摘要字段，不能替代正式 source snapshot digest。
- v3 计数为 4 collections/88 embeddings、MD5 7 records/7 values、图片 0 files、Skill objects 10；发现 2 个脱敏 `scope_conflict`。这些结果只作为本地观察，不能写入 `migration_maps` 或目标业务表。
- 后续仍必须分别记录 batch manifest digest、逐表/逐对象 content digest 和原始文件/归档 artifact digest；尚未生成正式业务 source manifest、`migration_maps`、目标业务行或审计 correlation。
- generation/active pointer 不在 E4 本批激活；Chroma 只作为待核验派生输入，正式重建属于 E5。

## 负向与恢复覆盖

- 本轮全量门禁首次出现既有 `test_unknown_job_type_is_dead_lettered_and_counted` 的调度竞态（`425 passed, 1 failed, 1 warning`，单次 `run_once()` 后状态暂留 `running`）；未修改 E2 runner，立即完整复跑通过 `426 passed, 1 warning`，失败现场保留并列入 E4-07 live runner 验证。

- 历史过程失败：首次收紧确定性 target UUID 后，旧碰撞夹具依赖任意显式 UUID，定向结果为 `35 passed, 2 failed`；夹具随后改为确定性 UUIDv5 与 canonical UUID 的真实碰撞场景，并新增任意显式 UUID 拒绝回归。该失败不作为绿色证据，也未被删除。
- 历史过程失败：精确校验既有 mapping 后，旧重复 target 夹具先触发其自身非法 UUIDv5（`41 passed, 1 failed`）；夹具改为两个各自合法但碰撞的 source key，并新增非法既有 mapping 拒绝回归。该失败不作为绿色证据，也未被删除。
- 历史过程失败：最终全量门禁一次出现 `test_cancellation_request_prevents_success_commit` 的 1 秒 lease 瞬时竞态（`395 passed, 1 failed`，状态停在 `cancel_requested`，未错误提交 success）；同一测试随后连续 8 次通过，完整套件复跑 `396 passed, 1 warning`。该既有 E2 runner 残余风险保留到 E4-07 live lease/fencing 验证，不在 E4 准备阶段隐式重构。
- 历史过程失败：本轮复核首次全量门禁出现 `test_runner_start_and_graceful_stop` 的调度等待竞态（`399 passed, 1 failed, 1 warning`，等待窗内 `succeeded_count=0`）；同一测试随后连续 8 次通过，最终完整套件复跑 `400 passed, 1 warning`。同样保留到 E4-07 验证，不在准备阶段修改 E2 runner。
- 无效校验命令：首次 topology artifact 一致性脚本因 PowerShell `-not`/`-ne` 表达式缺少括号误报 `running mismatch`；修正为显式布尔转换和括号后，container/image/running/health/restart/network/port/volume/server UUID 及 artifact SHA-256 全部匹配。该误报不作为资源失败证据，也未删除其上下文。
- 本轮扩展静态检查 `ruff check .` 返回 7 项既有问题：`mcp_servers/powershell_ls_server.py`、`mcp_servers/public_info_server.py` 的 import 顺序，以及 `seed_templates.py` 的 import 顺序和 4 个超长行；三者均未在当前工作树修改且不属于 E4 改动。`ruff check app tests scripts` 通过；失败输出保留，不把范围门禁通过改写成仓库根全绿。
- 已设计但未执行：unknown/duplicate identity、digest 漂移、FK/唯一冲突、重复/乱序、租约过期、旧 fencing token、kill/restart、超时、取消、异常、孤儿 job。
- 已设计但未执行：停写窗口、snapshot manifest、restore-forward、恢复后 revision/行数/digest/FK/audit 对账。
- 已修复并回归：笔记模板 reorder 路由冲突（`E4-ROUTE-01`）。
- 已修复并回归：分批导入在缺少前置实体时禁止 finalize，quarantine 结果显式标记 `blocked`，CLI 对 blocked 批次停止继续分批并返回非零码。
- 已修复并回归：E4 allowlist dataclass 快速路径校验绕过、DNS host 大小写端点重复检测和 DSN host 大小写匹配（`E4-PREP-09`）。
- 仍待 gate：加密配置 key 版本/重加密方案、图片 SQL 表、source/target/restore 身份和 allowlist。
- 未连接或注入 Redis/Chroma；未做真实文件删除、旧 generation 清理或 Django/旧脚本停写。
- 本轮正式执行仍未连接 MySQL/Django/Redis/Chroma；仅对已有 E4 Docker 元数据和历史 `auto.cnf` 证据执行只读 recheck，没有执行 live DDL、真实 `migration_maps` 写入、停写、切换、删除或 GC。

## 2026-09-05 正式执行记录

- `E4-03`：代码层 revision、ORM shadow 字段、受控旁表、媒体 SQL 模型和约束合同已实现；最新完整本地 pytest `428 passed, 1 warning`，仍提交为 `待验证`，不等同于 live schema 已迁移。
- `E4-04`：SQLite 隔离 fixture 覆盖批次/实体幂等、状态机、mapping 冲突、rollback、审计 correlation、媒体字节重放及跨批次同源幂等；补充 partial finalize 防护、quarantine blocked 结果、CLI 非零返回码和会话管理器事务 helper 回归；最新完整本地 pytest `428 passed, 1 warning`。请求/UoW 提交后回调、笔记提交/回滚投影及 post-commit cancellation 回归通过，笔记外部投影不再早于 SQL commit；live topology/preflight 因 recheck 中的退出容器、网络断开、账号漂移及缺少 allowlist/credential/backup/schema 权限而 `阻塞`。
- 静态门禁：`uv run ruff check app tests scripts`、`uv run python -m compileall -q app scripts`、`git diff --check` 均通过。

## 2026-09-07 较早执行记录（历史；当前状态见顶部 Live Checkpoint）

- `E4-01` / `E4-02`：真实只读审计与身份 dry-run 已完成。证据 `artifacts/e4-source-audit-20260906.json` 记录 314 个规范化身份、0 个冲突/orphan/重复，snapshot 内容 SHA-256 为 `11e6c61c7518f3af945377d774df57b44c46f995f7ccecf44ac1bc38f0b2847a`；不构成导入授权。
- `E4-04`：证据 `artifacts/e4-resource-discovery-20260907.json` 记录 target `ab8ece...` / restore `d007b0...`、独立 server UUID、端口 33427/33428、空库 0 表和当前权限。两个容器启动且健康，但未签发 preflight。
- `E4-04` 阻塞：target/restore app/root 凭证分别共享；source 发现使用 root 而非专用只读账号；缺少正式 `E4_ALLOWLIST_FILE`、restore-forward 演练和 1 个历史 PDF 原件。不得用推断或生成值替代用户批准输入。
- `E4-03` / `E4-04` 接线：证据 `E4-04-GUARD-WIRING-20260907` 记录 Alembic 与应用启动 inspector 注入修复；基线定向 `65 passed`，基线完整 `447 passed, 1 warning`，Ruff/compileall/diff check 通过。
- `E4-04-PAYLOAD-20260907`：先以 CLI 隔离回归复现 `11 failed, 2 passed`（缺失业务 adapter/行/必填列/密钥版本仍返回成功，或在校验前进入目标 guard）。新增 `app/e4/payload.py` 并接入 CLI 后，增加文档/媒体字节与脱敏回归，CLI 定向 `24 passed`。底层配置 quarantine 状态机不变；全量结果在收口记录中补记。
- 真实快照内存探测：`artifacts/e4-source-payload-probe-20260907.json`；314 条身份通过，250 条有对应业务 adapter，64 条 user/Skill 需另外适配，4 条已支持配置缺失 key-version；返回 blocked 是预期 gate 失败，不是已完成导入。未重新连接数据库，未保存业务 bundle。
- 执行期故障保留：跨平台 Bash `uv` 误重建了 Windows `.venv`，已用 Windows `uv sync --frozen --extra dev` 恢复，未更改锁文件。一次 PowerShell 默认编码解析失败将私有快照正文、密码哈希及配置密文带入工具错误输出；不能声称本轮零敏感输出。后续改用 UTF-8 结构化解析、异常脱敏和只输出计数/digest；原始快照未加入 Git。
- 本轮包含先前记录的只读源/目标查询和启动既有 E4 容器；不存在真实业务写入、DDL、停写或切换。测试体、失败现场及快照保留，不清理旧输入。
- 最终回归：CLI 与 importer 定向 `38 passed`，全量后端 `470 passed, 1 warning`（30.45s，既有 aiosqlite/Python 3.12 datetime adapter 弃用警告）；Ruff、compileall 和按仓库默认换行设置运行的 `git diff --check` 通过。文档检查 `195 files, 178 local links` 通过；锁文件和 pyproject 未变。
- 续跑兼容：新增回归确认纯载荷校验不把未随 bundle 提供的目标用户事实当作不存在；live 请求仍由 guard 后的 importer 查询权威用户/映射，再验证 FK/所有权。已知载荷错误则在 guard 前拒绝。源码内存探测用 `audit_payload.py --verify` 重放，与既有脱敏工件一致，预期 blocked 结果为 64 条 unsupported + 4 条 missing-key-version。

## 不能证明的内容

- 静态审阅、本地文件观察、SQLite、mock 或 fixture 不能证明 MySQL 事务/锁、真实源数据完整性、在线流量无双写、停写成功或生产恢复能力。
- E2/E3 关闭证据不能替代 E4 业务对象、文件、图片、Skill、Chroma metadata 或迁移映射对账。
- 现有 service 的绿色测试不能证明 FastAPI 已成为所有业务写入的唯一权威，也不能证明 Redis pending 不再影响正确性。

## 关闭规则

1. 用户确认 E4 计划后，本批可标为 `实施中`；真实资源相关实施项仍须各自通过 allowlist/preflight/backup gate。
2. 实现完成只能先标 `待验证`；审阅人核对真实证据和回滚后，用户明确确认才能标 `已关闭`。
3. 任一 mismatch、fail-open、双写、审计缺字段、未知 revision、孤儿无法解释或恢复不可执行，立即标 `阻塞`，不得删除旧输入。

## 清理与保留

阶段内保留全部测试体、失败/无效现场和可重建中间材料；所有 E 编号阶段完成并经最终验收后，统一删除原始敏感材料、临时 fixture 和可重建中间体，保留脱敏 manifest、审计、摘要、错误报告、备份及 restore-forward 证据。
