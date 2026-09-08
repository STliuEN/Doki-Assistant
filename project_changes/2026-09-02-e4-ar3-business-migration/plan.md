# E4/AR-3/S3 业务数据迁移与唯一写权威

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
最近更新：2026-09-08（本机生命周期/Redis 故障、源冻结、旧进程封闭和本地切流通过）
状态：实施中  
负责人：Codex  
审阅/批准人：用户  
用户确认：2026-09-02，用户完成 E4 grilling 并确认按本计划实施；2026-09-05 明确要求停止 prep、直接执行 E4 改动。授权包含分批 inventory、导入、停写窗口内切换和 FastAPI 唯一业务写权威，不授权删除旧输入。

## 执行授权与确认纪律

- **执行确认（已收到）**：用户对本计划作完整审阅后，以本轮 Q1-Q43 答案一次性授权 E4 计划内的开发、只读盘点、隔离演练、分批导入、停写和 FastAPI 切换。授权不覆盖未列入 allowlist 的资源、未知 server UUID、未知密钥版本、删除旧输入或后续 E5/E6/E7/E8 阶段。
- **验收确认（尚未发生）**：实现和证据完成后，本批只能先标为 `待验证`；用户第二次审阅并明确验收后，才可标为 `已关闭`。
- 分批 gate、checkpoint、暂停/恢复和回滚记录属于执行证据，不增加用户确认次数。
- 用户要求 Q41 由本执行者接手；Q42 确认按文档执行；Q43 要求参照 E0-E3 的状态机、证据、恢复和清理方式。
- **正式执行指令（已收到，2026-09-05）**：用户要求停止 prep，直接执行 E4 改动。本轮不再新增 `E4-PREP-*` 编号；历史 prep 记录仅作为历史证据保留。

## 暂停/恢复记录

- 2026-09-03：按用户要求结束上一轮执行并记录收口；本轮收到“继续执行 E4 准备”后恢复，仅处理离线代码/文档证据。
- 恢复范围：修正 `E4Target` 已解析 tuple/list 的逐项校验，重跑 E4 守卫、inventory、路由回归和静态门禁，并把本地 v3 manifest 纳入证据索引。
- 恢复限制：不调用子智能体；不连接 MySQL、Django、Redis、Chroma 或未知 `mysqld.exe`；不执行 DDL、`migration_maps` 写入、停写、切换、删除或 GC。

## 2026-09-05 正式执行记录

- 已停止 prep 流程并进入正式 E4 改动。后续变更只关联 `E4-01` 至 `E4-08`，不再新增 `E4-PREP-*`。
- `E4-03`：已实现最终数据库的 additive/shadow Alembic revision、canonical UUID/digest 约束、E4 批次/实体/媒体 SQL 表、事务式 repository 和 ORM/revision 合同测试；实现状态为 `待验证`，未执行 live DDL。
- `E4-04`：已完成 SQLite 隔离 fixture 的批次幂等、实体状态机、mapping target/digest 冲突、UoW 回滚、SQL 媒体字节重放和审计脱敏回归；实现状态为 `待验证`。2026-09-05 topology recheck 显示 target/restore 均已退出且正式 allowlist、凭证引用、备份位置和 schema/权限事实缺失，live preflight 标记为 `阻塞`。
- 事务边界收尾：请求托管 session 与 `SqlUnitOfWork` 统一采用提交后回调；笔记 Chroma 写入/删除及自动标注不再发生在 SQL 提交前，外部投影失败不改变已提交业务事实。媒体 SQL 资产的同源重放不再受 `migration_batch_id` 变化影响，内容/字节/digest 漂移仍 fail-closed。
- 最新本地门禁：后端 `pytest` 为 `428 passed, 1 warning`；`ruff check app tests scripts`、`compileall`、`git diff --check` 和文档链接检查均通过。该证据仍只证明离线实现，不替代 live DDL、业务对账或停写切换。
- 当前不读取凭证、不连接 MySQL/Django/Redis/Chroma，不执行真实 `migration_maps`/业务表写入、停写、切换、删除或 GC。

## 2026-09-06 执行续接（UTC）

