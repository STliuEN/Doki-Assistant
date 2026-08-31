# E3/AR-2/S2 测试与迁移证据

状态：待你确认  
负责人：Codex  
执行口令：`开始执行e3`

本文件只记录 E3 证据。未收到执行口令前，所有实现、迁移、真实依赖和浏览器验证均不得运行。证据状态只使用 `verified-local`、`verified-live`、`blocked`、`not-run`；`fixture`、`mock`、`historical` 是证据类型，不是状态。

## 环境限制

- 平台：Windows / PowerShell；当前分支：`ai_document_assistant`。
- E2/AR-1 已关闭；E2 source/restore 容器、volume、network 和证据保留且禁止复用。
- 本批只允许在执行确认后使用新的 E3 隔离 MySQL 8.4 source/target/restore 拓扑。
- source 用户数据只能来自用户批准的只读 dump 或脱敏离线副本；不得读取 `.env` 推断目标，不得连接在线 Django 写库。
- 当前本文件只属于计划准备；未运行外部依赖、数据库、Docker、前端服务器或认证切换。

## 证据表

| ID | 环境/版本 | 拓扑 | 证据类型 | 命令/动作 | 阈值 | 实际结果 | 结果/处置 | 日志/文件 | owner | approver | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `E3-PREP-01` | source tree / UTF-8 Markdown | 仓库文件 | verified-local | 读取 E3 计划、交接手册、蓝图、E2 关闭记录和阶段模板 | E3 必须位于 E2 之后；状态为待确认；不授权跳阶段 | 已核对 E3=`AR-2/S2`、E2 已关闭；本批状态保持 `待你确认` | passed；仅证明文档入口和阶段边界，不证明实现 | `plan.md`、`docs/architecture_rewrite_plan.md`、`docs/architecture-execution-handoff-2026-08-26.md`、E2 records | Codex | 用户 | verified-local |
| `E3-PREP-02` | Python/TypeScript source tree | source tree only | verified-local | 静态检索 FastAPI auth helper、Django user routes、Vite `/user` proxy、identity models、Redis/YAML admin path | 明确现状与目标差距，不将局部 primitive 当作接管完成 | 已确认 FastAPI 当前依赖 Django JWT/Redis；Vite `/user` 指向 Django；E2 auth tables 仅为结构 | passed；未修改或调用这些路径 | `backend/app/utils/auth_utils.py`、`backend/app/router/user.py`、`front/vite.config.ts`、`DjangoUserService/apps/user/` | Codex | 用户 | verified-local |
| `E3-PREP-03` | 用户质询记录 | 设计树 | verified-local | 固化 Q1-Q45 及 Q41-B 决策 | 所有关键范围、迁移、token、cookie、role、审计、回滚和验收分支已回答 | 已形成完整共享理解：本地开发、完整接管、两次大确认、唯一执行口令 `开始执行e3` | passed；本记录不替代用户执行授权 | `plan.md` §2、§12 | Codex | 用户 | verified-local |
| `E3-PREP-04` | source tree | 无外部拓扑 | not-run | E3 plan/change-log/test-record 三件套和索引链接检查 | 文件存在、Markdown fence/link 无错误、状态一致 | 待文档写入后执行只读检查 | 不连接外部依赖；若失败只修正文档 | 本目录三份记录、`project_changes/README.md` | Codex | 用户 | not-run |
| `E3-00-preflight` | 执行后环境 | 新 E3 allowlist | not-run | 口令校验、资源/DSN/server UUID/image/network/port preflight | 只允许 E3 资源；E1/E2/当前业务资源 deny；preflight 未过不得建连 | 等待 `开始执行e3` | 未授权前不得运行 | `plan.md` §3、执行日志 | Codex | 用户 | not-run |
| `E3-01-schema` | MySQL 8.4 | E3 target/restore | not-run | user_profiles、session metadata、authorization grant、Alembic head/migration | model/migration parity；精确 head；无自动 DDL；restore 零差异 | 等待执行 | 未执行 | E3 artifacts/schema map | Codex | 用户 | not-run |
| `E3-02-migration` | MySQL 8.4 / source dump | E3 source -> target -> restore | not-run | 全量用户 dry-run、UUID mapping、profile/hash import、冲突拒绝、manifest/restore-forward | 关键冲突零容忍；行数/digest/约束/mapping 零差异；证据不含完整 hash/未脱敏 PII | 等待执行 | 未执行 | E3 artifacts/migration report | Codex | 用户 | not-run |
| `E3-03-auth-lifecycle` | Python 3.12 / MySQL 8.4 | FastAPI + SQL | not-run | register/login/refresh/logout/password/profile/session lifecycle | access/opaque refresh、cookie、rotation/replay、token version、disabled/locked 全部 fail-closed | 等待执行 | 未执行 | API logs/audit correlation | Codex | 用户 | not-run |
| `E3-04-role-grant-audit` | Python 3.12 / MySQL 8.4 | role/grant/audit | not-run | bootstrap、role separation、four-eyes approve/revoke、审计必填字段、correlation query | 同身份冲突和越权全部拒绝；无 secret/PII；append-only | 等待执行 | 未执行 | audit export/negative matrix | Codex | 用户 | not-run |
| `E3-05-frontend` | Node/Vite/Chromium | Vite -> FastAPI | not-run | proxy、withCredentials、cookie、refresh single-flight、七个 `/user/*` 浏览器流程 | 无 Django 前端直连；cookie 正确；401 refresh 后原请求只重试一次 | 等待执行 | 未执行 | browser screenshots/console log | Codex | 用户 | not-run |
| `E3-06-shadow-cutover` | MySQL 8.4 / Django read-only adapter | E3 target + old read-only | not-run | 全量 shadow、切换、failure injection、snapshot restore-forward、无双写回退 | 关键 mismatch 为零；回滚可执行；无 Django 新写入 | 等待执行 | 未执行 | shadow report/cutover log/rollback log | Codex | 用户 | not-run |
| `E3-07-final-gate` | source tree + E3 isolated dependencies | API/UI/SQL | not-run | scoped/full pytest、Ruff、OpenAPI、lock、docs、API/UI/E2E 和证据审阅 | 全部退出码为 0；关键真实证据齐全；实现者只能提交 `待验证` | 等待执行 | 未执行 | final evidence bundle | Codex | 用户 | not-run |

