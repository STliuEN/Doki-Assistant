# E4/AR-3/S3 测试与迁移证据

日期：2026-09-02  
最近更新：2026-09-03（暂停后恢复准备）  
状态：实施中  
负责人：Codex  
审阅/批准人：用户  
用户确认：2026-09-02，Q1-Q43 完成；执行确认已收到，验收确认尚未发生。

本文件只记录 E4 准备和后续迁移证据。证据状态只使用 `verified-local`、`verified-live`、`blocked`、`not-run`；`fixture`、`mock`、`historical`、`observed-only` 是证据类型或限制，不是状态。`verified-local` 只证明仓库/隔离环境中的动作，不证明在线业务数据或生产切换。

## 环境限制

- 平台：Windows / PowerShell；分支：`ai_document_assistant`；初始日期：2026-09-02；本次恢复：2026-09-03。
- E1/E2/E3 资源和证据保持隔离；本准备阶段没有启动、复用或清理它们。
- 本阶段只读取仓库文档、源代码和被 `.gitignore` 排除的本地 `backend/data` 文件；未读取 `.env` 推断目标。
- 未连接在线 MySQL、Django、Redis 或 Chroma；没有用户批准的 E4 source dump、target/restore allowlist 或停写窗口。
- 只读 OS 观察到两个身份未确认的 `mysqld.exe` 进程；按未知现有资源保护，未探测端口、未连接、未复用，也未将其计入 E4 拓扑。

## 证据表

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
| `E4-01` | 本地只读文件 + 待批准 source snapshot | 仓库/离线副本；在线 source 未连接 | fixture/observed-only | 生成可重放 inventory manifest；在线部分须有 server identity/权限证明 | 路径 containment；digest/计数可复现；未知资源不连接 | 本地非业务资源 manifest 准备中；批准 snapshot 尚未交付 | 继续执行只读盘点；在线 source 保持 not-run | `source-inventory.md` | Codex | 用户 | not-run |
| `E4-02` | E4 isolated target | 待建立 target/restore allowlist | fixture/live | identity-map dry-run、冲突/孤儿和幂等重放 | `conflict=0`、`orphan=0` 或有明确批准处置 | 尚未执行 | 等待 E4-01 和独立拓扑 preflight | `identity-map-contract.md` | Codex | 用户 | not-run |
| `E4-03` | E4 target/restore MySQL | 待建立 allowlist | live | additive/shadow schema、导入、行数/digest/FK/审计对账 | source/target/restore 零未解释差异 | 尚未执行 | 等待 E4-01/E4-02 和备份 gate | `rollback-runbook.md` | Codex | 用户 | not-run |
| `E4-04` | FastAPI + SQL runner | 待建立隔离运行拓扑 | fixture/live | 唯一写权威、重复/乱序、lease/fencing、kill/restart、timeout/cancel/error/orphan | 旧写入口零长期双写；旧 fencing token fail-closed | 尚未执行 | 等待 E4-03；不增加第三次用户确认 | `write-path-inventory.md` | Codex | 用户 | not-run |
| `E4-PREP-09` | Python 3.12.3；pytest 9.1.0；Ruff 0.15.17 | 当前工作树；无外部拓扑 | verified-local | 修正 `E4Target` tuple/list 快速路径校验；运行 `pytest -q tests/test_e4_guard.py tests/test_e4_inventory.py tests/test_note_template_route_matching.py`、Ruff、`compileall`、`git diff --check`、`scripts/check-docs.ps1` | 22 个定向测试通过；静态/文档门禁 exit 0；不得连接或写入业务资源 | `22 passed`；Ruff/compileall/diff check 通过；文档 `194 files, 178 local links` 通过；未建立网络/数据库连接 | 通过；仅证明本地守卫、inventory 和路由合同；在线业务证据仍 not-run | `backend/app/db/e4_guard.py`；`backend/tests/test_e4_guard.py`；`artifacts/local-inventory-v3.json` | Codex | 用户 | verified-local |
| `E4-PREP-10` | backend `uv` frozen environment | 当前工作树；无外部拓扑 | verified-local | 重跑 E4 guard/identity/inventory/route gate；修正无 source metadata 的既有 target 冲突分类，并确保 canonical UUID 显式拒绝大写 | 30 个定向测试和相关 Ruff 检查全部通过；不得连接或写入业务资源 | `30 passed in 0.75s`；`All checks passed!` | 通过；身份 dry-run 保持 fail-closed；真实 source/target/restore 仍 not-run | `backend/app/e4/identity.py`；`backend/tests/test_e4_identity.py` | Codex | 用户 | verified-local |

## 数据对账

- 当前准备阶段没有 source/target/restore 业务行数对账；本地 Chroma/MD5/图片/Skill 数量仍只是 `observed-only`，不构成迁移证据。
- 已生成脱敏离线 `artifacts/local-inventory-v3.json`：canonical manifest digest `7566814bfc0e4a16a9c61988d41074e2c486982840563853ded176f3e8ddb0ac`；文件封装 SHA-256 `8c018624c28192a7e84000ca6b1f455d08ee57d172a6c81792d9cf7058bf7faf`。canonical digest 按工具定义排除 `captured_at` 与自身摘要字段，不能替代正式 source snapshot digest。
- v3 计数为 4 collections/88 embeddings、MD5 7 records/7 values、图片 0 files、Skill objects 10；发现 2 个脱敏 `scope_conflict`。这些结果只作为本地观察，不能写入 `migration_maps` 或目标业务表。
- 后续仍必须分别记录 batch manifest digest、逐表/逐对象 content digest 和原始文件/归档 artifact digest；尚未生成正式业务 source manifest、`migration_maps`、目标业务行或审计 correlation。
- generation/active pointer 不在 E4 本批激活；Chroma 只作为待核验派生输入，正式重建属于 E5。

## 负向与恢复覆盖

- 已设计但未执行：unknown/duplicate identity、digest 漂移、FK/唯一冲突、重复/乱序、租约过期、旧 fencing token、kill/restart、超时、取消、异常、孤儿 job。
- 已设计但未执行：停写窗口、snapshot manifest、restore-forward、恢复后 revision/行数/digest/FK/audit 对账。
- 已修复并回归：笔记模板 reorder 路由冲突（`E4-ROUTE-01`）。
- 已修复并回归：E4 allowlist dataclass 快速路径校验绕过、DNS host 大小写端点重复检测和 DSN host 大小写匹配（`E4-PREP-09`）。
- 仍待 gate：加密配置 key 版本/重加密方案、图片 SQL 表、source/target/restore 身份和 allowlist。
- 未连接或注入 Redis/Chroma；未做真实文件删除、旧 generation 清理或 Django/旧脚本停写。
- 本轮暂停后恢复仍未连接或注入任何真实资源；没有执行 DDL、`migration_maps` 写入、停写、切换、删除或 GC。

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