- 用户要求继续协助执行 E4；沿用既有执行授权和批次 gate，不新增 prep 编号，不扩大资源或删除范围。
- 本轮先实施 `E4-04` 缺失的可执行 preflight 签发 CLI：只接受显式进程环境，先验证 allowlist、角色、开关、TTL 和当前容器身份，再允许只读数据库身份检查；不自动签发 allowlist，不读取 `.env`，不替代 schema/权限、备份、正式 source 或停写 gate。
- 证据 ID：`E4-04-PREFLIGHT-CLI-20260906`；回滚点：仅撤销本轮新增 CLI、测试及对应操作说明，不改变既有迁移器、数据库或容器。
- 2026-09-06（UTC）只读复核显示原 E4 target/restore 仍为 `exited`、退出码 `255`，网络连接为空；本地 E4 环境变量和 `backend/.runtime/e4` 正式输入未提供。不得从已有容器环境中提取凭证或猜测正式 source。
- 本轮状态先记为 `实施中`；测试结果与现场证据完成后回写，真实迁移保持受阻，不把离线实现标成 live 完成。
- 用户随后明确要求自行从数据库和工程定位缺失信息。本轮据此读取工程配置及 E4 容器凭证，仅在内存使用秘密值；配置指向的 `chat_history` / `user_service` 已通过只读事务确认同属 MySQL server UUID `13e60c20-6874-11f1-8e4a-bcfce7d65b5f`，不再将其记作未知进程或未提供 source。该授权允许只读发现，不代表正式迁移 gate 自动通过。
- `E4-01` / `E4-02` 续接：在上述精确 source 身份下生成一致性只读快照、脱敏计数/digest 和关联完整性报告。原始快照仅保存于被 Git 排除且关闭 ACL 继承的 `.runtime/e4`；不读取其他业务库，不修改源库账号、schema 或业务行。证据 ID：`E4-01-SOURCE-20260906` / `E4-02-SOURCE-AUDIT-20260906`；回滚点为撤销本轮采集工具，不删除快照或旧输入。
- `E4-04` 只读发现：两个现有 E4 容器的 Compose 标签精确指向本仓库，ID/image/volume/端口与历史记录一致；通过停止容器的 `auto.cnf` 流重新确认两个独立 server UUID。容器内实际 restore 账号仍为 `doki_e4_app`，且 target/restore 的 app/root 密码分别相同。允许仅启动这些已核验的原容器以读取身份、schema 和权限；不重建容器、不改凭证、不执行 DDL/导入/切换。共享凭证问题继续作为正式隔离 gate，不伪造独立凭证引用。

- `E4-03` / `E4-04` 接线修复：发现 Alembic 与应用启动消费 E4 guard 时未注入必需的当前容器 inspector；先增加隔离回归复现，再只补齐 E4 分支，保持 E2/E3 分支不变。证据 ID：`E4-04-GUARD-WIRING-20260907`；回滚点为撤销本轮两处 inspector 接线和测试，不触碰真实 schema。
- 2026-09-07 续接核对：`artifacts/e4-resource-discovery-20260907.json` 证明已启动既有 target/restore 并完成只读身份/schema/权限观察；`artifacts/e4-source-audit-20260906.json` 证明 314 个身份在真实 source 上 dry-run 通过。正式 preflight 仍不得签发，原因保持：target/restore 凭证不独立、source 使用 root 而非专用只读账号、缺少正式 allowlist/restore-forward gate，以及 1 个历史 PDF 原件缺失。

## 2026-09-07 业务载荷校验续接

- `E4-04`：现有 CLI 的 `--dry-run` 仅运行身份映射，不能识别尚无业务 adapter 的 user/Skill 实体、缺失行载荷、必填列、文档字节或密钥版本。本轮补充纯离线载荷报告，并在 CLI 打开目标连接前拒绝已知失败载荷；不改变底层 importer 的配置 quarantine 状态机。
- 证据 ID：`E4-04-PAYLOAD-20260907`。先以隔离 CLI 回归复现 false-success，再修复并对已捕获快照做内存转换探测。报告仅保留 source-key 摘要/问题代码，不保存密码、密文或业务正文；不把转换探测称作正式导入 bundle。
- 回滚点：撤销本轮载荷校验模块、CLI 接线和相应测试；保留历史证据和源快照，不执行任何数据库写入、凭据轮换或资源重建。
- 真实快照探测已执行：`artifacts/e4-source-payload-probe-20260907.json` 记录 314 个身份仍通过，但只有 250 条落在当前业务 adapter 范围；另 2 个 Django 用户须经 E3 canonical 用户引导/映射，62 条 Skill 记录须完成 E4 必要输入适配，不能扩大到 E6 完整发布。支持范围内另有 4 条配置缺少 `api_key_key_version`，当前整批载荷 blocked。探测只在内存解码已核验快照的日期/字节/JSON，不输出可导入文件、不推定历史时区、不写目标库。
- 最终验证：定向 `38 passed`，完整后端 `470 passed, 1 warning`，Ruff/compileall/diff/docs 门禁通过；源探测重放一致。上述通过只证明当前代码和已捕获源的离线载荷检查；E4-03/E4-04 的 live DDL/凭据/恢复 gate 仍阻塞，E4-05 至 E4-08 尚未执行。

