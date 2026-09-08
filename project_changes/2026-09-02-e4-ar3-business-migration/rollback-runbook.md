# E4 备份、切换与 Restore-forward Runbook（本机切换已执行）

## 2026-09-08 已执行的本机部署与回滚边界

主证据为 `artifacts/e4-full-lifecycle-cutover-20260908.json`；下方 2026-09-07 参数表是历史 checkpoint，不代表当前未停写。源自 `2026-09-08T00:50:34Z` 起持续冻结。最终 restore 39 表/2,539 行，备份 SHA-256 `bbcf14de7d4024aadc523d5e923fd73de917ad25c5396cf77c31b6c0d66a1b75`；所有旧备份保留。

当前本机入口：前端 `127.0.0.1:18080` -> FastAPI `127.0.0.1:18000` -> target `127.0.0.1:33427/doki_e4`；Django `127.0.0.1:18001` 是 410 retired 入口，只持有 `doki_e4_source_ro`。源 `3306` 不接受业务写入，restore `33428` 不是在线写目标。E4 专用 Redis 为 `doki-e4-20260908-redis` / `18020`。

可重复启动使用本机私有启动器；它读取受限凭据，校验当前容器/UUID并签发新的 runtime/switch preflight。E4 变量必须由进程注入；仅改 `.env` 不足以启动，不能直接使用旧 `scripts/start-all.ps1` 期待自动获得 E4 授权。该脚本不属于持久服务管理器，不承诺开机自启。

```powershell
# 从仓库根运行。启动不复用过期 preflight；端口已占用会拒绝。
backend/.venv/Scripts/python.exe .runtime/e4/app_runtime.py
# 优雅关闭（使用私有 stop marker，而不是强杀）
backend/.venv/Scripts/python.exe .runtime/e4/app_runtime.py stop
# 等待端口关闭和 active-app.json 所指进程记录 shutdown_complete，再做备份/恢复。
backend/.venv/Scripts/python.exe .runtime/e4/live_execute.py source-recheck
backend/.venv/Scripts/python.exe .runtime/e4/live_execute.py verify
backend/.venv/Scripts/python.exe .runtime/e4/live_execute.py restore
```

Django 的生产 CORS 白名单已补入本地 `.env`，可在其目录使用 `.venv/Scripts/python.exe manage.py runserver 127.0.0.1:18001 --noreload`。前端在 `front` 目录使用 `C:/nvm4w/nodejs/npm.cmd run dev -- --host 127.0.0.1 --port 18080`，先将 `C:/nvm4w/nodejs` 加入 PATH；Vite 默认 proxy 为 18000，含 `/jobs`，不再指 Django。

回滚顺序：先停止/摘除前端业务流量，再优雅停 FastAPI 并确认 runner 锁释放；对 target 备份后仅在 allowlisted restore 验证 restore-forward。**不能把 DSN 直接切回冻结旧源**：target 已有新 auth/job/audit 事实，旧源并不包含这些增量。重新开放源写入、解除 `st@%` 锁定、管理员关闭 `super_read_only` 或生产流量切换必须另行审阅精确方案。不要 populated downgrade、bootstrap 或删除迁移/审计证据。

生产共享卷、DNS/LB/TLS 和开机自启未交付；最终 FastAPI 为本地 development、DEBUG false、rate limit true、shared storage false。不得用 `SKILL_STORAGE_SHARED=true` 冒充已经挂载共享卷。认证签名密钥、target app 密码和 approval 已轮换；旧登录 access token 必须重新登录，第三方 API key 需要用户在供应商端轮换。

日期：2026-09-02  
状态：实施中  
适用范围：E4/AR-3 业务数据迁移和唯一写权威切换  
执行状态：已授权进入正式代码实施/分批执行；真实命令仍受 allowlist、preflight、backup 和 gate 约束

## 0. 绝对前提

本 runbook 不能扩大用户已授予的范围。用户已确认 E4 计划并授权分批实施；只有在 source/target/restore allowlist、备份位置、owner/approver 和迁移开关完成 preflight 后，才可填入真实值并执行。所有命令必须拒绝默认 DSN、未登记 server UUID、E1/E2/E3 资源、在线 Django 写库、Redis/Chroma 写路径和未脱敏 source。

