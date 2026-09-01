# E3/AR-2/S2 变更日志

状态：已关闭
负责人：Codex  
执行口令：`开始执行e3`；恢复口令：`继续执行e3`
关闭确认：2026-09-01，用户明确回复 `批准关闭 E3`

| 时间 | commit/文件/schema | 变更 | 原因 | 影响 | 回滚点 | 负责人 | 证据 |
|---|---|---|---|---|---|---|---|
| 2026-08-31 | `project_changes/2026-08-31-e3-ar2-fastapi-auth/plan.md` | 新建 E3 完整开发计划，记录身份迁移、cookie/token、session、角色、grant、审计、shadow、切换、回滚和退出条件 | 将 E3/AR-2 的共享理解固化为唯一执行入口 | 仅新增计划文档；未改代码、schema、配置、前端、数据库或外部资源 | 删除本批文档；不影响运行状态 | Codex | `E3-PREP-01` |
| 2026-08-31 | `project_changes/2026-08-31-e3-ar2-fastapi-auth/change-log.md` | 新建变更记录模板并登记当前仅文档准备状态 | 遵循阶段三件套和两次大确认纪律 | 仅新增文档 | 删除本批文档 | Codex | `E3-PREP-01` |
| 2026-08-31 | `project_changes/2026-08-31-e3-ar2-fastapi-auth/test-record.md` | 新建测试/迁移证据占位，明确所有实施项在执行口令前为 `not-run` | 防止把静态审阅误写成认证或迁移证据 | 仅新增文档 | 删除本批文档 | Codex | `E3-PREP-01` |
| 2026-08-31 | `project_changes/README.md` | 增加 E3 计划入口 | 使当前阶段材料可追溯，避免与 E2 记录混淆 | 仅更新历史变更索引 | 恢复 E3 入口行 | Codex | `E3-PREP-02` |

## 执行记录

