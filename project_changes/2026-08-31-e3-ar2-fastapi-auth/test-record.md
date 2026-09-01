# E3/AR-2/S2 测试与迁移证据

状态：已关闭
负责人：Codex  
执行口令：`开始执行e3`；恢复口令：`继续执行e3`
关闭确认：2026-09-01，用户明确回复 `批准关闭 E3`

本文件只记录 E3 证据。执行确认和恢复确认均已收到；用户已于 2026-09-01 完成第二次验收并批准关闭 E3。证据状态只使用 `verified-local`、`verified-live`、`blocked`、`not-run`；`fixture`、`mock`、`historical` 是证据类型，不是状态。

## 环境限制

- 平台：Windows / PowerShell；当前分支：`ai_document_assistant`。
- E2/AR-1 已关闭；E2 source/restore 容器、volume、network 和证据保留且禁止复用。
- 本批使用新的 E3 隔离 MySQL 8.4 target/restore 拓扑；E1/E2 资源未启动、未复用、未清理。
- source 用户数据只能来自用户批准的只读 dump 或脱敏离线副本；不得读取 `.env` 推断目标，不得连接在线 Django 写库。
- 当前 FastAPI、Vite、Playwright 已停止；E3 MySQL target/restore 保持 healthy 供关闭后复核。

## 证据表