## 1. 当前批次参数（2026-09-07）

| 参数 | 现值 | 责任 |
|---|---|---|
| `migration_batch_id` | `e4-business-live-20260907`；用户批 `e4-test-users-20260907` | Codex |
| source snapshot/manifest | 私有 `.runtime/e4/source-11e6c61c7518f3af.json` 及同 stem `.manifest.json`；内容 SHA-256 `11e6c61c7518f3af945377d774df57b44c46f995f7ccecf44ac1bc38f0b2847a` | Codex |
| source 身份 | `localhost:3306`，`chat_history`/`user_service`；UUID `13e60c20-6874-11f1-8e4a-bcfce7d65b5f`；`doki_e4_source_ro@localhost` | Codex |
| target 地址/身份 | `127.0.0.1:33427/doki_e4`，`doki_e4_app`；UUID `0c0d3e33-a743-11f1-af41-ea47e0ceb469` | Codex |
| restore 地址/身份 | `127.0.0.1:33428/doki_e4`，`doki_e4_restore`；UUID `0bf5339b-a743-11f1-9ab9-febdaaf248fb` | Codex |
| source/target/restore allowlist | `backend/ops/e4/e4_allowlist.json`；绑定新 container ID、镜像、网络、精确 DSN 和私有凭据引用 | 用户既有授权 / Codex 核验 |
| credential reference | `private://e4-20260907/source-ro`、`private://e4-20260907/target`、`private://e4-20260907/restore`；值仅在 `.runtime/e4/live-credentials.json` | Codex |
| schema revision | target/restore 已执行 `20260905_0008_e4_business_shadow`，39 表 | Codex |
| backup location/retention | 私有 `.runtime/e4/backup-target-841b40167d79ee9c.sql`；SHA-256 `841b40167d79ee9c6ef940bd26af8db7fdc3b27474846dcdb23eff8b99a03e95`；旧备份全部保留 | Codex |
| stop-write window (UTC) | 未开始；应用未切换，源未封闭写入；后续记录实际起止 | Codex |
| rollback decision authority | 用户；Codex 执行已批准范围内恢复并留证 | 用户 |

当前 checkpoint：`artifacts/e4-write-authority-20260907.json`（日常写权威）；初次执行记录 `artifacts/e4-live-execution-20260907.json` 保留为历史。两个 E4 容器健康，凭据已分离，source 只读账号仅 SELECT/SHOW VIEW。E4 容器重建保留既有 volumes/server UUID，E1-E3 未修改；以前的退出/空库/账号不符记录保留为历史，不代表当前状态。

已完成：真实角色 preflight、Alembic、2 用户重建、312 条业务导入、314 mappings、幂等重放和独立恢复。最新恢复证据 `artifacts/e4-restore-20260907T042748.json` 为 39 表/2,407 行 DDL 和行摘要全等，完成于 `2026-09-07T04:27:48Z`（台北 12:27）。日常 API/runner 的临时业务行已经受审计事务清理，新增 auth/job/audit 证据保留；312 条导入实体不变。备份 2,195,497 bytes；源 21 表摘要复查未变，源业务行未修改。

### 本机续跑命令与保护

以下从仓库根目录、Windows venv 执行；本机私有脚本会从受限文件读凭据、重新签发短期 preflight 并核验容器/server UUID。不得粘贴私有文件或将 DSN/密码输出到日志。

```powershell
backend/.venv/Scripts/python.exe .runtime/e4/live_execute.py verify
backend/.venv/Scripts/python.exe .runtime/e4/live_execute.py source-recheck
backend/.venv/Scripts/python.exe .runtime/e4/live_execute.py restore
```

`restore` **会替换 allowlist 中独立 restore 的表/数据**：先分别备份当前 restore 和 target，再使用 binary-safe MySQL dump 恢复，并逐表比较 DDL/行摘要。不得将它改指向 source 或 E1-E3。它不是“已切换应用的回滚”；完整应用恢复仍需后续 runtime/写权威 gate。不要重跑 `bootstrap`，不要在 populated target 执行 downgrade、初始化或旧 root 密码回切。