## 2026-09-07 测试用户重建授权与 live 执行

- 用户明确说明数据库用户均为测试数据，允许推倒重做并要求执行。本轮采用最小影响方案：在独立 E4 target 重建 canonical 测试用户与其迁移映射，优先保留可迁移业务；不把该授权扩展为删除源库、文件原件、历史快照或 E1–E3 资源。
- `E4-04`：允许执行者生成并保存在 Git 忽略、受限 ACL 目录内的随机 E4 独立密码及批次 token，不再要求用户手填 4 个密码。仅对已核验的 E4 target/restore 轮换数据库账号和更新容器配置，保留原数据卷与 server UUID；为已识别源创建最小权限只读账号，不改变源业务行。
- 顺序：先保存 E4 容器元数据/账号恢复材料并核验空库；建立正式 allowlist 与 preflight；执行 target Alembic；备份/恢复演练；在同一事务重建两名 canonical 测试用户、角色/映射/审计；再按已核验快照导入支持的业务域并对账、重放。Skill 和缺失原件不因用户可重建而自动丢弃。
- 证据 ID：`E4-04-LIVE-20260907` / `E4-03-LIVE-20260907` / `E4-05-TEST-USERS-20260907`。每个操作记录独立结果；配置密钥版本必须有实际解密/指纹证据，不猜测。未通过完整数据与切换 gate 前不改当前服务 DSN，不宣称 E4 已关闭。
- 恢复路径：保留旧源和旧凭据私有记录、源快照及 target dump；故障现场保留，优先恢复到独立 restore，不执行源库清空或 populated downgrade。
- 已通过 live 身份 gate 并执行 Alembic head，target 共 39 表；第一次独立 restore-forward 逐表 DDL/行摘要完全一致。两名 canonical 用户已通过 E3 身份导入函数在 E4 guard 下重建，随机登录密码只保存私有目录；source 用户未改动。
- `E4-04` / `E4-05` 下一批：补充既有 Skill 输入表 adapter（只复制和验证旧事实，不创建新发布）；保留旧 PK 与 FK、E4 mapping 旁表记录 canonical 身份。增加 ISO datetime 载荷转换和 Skill 依赖/重放回归；配置仅在当前工程密钥实际解密通过后登记指纹版本。逐批业务导入仍在隔离 E4 目标，不构成应用切换。
- `E4-06` 实测发现：真实认证 API 登录/刷新/注销均通过，但现有笔记/配置 SQL 查询仍比较 legacy `user_id`，canonical 登录后不可见迁入数据。本轮增加统一 owner predicate：已迁移记录以非空 `canonical_user_id` 为准；只有 shadow 为空才保留旧 ID 路径，禁止旧 ID 越过非空 canonical owner。覆盖会话、笔记/模板、记忆、知识文档、模型/Embedding 服务查询，不重写源 ID，不用全局认证 ID 降级绕过。

- 本轮最终 checkpoint：312 条业务、2 个用户、314 mappings、48 FK、6 份原件 455,311 bytes 和 10 个 Skill archive 均对账；重放 0/312。真实 runner 子进程强制结束后重启回收 lease、旧 fencing 拒绝、第二 runner 排他验证通过。
- `2026-09-07T02:14:01Z`（台北 10:14:01）重新备份并恢复到独立 restore，39 表/2,245 行 DDL 和行摘要全等。备份 SHA-256 `8f68a41cf1520550e65cbdae7baa87e920cf5d59d8ab86cd33a12943305f676e`；旧备份保留。
- 全量后端 `473 passed, 1 warning`；Ruff 与 compileall 通过。完整 E4 仍为 `实施中`，不以局部真实测试代替最终停写、切换与验收。