| ID | 环境/版本 | 拓扑 | 证据类型 | 命令/动作 | 阈值 | 实际结果 | 结果/处置 | 日志/文件 | owner | approver | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `E3-PREP-01` | source tree / UTF-8 Markdown | 仓库文件 | verified-local | 读取 E3 计划、交接手册、蓝图、E2 关闭记录和阶段模板 | E3 必须位于 E2 之后；状态为待确认；不授权跳阶段 | 已核对 E3=`AR-2/S2`、E2 已关闭；本批状态保持 `待你确认` | passed；仅证明文档入口和阶段边界，不证明实现 | `plan.md`、`docs/architecture_rewrite_plan.md`、`docs/architecture-execution-handoff-2026-08-26.md`、E2 records | Codex | 用户 | verified-local |
| `E3-PREP-02` | Python/TypeScript source tree | source tree only | verified-local | 静态检索 FastAPI auth helper、Django user routes、Vite `/user` proxy、identity models、Redis/YAML admin path | 明确现状与目标差距，不将局部 primitive 当作接管完成 | 已确认 FastAPI 当前依赖 Django JWT/Redis；Vite `/user` 指向 Django；E2 auth tables 仅为结构 | passed；未修改或调用这些路径 | `backend/app/utils/auth_utils.py`、`backend/app/router/user.py`、`front/vite.config.ts`、`DjangoUserService/apps/user/` | Codex | 用户 | verified-local |
| `E3-PREP-03` | 用户质询记录 | 设计树 | verified-local | 固化 Q1-Q45 及 Q41-B 决策 | 所有关键范围、迁移、token、cookie、role、审计、回滚和验收分支已回答 | 已形成完整共享理解：本地开发、完整接管、两次大确认、唯一执行口令 `开始执行e3` | passed；本记录不替代用户执行授权 | `plan.md` §2、§12 | Codex | 用户 | verified-local |
| `E3-PREP-04` | source tree | 无外部拓扑 | verified-local | E3 三件套和索引链接/状态一致性检查 | 文件存在、Markdown fence/link 无错误、状态一致 | 已完成只读检查 | 通过 | 本目录三份记录、`project_changes/README.md` | Codex | 用户 | verified-local |
| `E3-00-preflight` | MySQL 8.4 / Docker | 新 E3 allowlist | verified-live | 口令、资源/DSN/server UUID/image/network/port preflight | 只允许 E3 资源；E1/E2/业务资源 deny；未过不得建连 | target/restore preflight 均通过 | 通过 | `.runtime/e3/preflight-target-final.json`, `.runtime/e3/preflight-restore-final.json` | Codex | 用户 | verified-live |
| `E3-01-schema` | MySQL 8.4 | E3 target/restore | verified-live | user_profiles、session metadata、authorization grant、Alembic head/migration | model/migration parity；精确 head；restore 零差异 | target/restore 均 36 表，revision `20260901_0007_e3_auth`，inventory SHA 相同 | 通过 | `.runtime/e3/target-final.inventory.json`, `.runtime/e3/restore-final.inventory.json` | Codex | 用户 | verified-live |
| `E3-02-migration` | MySQL 8.4 / source dump | E3 source -> target -> restore | verified-live | 全量用户 dry-run、UUID mapping、profile/hash import、冲突拒绝、manifest/restore-forward | 关键冲突零容忍；行数/digest/约束/mapping 零差异；证据不含完整 hash/未脱敏 PII | 本机测试 Django MySQL 只读导出 2 用户；dry-run `2/2` 通过，原子导入 `2/2`；2 maps/2 profiles；身份、PBKDF2 hash digest、profile、status 均匹配；双管理员 bootstrap 成功且身份不同 | 通过；source 原文和完整 hash 不保留为正式证据 | `.runtime/e3/django-users-e3-source.manifest.json`, `.runtime/e3/django-users-e3-migration-evidence.json`, `.runtime/e3/target-before-user-import-v3.manifest.json` | Codex | 用户 | verified-live |
| `E3-03-auth-lifecycle` | Python 3.12 / MySQL 8.4 | FastAPI + SQL | verified-live | register/login/refresh/logout/password/profile/session lifecycle | access/opaque refresh、cookie、rotation/replay、token version、disabled/locked 全部 fail-closed | live API 27 checks 全部通过 | 通过 | `.runtime/e3/api-live-result-v2.json` | Codex | 用户 | verified-live |
| `E3-04-role-grant-audit` | Python 3.12 / MySQL 8.4 | role/grant/audit | verified-live | bootstrap、role separation、four-eyes approve/revoke、审计必填字段、correlation query | 同身份冲突和越权全部拒绝；无 secret/PII；append-only | 角色分离、四眼审批、越权拒绝和审计脱敏检查通过 | 通过 | `.runtime/e3/api-live-result-v2.json`, `.runtime/e3/cleanup-manifest.json` | Codex | 用户 | verified-live |
| `E3-05-frontend` | Node/Vite/Chromium | Vite -> FastAPI | verified-live | proxy、withCredentials、cookie、refresh single-flight、`/user/*` 浏览器流程 | 无 Django 前端直连；cookie 正确；401 refresh 后原请求只重试一次 | 登录、FastAPI proxy、HttpOnly cookie、无认证 Web Storage、console 0 errors 通过 | 通过 | `output/playwright/e3-final-authenticated-notes.png`, `front/README.md` | Codex | 用户 | verified-live |
| `E3-06-shadow-cutover` | MySQL 8.4 / Django read-only boundary | E3 target + old read-only | verified-live | failure injection、snapshot restore-forward、无双写回退和切换边界 | 关键 mismatch 为零；回滚可执行；无 Django 新写入 | post-import target/restore 均 36 表、revision `20260901_0007_e3_auth`，inventory SHA-256 均为 `fb487e2d705e73031e9b986f92dc903db4f5be3289428c0213853ddb5dc38926`；restore-forward `equal: true`；首次文本编码 mismatch 已用 binary stdin 修正 | 通过；Django 仍只读，未发生双写 | `.runtime/e3/target-post-user-import.inventory.json`, `.runtime/e3/restore-post-user-import.inventory.json`, `.runtime/e3/restore-forward-post-user-import.diff.json` | Codex | 用户 | verified-live |
| `E3-07-final-gate` | source tree + E3 isolated dependencies | API/UI/SQL | verified-local | full pytest、Django test、Ruff、ESLint、Vite build、OpenAPI/lock、证据审阅 | 测试/构建退出码为 0；限制明确；实现者先提交 `待验收` | backend `354 passed`；Django `20 passed`；frontend `28 passed`；E3 Ruff、ESLint、Vite build 通过；一次异步测试瞬时超时后单测与全量重跑均通过 | 通过；用户已于 2026-09-01 验收确认 | `.runtime/e3/api-live-result-v2.json`, `plan.md`, `change-log.md` | Codex | 用户 | verified-local |