私有测试登录信息在 `.runtime/e4/test-users-login.json`；只适用于已导入的 E4 目标，当前应用尚未切换。恢复版本改变后须重查 target/restore 身份、revision、凭据引用和 API/runner，不复用过期 preflight。

## 2. 阶段 A：Preflight（只读）

目标：证明所有资源、版本和路径都在批准范围，且不会误连现有业务资源。

1. 将 source/target/restore 的完整 host、port、database、专用数据库账号、server UUID、容器 ID、image ID、网络和凭证引用写入 allowlist；target/restore 不复用凭证，禁止从 `.env` 或默认值补全。
2. 执行项目现有的 preflight/guard，仅对批准的隔离资源做 `SELECT 1`、server identity、schema revision 和权限检查；不得执行业务查询或写入。
3. 记录 FastAPI、Django、runner、Redis、Chroma、Skill Storage 进程/版本和当前 active revision/generation；只读检查失败立即标 `阻塞`。
4. 对本地文件、MD5、图片和 Skill Storage 生成只读 manifest；路径必须通过 containment，符号链接/junction 拒绝。

**通过标准**：所有资源精确命中 allowlist；无隐式连接；manifest 可重放；E1/E2/E3 资源未启动、未复用、未修改。

## 3. 阶段 B：Snapshot 与 Dry-run

1. 在批准停写前先取得 source snapshot/dump；记录开始/结束 UTC、事务隔离、server UUID、schema revision、文件/Chroma manifest 和 SHA-256。
2. 对 snapshot 运行 identity-map dry-run：规范化 UUID、owner scope、唯一约束、FK、源行 digest，并输出新增/no-op/conflict/orphan 计数。
3. 使用同一 snapshot digest 生成目标导入计划；digest 漂移、未知用户、重复身份、跨用户 MD5 冲突或不可解释 orphan 均停止。
4. 将 dry-run 结果和摘要写入 `test-record.md`；不得把完整密码 hash、token、原始 IP、原始 BLOB 或未脱敏 PII 放入仓库。

**通过标准**：source/target 预期行数、digest、唯一约束和审计字段均可解释；`conflict=0`、`orphan=0` 或有用户批准的明确处置；重复 dry-run 结果稳定。

## 4. 阶段 C：隔离演练

1. 在独立 E4 target/restore fixture 中运行 additive/shadow schema 和迁移器；当前已完成 SQLite repository 回归及 E4 MySQL 真实导入/恢复和局部 runner 故障验证，禁止使用 E1/E2/E3 容器、volume、network 或业务快照。
2. 重放同一批次两次，确认第二次为 no-op；修改一条 source payload，确认 digest conflict 拒绝且旧映射不变。
3. 注入 FK/唯一冲突、重复/乱序、租约过期、旧 fencing token、runner kill/restart、超时、取消和孤儿 job；验证 fail-closed、retry/DLQ 和审计 correlation。
4. 将 fixture 结果与真实等价限制分开记录；fixture 不能替代批准的 MySQL/文件/Chroma live 证据。

## 5. 阶段 D：停写与切换（受批次 gate 约束，不新增用户确认）

1. 冻结并记录 active schema revision、migration batch、source digest、job/attempt/audit 快照和当前流量窗口。
2. 让 Django、旧脚本和文件业务入口进入只读；保留的 import/export/debug 必须显式调用并写 audit。确认没有长期双写进程。
3. 在同一 SQL UoW 中写入 canonical 业务行、`migration_maps`、FK/审计和 durable job；API 成功响应只依据 SQL commit。
4. 事务提交后由 runner 处理 Chroma/文件等派生 job；SSE/polling 从 SQL job 状态读取，Redis 只做唤醒提示。
5. 切换期间持续检查 source snapshot digest 和未登记写入；任一漂移立即停止并转阶段 F。

## 6. 阶段 E：切换后验证