## 数据对账占位

- source/target/restore 用户行数：`待执行`。
- `users`、`user_profiles`、`migration_maps` canonical digest：`待执行`。
- auth session/refresh/revocation 状态和 family/replay 结果：`待执行`。
- roles/role_bindings/authorization_grants 的 revision、审批 actor 和 grant diff：`待执行`。
- audit event 数量、必填字段、correlation 链路和 secret/PII 扫描：`待执行`。
- Vite/API/browser cookie、refresh retry、Django write-path deny：`待执行`。

## 不能证明的内容

- 计划材料、静态检索、SQLite、mock 或 fixture 不能证明 MySQL 8.4 的锁、事务、恢复、真实用户迁移或唯一写权威。
- E2 已关闭证据不能替代 E3 用户/hash/session/role/audit 证据。
- 旧 Django 单测、Redis blacklist 单测或现有 `SyntheticAuthRepository` 不能证明 FastAPI 已接管认证。
- 开发环境 `SameSite=Strict` 且无 CSRF/Origin 中间件的结果不能被描述为生产安全门禁。
- 调试管理员旁路、用户名/环境变量管理员推断或任何未登记后门不能作为角色授权证据。

## 关闭规则

1. 执行口令之前所有实施条目保持 `not-run`，本批状态保持 `待你确认`。
2. 实现完成后只标 `待验证`，并提交三份记录、证据路径、失败/限制和回滚结果。
3. 任一关键证据缺失、关键 mismatch、fail-open、审计字段缺失、未知 revision、双写或回滚不可执行时标 `阻塞`。
4. 只有用户完成第二次验收确认后，才可将本批和主计划 E3 状态改为 `已关闭`。