附加边界检查：全仓 Ruff 检查发现 7 个既有、非 E3 范围问题（`mcp_servers/powershell_ls_server.py`、`mcp_servers/public_info_server.py`、`seed_templates.py`）；E3 作用域 Ruff 已通过，本批不修改这些无关文件，也不将其作为 E3 关闭阻断。

## 数据对账结果

- target/restore 均为 36 张表，revision `20260901_0007_e3_auth`，post-import inventory SHA-256 均为 `fb487e2d705e73031e9b986f92dc903db4f5be3289428c0213853ddb5dc38926`。
- source 只读导出为 2 个 active 测试用户；target/restore 各有 2 `users`、2 `user_profiles`、2 `migration_maps`，2 个 source hash digest 与 target hash digest 一致，profile/身份/status/UUID mapping 全部一致。
- `skill_admin` 与 `security_admin` 分别绑定不同 target UUID；本次 bootstrap 成功审计 1 条，历史 append-only bootstrap 审计仍保留。
- restore-forward diff：`equal: true`，无 missing/extra/changed tables；首次文本 stdin 导入造成的 UTF-8 JSON mismatch 已纠正并记录。
- live API：27 checks，0 failures；浏览器 HttpOnly cookie、refresh retry、FastAPI proxy 和 storage redaction 已验证。

## 不能证明的内容

- 计划材料、静态检索、SQLite、mock 或 fixture 不能证明 MySQL 8.4 的锁、事务、恢复、真实用户迁移或唯一写权威。
- E2 已关闭证据不能替代 E3 用户/hash/session/role/audit 证据。
- 旧 Django 单测、Redis blacklist 单测或现有 `SyntheticAuthRepository` 不能证明 FastAPI 已接管认证。
- 开发环境 `SameSite=Strict` 且无 CSRF/Origin 中间件的结果不能被描述为生产安全门禁。
- 调试管理员旁路、用户名/环境变量管理员推断或任何未登记后门不能作为角色授权证据。

## 关闭规则

1. 执行口令之前所有实施条目保持 `not-run`，本批状态保持 `待你确认`（历史准备阶段规则）。
2. 实现完成后只标 `待验收`，并提交三份记录、证据路径、失败/限制和回滚结果。
3. 任一关键证据缺失、关键 mismatch、fail-open、审计字段缺失、未知 revision、双写或回滚不可执行时标 `阻塞`。
4. 用户已于 2026-09-01 完成第二次验收确认并明确回复 `批准关闭 E3`；本批和主计划 E3 状态均已改为 `已关闭`，E4 仍保持 `待你确认`。

## 收口检查点（2026-09-01）

用户已发出 `继续执行e3`，并于 2026-09-01 明确回复 `批准关闭 E3`。实现、live/restore 验证、浏览器检查、失败注入、清理和文档闭环已完成；本批状态为 `已关闭`。

最终证据：`.runtime/e3/api-live-result-v2.json`（27 checks，0 failures）、`.runtime/e3/django-users-e3-source.manifest.json`、`.runtime/e3/django-users-e3-migration-evidence.json`、`.runtime/e3/target-post-user-import.inventory.json`、`.runtime/e3/restore-post-user-import.inventory.json`、`.runtime/e3/restore-forward-post-user-import.diff.json`、`.runtime/e3/target-post-user-import-v1.manifest.json`、`.runtime/e3/cleanup-manifest.json`、`output/playwright/e3-final-authenticated-notes.png`。

真实 Django 用户迁移限制已解除：本机测试库 2 用户已完成只读导出、dry-run、原子 import、hash/profile/mapping 对账和恢复验证。正式证据不保留 source 原文、完整 hash 或审批口令；旧 session/refresh token 未迁移。