## 2026-09-07 E4-06 日常写权威续跑

- 用户明确授权丢弃缺失 PDF 测试原件；将该 source 记录为 user-approved excluded，不再要求找回原始字节。本次只排除迁移输入，不删除其它旧文件、快照或 Chroma generation。
- 实施 E4-06：统一 E4 专用 Session 的 canonical owner/parent、不可变身份、业务审计和 SQL jobs；对批量 DML 使用 tracked ORM 行，业务/审计/job 一起提交或回滚。
- 将内存标签任务改为 durable job；业务 handler 的 SQL 副作用与 fencing 成功转换同事务，避免 handler 已写入而 runner 结果被拒绝。
- E4 运行器接入真实应用生命周期，支持按已启用 job 类型消费。未启用 E5 的知识/向量重建保留 queued，不伪装成功、不消耗重试进入死信。
- 封闭 Django 历史认证/文件和 FastAPI 文件直写维护入口，提供 SQL job 查询；知识原文写 SQL 后只返回已接收，不把投影完成当作 SQL 成功条件。
- 回滚点：本轮代码/配置可单独回退；不 populated downgrade、不清除旧输入；SQL live 验证前重新 preflight/备份，保留所有成功和失败 evidence。完整应用切换仍需验证后执行。

### 本轮完成证据

- `artifacts/e4-write-authority-20260907.json` 汇总本轮范围与限制；`artifacts/e4-business-write-smoke-20260907T042611.json` 为真实 API/SQL。手动/自动标签共 2 次成功、无重复复习记忆；9 个测试 job 中 2 succeeded / 7 cancelled（测试清理），保留全部审计。
- 修复两个 live 暴露问题：同次 flush 中 job audit 的 FK 排序；MySQL 秒精度导致复习时间摘要变化。保留失败 target dump 和首次失败 journal，修复后原迁入 312 条仍逐列一致。
- `artifacts/e4-restore-20260907T042748.json`：39 表/2,407 行 DDL/摘要全等；SHA-256 `841b40167d79ee9c6ef940bd26af8db7fdc3b27474846dcdb23eff8b99a03e95`。测试创建的业务行通过 UoW 删除，source/旧映射不改；审计/session/job 证据保留。

## 0. 执行边界

### 2026-09-07 E4-06 续执行合同

- 用户明确允许丢弃缺失的测试 PDF；将该唯一原件缺失记录标为 `excluded`，不再阻断迁移。不删除其余原件、快照或整个 Chroma 库；派生残留随后续 E5/E7 清理，不伪造原始字节。
- 本轮补齐 E4 runtime 的 SQL 事务写权威：新增/修改/删除业务对象统一 canonical 字段和脱敏 audit，需投影的变更在同一事务产生 durable SQL job；批量 DML 不得绕过。
- 请求内 Chroma/文件/内存后台任务改为 SQL 接受与持久调度；未接管的旧写入口 fail-closed，不以返回成功掩盖未执行。Django 旧 HTTP 写入口封闭；不静默停止其他进程或切换应用 DSN。
- 验证：rollback 时业务/audit/job 全部消失；commit 后重启可消费；canonical owner/parent、防越权、批量更新/删除、重复/乱序、runner fencing 与旧入口拒绝。先本地回归，再对允许的 E4 target 做真实 SQL smoke/恢复。
- 回滚点：新 runtime 接线、业务 authority/handler、旧入口 gate 和对应测试；保留迁移输入/执行证据，绝不对 populated schema downgrade。

本批对应 `E4 = S3 = AR-3`。E2/AR-1 与 E3/AR-2 已关闭，用户已确认本计划并授权进入实施。当前已完成受控 preflight、真实源只读 inventory、隔离目标导入及独立恢复；本机应用已切换 E4 target DSN。每次续跑必须重新通过 allowlist、身份核验和批次 gate。不得从默认端口、`.env` 或未知进程推断目标，不得在 allowlist 之外连接或写入业务资源。

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