- 逐表比较 source/target/restore 的行数、规范化 content digest、唯一约束、FK、时间和审计 correlation。
- 抽样验证每类 user/session/message/note/memory/knowledge/image/Skill 对象及其 owner scope；确认不存在无法解释 orphan。
- 重复请求和重复导入为幂等；乱序事件、旧 fencing token、过期 lease、kill/restart、超时、取消和异常按合同处理。
- 停止 runner 时 API readiness 仍反映 SQL 可用性，不把 Redis pending、内存队列或 Chroma 状态当业务成功。
- 保存命令、原始日志、manifest、diff、快照位置和审阅人；实现者只能提交 `待验证`。

## 7. 阶段 F：Restore-forward（失败路径）

触发条件：任何误连、source digest 漂移、唯一/FK mismatch、审计缺字段、双写、旧 token 成功提交、健康快照覆盖或回滚不可执行。

1. 立即停止 E4 runner、FastAPI 业务写入和所有迁移脚本；保留进程日志、job/attempt、audit、migration map 和错误目标，不删除 source。
2. 验证迁移前快照的 manifest、SHA-256、server UUID、schema revision、文件/Chroma manifest；不覆盖原快照。
3. 将快照恢复到独立 restore-forward 数据库/目录（目标必须在 allowlist），恢复过程使用 binary-safe 管道并保留原始日志。
4. 对恢复目标执行 schema/表/行数/content digest/唯一约束/FK/audit/correlation/migration map 对账；任何差异保持 `阻塞`。
5. 保留故障目标只读供审阅，记录 restore-forward diff 和决定；用户决定修复重试或退回，不执行 populated downgrade 或无目标删除。
6. 恢复后重新运行 API/runner smoke，确认旧 fencing token 和过期 lease 无法提交结果，再决定是否重开批次。

## 8. 关闭与后续边界

只有以下均完成且用户确认，E4 才能关闭：

- source/target/restore 对账和恢复证据完整；
- FastAPI 单一写权威抽样通过，旧写入口只读/显式运维；
- 重复/乱序、lease/fencing、kill/restart、timeout/cancel/error/orphan 覆盖通过；
- 未授权删除为零，旧输入和健康快照仍可恢复；
- 审阅人核对三件套与证据，用户明确确认关闭。

E4 关闭不自动授权 E5 RAG generation、E6 Skill 发布、E7 文件/sidecar 清理或 E8 删除/部署；这些阶段仍须单独计划和确认。

## 当前阻塞

- 隔离数据迁移/恢复 gate 已通过；缺失的测试 PDF 已按用户明确授权排除，并记录 SQL 审计 `migration.source_excluded`，见 `artifacts/e4-pdf-exclusion-20260907.json`。它不再阻塞迁移；其历史 sidecar/chunks 未删除。最终 source 冻结仍未执行。
- E4 新业务 canonical owner/parent/digest、audit/job 同事务、SQL job 查询和旧入口代码防护已经实现；真实业务 API、accepted SSE 和有 fencing 的笔记 enrich handler 验证通过。E5 投影 handler 未注册，相关 job 保持 queued，不冒充成功。
- 旧 Django 运行进程未重启，旧客户端数据库级写权限未统一撤销，永久 DSN/流量未切换。完整 main 生命周期、Redis 故障和全部业务故障矩阵仍待验证；代码防护不等于现有运行进程已停写。
- 日期/JSON 表示口径见测试记录；不得把字面时间保留表述为 UTC 来源已证明。

## 明确未做

- 未停止 source 写入、未修改应用 `.env`/永久 DSN、未切换流量、未删除旧输入；source 权限管理已做，业务数据未改。
- 未将隔离真实业务 API、SQL runner 和确定性 tagger 验证扩大成全应用切换或 E4 关闭证据；未验证外部 LLM，也未激活 E5 投影或执行 E6 发布。
- 用户最终验收未发生；后续 gate 沿用既有执行授权，不因可本地查到的参数重复索取确认。

## 清理与保留

阶段内保留所有中间测试体、失败现场和可重建材料。所有 E 编号结束并经最终验收后，统一清除原始敏感材料、临时 fixture 和可重建中间体；保留脱敏 manifest、审计、摘要、错误报告、备份和 restore-forward 证据。此规则不授权删除旧输入或未对账源。