| 时间 | commit/文件/schema | 变更 | 原因 | 影响 | 回滚点 | 负责人 | 证据 |
|---|---|---|---|---|---|---|---|
| 2026-09-01 | `backend/alembic/versions/20260831_0006_e3_auth_runtime.py`, `20260901_0007_e3_auth_constraints.py`, `backend/app/models/identity_domain.py` | 增加 E3 用户 profile、session metadata、refresh/revocation、role binding、authorization grant 和约束，启动校验精确 revision | 建立 FastAPI SQL 认证写权威 | 仅作用于 E3 隔离 schema；不修改 E1/E2 schema | 停写并按 snapshot/restore-forward 回滚 | Codex | `target-final.inventory.json`, `restore-final.inventory.json` |
| 2026-09-01 | `backend/app/auth/`, `backend/app/router/user.py`, `backend/app/utils/auth_utils.py` | 实现 register/login/detail/update/reset/refresh/logout、PBKDF2 兼容与 Argon2id upgrade、JWT access、opaque refresh rotation/replay、session revoke、token version 和 SQL role authorization | 接管 FastAPI `/user/*` 认证生命周期 | refresh 原文只在 HttpOnly cookie；SQL 只保留 digest；Redis/Django 不作认证权威 | 停止 FastAPI auth 写入并恢复最近 snapshot | Codex | `api-live-result-v2.json`, backend tests |
| 2026-09-01 | `backend/app/core/`, `backend/app/db/`, `backend/scripts/e3_preflight.py`, `bootstrap_e3_admins.py`, `import_e3_users.py` | 增加 correlation/audit 失败事务、E3 allowlist/preflight、一次性双管理员 bootstrap、只读 dump 解析/dry-run/import 工具 | 保证 fail-closed、四眼审批和资源隔离 | `skill_admin` 与 `security_admin` 强制不同身份；真实 source import 需批准 dump | preflight/approval 失效即停止 | Codex | `preflight-target-final.json`, `preflight-restore-final.json`, `api-live-result-v2.json` |
| 2026-09-01 | `DjangoUserService/apps/user/management/commands/export_e3_users.py`, `backend/app/auth/migration.py` | 通过 Django ORM 只读事务导出 2 个测试用户；按 Django `TIME_ZONE` 规范化 naive `last_login`，允许 bio 的换行/制表符并拒绝危险控制字符 | 保留 source profile/hash 语义并避免文本或时间静默变形 | 只生成临时 source JSON；不写 Django source 库 | 删除临时 source 文件；导入前 dry-run fail-closed | Codex | `django-users-e3-source.manifest.json`, `django-users-e3-migration-evidence.json` |
| 2026-09-01 | E3 target/restore MySQL data | 在 fresh preflight 下完成 source 2/2 用户 dry-run 和原子导入；按确定性 UUID 写入 mapping/profile/default role，并以不同身份完成 `skill_admin`/`security_admin` bootstrap | 完成真实测试数据迁移和四眼角色初始化 | target 现有审计记录保留；不迁移旧 session/refresh token | target-before snapshot；停写后可 restore-forward | Codex | `django-users-e3-migration-evidence.json`, `target-before-user-import-v3.manifest.json` |
| 2026-09-01 | E3 restore-forward after user import | 对 target post-import 快照执行二进制 restore 到独立 restore 库，验证 36 表 schema、行数和 canonical digest 零差异；记录首次文本管道编码 mismatch 并修正 | 证明恢复过程保留 UTF-8 JSON 与认证数据完整性 | restore 库重建为本次 snapshot 内容 | 保留 target/restore inventory 和 diff；不执行 populated downgrade | Codex | `target-post-user-import-v1.manifest.json`, `target-post-user-import.inventory.json`, `restore-post-user-import.inventory.json`, `restore-forward-post-user-import.diff.json` |
| 2026-09-01 | `front/src/api/`, `front/src/pages/`, `front/src/stores/`, `front/vite.config.ts` | `/user` proxy 切至 FastAPI，Axios `withCredentials`、refresh single-flight、内存 access token，移除 refresh localStorage/sessionStorage | 与 HttpOnly cookie 认证契约一致 | 旧 Django 前端认证入口不再使用 | 恢复 proxy 配置并重新登录 | Codex | `e3-final-authenticated-notes.png`, frontend tests/build |
| 2026-09-01 | E3 target/restore data and evidence | 完成 live API、浏览器、角色/grant 负向矩阵、failure injection、清理 smoke 身份和 restore-forward 对账；删除临时 SQL dump、管理员 ID、原始审批口令、live 脚本和旧证据 | 收束现场并避免敏感中间文件残留 | target/restore 业务身份表清零；append-only audit 保留 | 保留正式最终 evidence，可按清单重建验证现场 | Codex | `cleanup-manifest.json`, `restore-forward-final.diff.json` |
| 2026-09-01 | E3 runtime artifact cleanup and final rerun | 删除 source 原文、SQL dump、dump payload bundle、snapshot metadata 和完整 Docker inspect；保留脱敏 manifest/inventory/diff；重跑 backend `354`、Django `20`、frontend `28` 测试及 E3 scoped Ruff/lint/build | 完成敏感中间材料清理并使最终测试计数与当前工作树一致 | 不改变 E3 target/restore 数据或 E1/E2 资源 | 保留 target/restore 容器、正式证据和脱敏清单；不保留 dump payload | Codex | `cleanup-manifest.json`, `target-post-user-import-v1.manifest.json`, `target-post-user-import.inventory.json`, `restore-forward-post-user-import.diff.json` |

## 当前限制

- source 为本机测试 Django MySQL 库；只读导出、2 用户 dry-run/import、mapping/profile/hash 对账和双管理员 bootstrap 已完成。旧 session/refresh token 未迁移，用户需重新登录。
- 本地开发按用户决定不启用 CSRF/Origin 防护；refresh cookie 仍固定 `HttpOnly + SameSite=Strict + Path=/user/refresh-token/`。
- 不做公网、HA、生产加固、E4/E5/E6 或 E1/E2 资源变更。

## 后续记录规则

每个实现变更必须关联一个 `E3-*` 任务、一个回滚点和一个证据 ID；实现完成先记录为 `待验收`。用户于 2026-09-01 完成第二次验收确认并明确回复 `批准关闭 E3`，本批状态现为 `已关闭`；该关闭不授权 E4。

## 收口检查点（2026-09-01）

用户已发出 `继续执行e3`，并于 2026-09-01 明确回复 `批准关闭 E3`；本批已完成实现、测试数据迁移、证据收口和临时材料清理，状态为 `已关闭`。最终证据见 `.runtime/e3/api-live-result-v2.json`、`django-users-e3-source.manifest.json`、`django-users-e3-migration-evidence.json`、`target-post-user-import.inventory.json`、`restore-post-user-import.inventory.json`、`restore-forward-post-user-import.diff.json`、`target-post-user-import-v1.manifest.json` 和 `output/playwright/e3-final-authenticated-notes.png`。

E3 两个 MySQL 容器保持 healthy 供复核；FastAPI、Vite、Playwright 已停止；E1/E2 资源未启动、未复用、未清理。E4/AR-3 仍为 `待你确认`，未因 E3 关闭而启动。