- 不操作 allowlist 之外的资源，不执行未经授权的删除或 E5/E6/E7/E8 工作；真实 E4 导入、dump 和停写切换按既有授权与 gate 执行。
- 不修改现有 populated 表的主键、`user_id` 类型、FK、删除策略、时间字段或内容存储，直到逐表 dry-run、备份、对账和用户授权完成。
- 不在本批激活或清理 Chroma generation；RAG port、generation 重建和旧 generation 处置属于 E5/AR-4。
- 不完成 Skill package 规范化发布、C 级执行或旧 Skill runtime 清理；E4 只盘点并迁移必要业务关联，规范化属于 E6/AR-5。
- 不删除 Django、Redis、MD5 sidecar、旧文件目录、旧 Chroma 或 Skill Storage；删除属于 E7/E8 且需要单独清单和确认。
- 不以 E3 的两个测试用户、E2 合成快照、SQLite/mock 或现有局部 service commit 证明 E4 已完成。

## 3. 入口条件与依赖

- E2/AR-1 已关闭：统一 schema、UoW、SQL job/runner、备份/restore 证据可审阅；E2 只使用合成/隔离数据，未迁移现有业务数据。
- E3/AR-2 已关闭：`users`、`auth_sessions`、角色、审计和 `migration_maps` 的认证上下文可用；旧 session/refresh token 不在 E3 迁移范围。
- target/restore 均已执行精确 Alembic head `20260905_0008_e4_business_shadow`，各 39 表；正式 allowlist 为 `backend/ops/e4/e4_allowlist.json`，专用 source 只读账号和独立 target/restore app/root 凭据已建立。
- source 由用户授权从工程与数据库定位，并经 server UUID 和 21 表快照 digest 核验；不复用 E1/E2/E3 容器、volume、network 或凭证。source 用户和业务行未修改；新增只读账号属于已执行的权限管理。
- PDF 已按用户授权排除；2026-09-08 已完成本机最终停写、21 表冻结复验、完整应用及旧进程部署核验。私有凭据和备份见 runbook，启动时重新签发 preflight，不复用过期许可。

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
- [x] `E4-PREP-10`：收紧既有 target 无 source metadata 的冲突分类和显式 canonical target UUID 校验；完成定向回归，真实资源保持 `not-run`。
- [x] `E4-PREP-11`：修正身份 dry-run 的 artifact digest、标准 UUID 保留、Django ShortUUID 边界和既有 target UUID 复用校验；补齐迁移用途的专用账号、精确 DSN、migration switch 与容器拓扑 preflight gate。
- [x] `E4-PREP-12`：完成 E4 定向与后端全量回归、Ruff、`compileall`、差异和文档门禁；真实资源仍保持 `not-run`。
- [x] `E4-PREP-13`：按本轮审阅收紧确定性显式 UUID、资源角色用途矩阵、精确数据库账号、独立容器 inspector、server UUID 和 target/restore 凭证边界；补齐负向回归并重跑定向门禁。
- [x] `E4-PREP-14`：完成加固后的后端全量回归和全部本地静态门禁；记录 Compose 未注入凭证时的预期拒绝及占位值重跑通过；真实资源仍保持 `not-run`。
- [x] `E4-PREP-15`：复核其他执行者留下的工作树，修正容器型 preflight 的检查顺序，使缺失或漂移的容器事实在数据库 inspector 调用前 fail-closed；完成最终 `400` 项后端回归和静态门禁，保留瞬时 runner 失败现场；真实资源仍保持 `not-run`。
- [x] `E4-PREP-16`：发现并只读核验其他执行者已启动的 E4 target/restore Docker 拓扑，记录 container/image/network/loopback port/volume/health/server UUID；未读取凭证、未连接 MySQL、未签发 preflight，E4-01 至 E4-08 状态不变。
- [x] `E4-PREP-17`：将 migration approval token、preflight TTL 和已记录 preflight 的静态有效性检查前移到所有 injected inspector 之前；补齐零调用回归并再次通过完整后端/静态门禁，未连接已存在的 E4 MySQL。
- [x] `E4-PREP-18`：移除 preflight 消费接口的静态 `container_facts` 旁路，强制容器型 guard 在静态记录校验后使用显式 live inspector；补齐篡改、缺 inspector、静态注入和 health 漂移回归，复核 E4 拓扑未漂移并保留根范围 Ruff 既有失败现场。
- [x] `E4-01`：21 表快照和最终冻结复验完成；专用只读账号、持久只读、旧账号锁定/撤权及源备份已验证；缺失 PDF 按授权 excluded。
- [x] `E4-02`：314 mappings、312 业务及 2 canonical 用户复验通过；最终冻结源 21 表无漂移，48 FK 无孤儿。
- [x] `E4-03`：隔离 live target/restore 均为 head `20260905_0008_e4_business_shadow`、39 表；已校验 48 个 FK 无孤儿，恢复 DDL/行摘要一致；未原地改变 source populated 主键。
- [x] `E4-04`：正式 allowlist、独立凭据、角色 preflight、空库与 populated dump/restore 已真实执行；312 条导入、0 quarantine，重放 0 imported / 312 skipped。证据只涵盖已捕获快照，不涵盖缺失 PDF。
- [x] `E4-05`：源已最终冻结、摘要无增量漂移；本机 FastAPI 实际 DSN 与前端代理流量已切 target，并保留独立恢复点。仅本机范围，不代表外网生产切换。
- [x] `E4-06`：本机当前代码已部署切流；前端笔记新写入 canonical owner/digest、audit/job 同事务，旧 Django 26 路由及 ORM/raw SQL 拒绝，E4 runner 实际运行。管理员可解除源保护的边界明确保留。
- [ ] `E4-07`：已有真实认证/owner、runner kill/restart/lease/fencing、确定性 handler、accepted SSE；新增完整 main 生命周期、两次优雅关闭、Redis 正常/故障/恢复/故障冷启动及前端实际写入均通过。真实外部 LLM 成功/故障矩阵与浏览器人工验收未覆盖，不整体标完成。
- [ ] `E4-08`：E4 整体仍为 `实施中`；完整证据完成后提交 `待验证`，用户第二次验收确认后才可 `已关闭`。

## 6. 原始静态发现与实现差异（当前进度见任务清单）

- `chat_sessions` 使用 `String(64)` 的 `user_id` 且没有到 `users` 的 FK；`chat_messages.id` 仍是整数，不能直接当作 canonical UUID。
- `knowledge_source_documents` 使用 `String(64)` 的 `user_id`，保存 `content_blob`，只有 `(user_id, md5)` 本地唯一约束，没有用户 FK。
- `notes`、`memory_items`、`note_templates` 的用户 ID 为 `String(36)`，`user_model_configs`/`user_embedding_configs` 为 `String(64)`，均未形成 canonical `users.id` 的物理 FK。
- `SkillRunBinding.user_id/session_id` 为 `String(64)`；Skill 领域写入和旧 Storage/目录输入仍需逐项映射。
- `note_service.py`、`knowledge_document_service.py` 等服务已统一通过事务 helper flush；`database_session_manager.py` 的独立会话写入也已收敛到 `persist_service_write`，该 helper 对 managed/UoW session 延迟 owning commit，对当前独立调用保留兼容提交。笔记/知识写入与 Chroma、图片/MD5、自动标签/记忆等副作用仍按 after-commit job 边界处理。
- 本地只读观察到一个用户旧 ShortUUID `j6BVY9AHmHPQEbwoZabRMq` 出现在 MD5/Chroma metadata；这不是已批准的身份映射，也不能直接写入目标。
- Chroma 用户作用域 collection 名称后缀 `e5efbb90a85fadbf` 与 metadata/sidecar 的旧用户 ID 不一致，且 RAG metadata 含本机临时绝对路径；在 source manifest 证明前按 `scope_conflict` 和敏感路径脱敏问题处理。
- Legacy 32 位 MD5 只保留为历史内容标识，不能代替 `migration_maps.source_digest` 的 64 位小写 SHA-256；正式 inventory 必须同时记录两种 digest。
- `backend/data/reranker_config.json` 与 `backend/data/routing_calibration/` 目前只有本地配置/派生候选身份，未证明为 SQL 业务权威；不得由请求路径或迁移器隐式加载。
- 曾发现 `note_template_router.py` 的具体 `PUT /note-template/reorder` 路由注册在通用 `PUT /note-template/{template_id}` 之后；现已在 `E4-ROUTE-01` 修复并通过纯路由回归，后续 live 写权威验证仍须覆盖该入口。
- E3 `migration_maps` 保留 `mapped/conflict/error`；E4 已用专门旁表承载 candidate/validated/imported/reconciled/orphan/excluded 等流程状态，并已部署 live。当前业务批为 imported，对账证据不自动把批次或 E4 整体标为最终 reconciled/关闭。

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

- **已解除**：数据库迁移基础 gate、测试用户、Skill 输入 adapter/密钥版本；本轮进一步完成日常 canonical 身份、audit/job 同事务、tracked CRUD、任务查询和旧入口代码封闭。新证据：`artifacts/e4-write-authority-20260907.json`。
- **PDF 已处置**：用户明确允许丢弃该测试文档，SQL 审计 action `migration.source_excluded` 已落地；证据 `artifacts/e4-pdf-exclusion-20260907.json`。不再阻塞迁移；其它原件、源快照和 Chroma 残留未删除。
- **E4-06 部署验证**：已实现 E4 BusinessSession、owner/parent 不可变校验、审计/持久 job、聊天成对原子写入和旧 Django HTTP/ORM 拒绝；真实 E4 MySQL/API 的新增/删除/回滚/标签 handler/SQL polling/accepted SSE 通过。旧运行进程未重启、永久 DSN 未改，不能宣称现场已无双写。
- **E4-05 停写/切换**：尚未停止旧源写入、冻结最终源或切换应用流量；下一步是运行拓扑/依赖核验、实际停写窗口、最终漂移检查和受控切换，不再重复索要已可查参数。
- **E4-07 完整验证**：当前真实 handler 使用确定性 tagger，未实际调用 LLM；完整 app lifespan、真实 Redis outage、全部业务故障矩阵仍待执行。知识/笔记/embedding 投影 job 保留 queued，只有 E5 generation worker 才可消费，不能计为向量完成。
- **表示语义**：旧源 DATETIME 字面值保留，不推断历史 SYSTEM 时区。日常新写入按 MySQL 实际精度规范化，有时区值转 UTC 后存无时区字面；JSON 比较口径不变。
- **验收**：全量 `488 passed, 1 warning`、Ruff/compileall 通过；本轮恢复为 39 表/2,407 行全等。最终用户验收未发生，E4 仍为 `实施中`。

## 11. 用户确认记录（2026-09-02）

本轮用户确认摘要：Q1 完整授权；Q2/Q9 采用在线只读并直接建立最终数据库 canonical shadow；Q4 纳入聊天/会话、笔记/模板、记忆、知识源/原始字节、图片/媒体、MD5、模型/Embedding 配置及必要 Skill 关联，Skill 完整发布交 E6；Q5 固定 UUID/UUIDv5 并复用 E3 `users.id`；Q6/Q11 关键身份、FK、内容、权限、唯一约束、审计和跨域引用 fail-closed，非关键问题可 quarantine；Q7 FastAPI 唯一业务写入口，Django/旧脚本/文件只读；Q10 分批执行并记录文档和过程；Q12/Q27 原始文档和媒体进入 SQL，字节级一致；Q13/Q37 用户/Embedding 入 SQL、reranker 保持版本化配置、key-version 未确认不迁移密文；Q14/Q32/Q36 冻结完整 Skill 输入接口，E6 不重构输入接口；Q18/Q29 修复 reorder 路由；Q19/Q28 additive 扩展 `migration_maps`；Q20 Chroma 作用域冲突交 E5；Q23-Q25 快照、checkpoint、稳定排序和幂等批次；Q26 密文问题仅 quarantine 配置域；Q30 每项先更新计划并关联证据/回滚点；Q31/Q33/Q40 仅两次确认；Q34/Q43 所有 E 阶段结束验收后统一清理中间材料；Q35 不增加 3306 特殊保护但执行通用身份核验；Q38/Q42 不设固定停写时长，记录实际开始/结束并以 gate 失败阻断；Q39 批次大小由 inventory 决定；Q41 当前执行者接手。

执行确认语义：`批准 E4 计划并按已确认范围实施（含导入、停写和 FastAPI 切换；不删除旧输入）`。验收确认尚未发生。

## 12. 当前清理策略

阶段内保留成功、失败、无效和历史测试体及恢复现场，不提前清理。所有 E 编号完成并通过最终验收后，按 E0-E3 记录执行统一清理：移除原始敏感 source、临时 fixture、可重建中间体和完整环境快照；保留脱敏 manifest/inventory、审计、摘要、错误报告、备份、restore-forward 和回滚证据。该策略不授权删除旧输入、未对账源、健康快照或 E1-E3 保护资源。
