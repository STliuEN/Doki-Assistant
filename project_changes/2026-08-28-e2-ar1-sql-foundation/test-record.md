# E2/AR-1/S1 测试与迁移证据

状态：已关闭

## 环境限制

- 平台：Windows 11 / PowerShell；Git 分支 `ai_document_assistant`。准备时基线为 `33a8054dedd62745fb9fe0528efa2880a5fcc8a8`；当前实现 HEAD 为 `01fc34b`，工作树包含本批未提交变更。
- 当前已获 E2 实施授权；实现和验证仍只允许使用批准的 E2 隔离拓扑与合成数据。
- E2 MySQL/restore 拓扑已按批准创建并完成真实验证：验证期间 source `127.0.0.1:33317`、restore `127.0.0.1:33318`、network `doki-e2-20260828-net`，MySQL `8.4.11`；关闭动作后两个容器均 stopped，volume/network 保留。
- 未读取项目 `.env`，未连接或修改现有业务 MySQL、Redis、Chroma、Storage、文件/MD5 sidecar；只连接批准的 E2 source/restore MySQL。
- E1 两个 stopped 容器、两个 volume 和一个 network 只做名称/状态核对，未启动、挂载、修改、复用或清理。
- 关闭动作后 E2 source/restore 两个容器均为 stopped；E2 volume、network 和全部证据保留，未执行资源删除或清理。

## 证据字段

- `状态` 只使用 `verified-local`、`verified-live`、`blocked`、`not-run`。
- `结果/处置` 记录 `passed`、`failed`、`invalid`、`limitation` 或后续动作；fixture/mock/historical 是证据类型，不是状态。

## 证据表

| ID | 环境/版本 | 拓扑 | 证据类型 | 命令/动作 | 阈值 | 实际结果 | 结果/处置 | 日志/文件 | owner | approver | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `E2-PREP-01` | Git | 准备时工作树快照 | 只读本地 | `git rev-parse HEAD`、`git branch --show-current`、`git status --porcelain=v1 -uall` | 准备基线固定且当时干净 | 准备快照 HEAD `33a8054dedd62745fb9fe0528efa2880a5fcc8a8`；分支 `ai_document_assistant`；当时 porcelain 无条目 | passed；这是历史准备快照，不是当前状态 | 本文件、历史命令输出 | Codex | 用户 approved | verified-local |
| `E2-PREP-02` | Markdown/rg | 准备时活计划、交接手册、E1 证据 | 静态本地 | 核对 E1/E2 状态和关闭确认 | E1 当前事实源一致为已关闭；E2 在授权前不得实施 | 准备时 E2 为 `待你确认`；授权后已同步当前计划、蓝图和手册为 `实施中` | passed；历史准备快照已由后续记录修正 | `plan.md`、活计划 | Codex | 用户 approved | verified-local |
| `E2-PREP-03` | Python source/Alembic | 准备时 source tree | 静态本地 | 盘点 models、migrations、DB session、outbox、backup 工具和测试 | 明确可复用切片与缺口，不声称 runtime 通过 | 准备时为 2 条 Alembic revision/18 张 FastAPI 表、无通用 job/runner/UoW；当前已增加三条 E2 revision、UoW/job/runner 和 guarded ops | passed；见 `current-sql-inventory.md` 与本批实现记录 | 盘点文档 | Codex | 用户 approved | verified-local |
| `E2-PREP-04` | Docker metadata | 本机 Docker | 只读本地 | `docker ps -a --filter name=doki-e1`、volume/network list | E1 资源存在且 stopped；不得变更 | 两个 E1 MySQL 容器均 `Exited (0)`；两个 volume 和 `doki-e1-20260827-net` 保留 | passed；E2 禁止复用 | 本文件、命令输出 | Codex | 用户 approved | verified-local |
| `E2-PREP-05` | Python 3.12/uv | tmp_path + SQLite/source tree | fixture/静态本地 | `uv run pytest -q -p no:cacheprovider tests/test_migration_contract.py tests/test_skill_domain_models.py tests/test_skill_service_transactions.py tests/test_backup_restore.py` | 零失败；不连接外部服务；测试后工作树仍 clean | `45 passed in 42.25s`；执行时 E2 文档尚未写入，测试后 porcelain 无条目 | passed；只证明准备时现有局部合同 | pytest 输出、现有测试 | Codex | 用户 approved | verified-local |
| `E2-PREP-06` | Markdown/Git | source tree only | 静态本地 | `scripts/check-docs.ps1`；`git diff --check`；文件范围核对 | 零断链/围栏错误；diff check exit 0；无 backend/schema 变更 | `Markdown checks passed: 182 files, 163 local links`；diff check exit 0；工作树只含计划/证据文档 | passed；CRLF 提示不是 diff error；这是实施前快照 | 命令输出、`git status --short` | Codex | 用户 approved | verified-local |
| `E2-PREP-07` | Markdown/source tree | target schema proposal | 静态设计 | 逐表核对 E2/E3/E4/E5/E6 ownership、canonical 名称和 deferred DDL | 不把空结构、真实数据迁移和行为切换混在同一阶段 | `schema-map.md` 已经用户确认并冻结 UUID、audit/job 限额、lease/retry/backpressure 和 revision 拆分 | passed；尚未在真实数据库生成/执行 DDL | `schema-map.md` | Codex | 用户 approved | verified-local |
| `E2-LOCAL-SCHEMA` | Python 3.12/SQLAlchemy/Alembic | source tree + model recorder | fixture/静态本地 | E2 model/migration parity、线性 revision、legacy table 不变和 startup head gate 合同 | exact model/migration parity；unknown revision fail-closed | 通过；三条 revision 为 `20260828_0003_identity_auth`、`20260828_0004_jobs_audit`、`20260828_0005_rag_skill`，当前 head 为 `20260828_0005_rag_skill` | passed；仅本地合同，不替代 live bootstrap | `tests/test_foundation_models.py`、`tests/test_migration_contract.py` | Codex | 用户 approved | verified-local |
| `E2-LOCAL-UOW-JOBS` | Python 3.12/SQLite | tmp_path SQLite | fixture/local | UoW rollback、原子 enqueue、claim/lease/heartbeat/fencing/idempotency/retry/cancel/DLQ/backpressure | 无部分提交；旧 token 不能提交；终态不可重领 | 通过；repository/runner/primitive contracts covered | passed；SQLite 不证明 MySQL lock semantics | `tests/test_job_repository.py`、`tests/test_job_runner.py`、`tests/test_e2_primitives.py` | Codex | 用户 approved | verified-local |
| `E2-LOCAL-RUNTIME-GUARD` | Python 3.12/FastAPI | source tree + mocked guard | fixture/local | E2 runtime fail-closed、runner pool/lifecycle、独立 `/health/runner`、preflight issuance 校验 | 未授权/漂移 target 在建连或消费前拒绝；API readiness 与 runner liveness 分离 | 通过；scoped E2/runtime tests included | passed；未启动真实 runner/container | `tests/test_e2_runtime.py`、`tests/test_api_contracts.py`、`tests/test_e2_guard.py` | Codex | 用户 approved | verified-local |
| `E2-LOCAL-OPS` | Python 3.12 | tmp_path/source tree | fixture/local | manifest/tamper/path safety、canonical inventory/digest、旧 MySQL bundle provenance 拒绝、显式 `issue-preflight` CLI 合同 | 篡改/旧 bundle/未知 SQL 值 fail-closed；不把 secret 写入 stdout | 通过；CLI 和负向测试已加入 | passed；未执行真实 mysqldump/import | `tests/test_backup_restore.py`、`backend/scripts/backup_restore.py` | Codex | 用户 approved | verified-local |
| `E2-01-schema` | MySQL 8.4.11 | E2 源/恢复库 | 真实隔离 | 空库 bootstrap、head/model parity、schema/constraint diff | exact match；无 auto-DDL | source/restore 均为 head `20260828_0005_rag_skill`；33 张表，inventory 零差异 | passed；详细 live 证据见 `E2-07-schema-live` | `artifacts/mysql/source-inventory-gate-final.json`、`artifacts/mysql/restore-inventory-gate-final.json` | Codex | 用户 approved | verified-live |
| `E2-02-uow` | MySQL 8.4.11 | E2 源库 | 真实隔离 | job enqueue、commit/rollback 边界、cancel 和 audit correlation | 无部分提交或孤儿 job | live runner enqueue/audit 通过；rollback/constraint 细节由 SQLite 合同覆盖，未宣称 live 全覆盖 | passed with limitation；详细矩阵见 `E2-08-runner-live`、`E2-LOCAL-UOW-JOBS` | `artifacts/mysql/e2-live-runner-probe-execution.json`、`tests/test_e2_primitives.py` | Codex | 用户 approved | verified-live |
| `E2-03-runner` | MySQL 8.4.11 | 单 runner、并发 1 | 真实隔离 | claim/lease/heartbeat/fencing/idempotency/retry/cancel/DLQ/backpressure | 满足 plan 冻结不变量 | 真实 probe 全部通过；`GET_LOCK`/`SKIP LOCKED` 路径已验证 | passed；详细 live 证据见 `E2-08-runner-live` | `artifacts/mysql/e2-live-runner-probe-execution.json` | Codex | 用户 approved | verified-live |
| `E2-04-restart` | MySQL 8.4.11 | runner process + SQL | 真实隔离 | 在 claim/start/side-effect/commit 前后 kill/restart | 旧 fencing token 0 行提交；可恢复 job 只执行允许的重试 | 首进程 exit 1；第二进程 exit 0；attempt 1 abandoned、attempt 2/fencing 2 succeeded | passed；详细 restart events 独立留存 | `artifacts/logs/e2-live-1787911709-restart-events.jsonl`、`artifacts/mysql/e2-live-runner-probe-execution.json` | Codex | 用户 approved | verified-live |
| `E2-05-recovery` | MySQL 8.4.11 | E2 源/恢复库 | 真实隔离 | dump/manifest/tamper/restore/restore-forward；结构/行数/digest/约束对账 | 无差异；篡改 fail-closed | 最终 bundle、restore-forward 和 source/restore inventory 均零差异；非空目标拒绝已验证 | passed；详细 recovery 证据见 `E2-10-recovery-live` | `artifacts/mysql/source-final-execution.bundle/manifest.json`、`artifacts/logs/restore-forward-final-execution.log`、`artifacts/mysql/source-restore-inventory-compare-final.json` | Codex | 用户 approved | verified-live |
| `E2-06-regression` | Python 3.12/uv | source tree + tmp_path/SQLite | local/fixture | scoped/full pytest、Ruff、OpenAPI、lock、docs、diff | 全部 exit 0 | full `344 passed, 1 warning`；API contract `11 passed`；Ruff/OpenAPI/lock/docs/diff 全部通过 | passed；仅本地回归，不替代 live 数据证据 | `backend/openapi.json`、本批 `E2-12-final-static-gates` | Codex | 用户 approved | verified-local |
| `E2-07-schema-live` | MySQL `8.4.11` | E2 source/restore containers | verified-live | 显式短时 preflight；source/restore `alembic upgrade head`；读回 revision、表、列、索引、FK、CHECK、行数和 canonical digest | 两库精确 head；33 张表；结构/约束/行数/content digest 零差异；不自动连接业务库 | source 与 restore 均为 `20260828_0005_rag_skill`；最终 inventory SHA-256 均为 `df1bad4c3e31b51b5b7e73da3f69f129524b4192ea70549249d9dc696469071f`；两库各 33 张表 | passed；只在批准 E2 拓扑执行 | `artifacts/preflight/source-gate-final.json`、`artifacts/preflight/restore-gate-final.json`、`artifacts/mysql/source-inventory-gate-final.json`、`artifacts/mysql/restore-inventory-gate-final.json`、`artifacts/logs/source-migration.log`、`artifacts/logs/restore-migration-first.log` | Codex | 用户 approved | verified-live |
| `E2-08-runner-live` | MySQL `8.4.11` / Python 3.12 | E2 source；单 runner、并发 1 | verified-live | 幂等重复/冲突、retry、cancel、unknown handler、DLQ、backpressure、lease expiry/fencing、`GET_LOCK` 互斥、kill/restart | 旧 token 不能提交；重复不产生第二 job；retry 有界；取消/DLQ/backpressure fail-closed；重启后新 fencing token 成功 | probe `e2-live-1787911709`：duplicate `false`、冲突拒绝；retry attempt 2 成功；cancelled；unknown `dead_letter`；backpressure 拒绝；旧 token `stale_fencing_token`；`GET_LOCK` 第二 runner failed；首进程 exit 1、第二进程 exit 0，attempt 1 `abandoned`、attempt 2 `succeeded` | passed；synthetic jobs 仅用于 E2 证据 | `artifacts/mysql/e2-live-runner-probe-execution.json`、`artifacts/logs/e2-live-1787911709-restart-events.jsonl`、`artifacts/logs/e2-live-runner-probe-execution.log` | Codex | 用户 approved | verified-live |
| `E2-09-terminal-gate` | MySQL `8.4.11` | E2 source | verified-live | 只读查询全部 job/attempt 的终态、active/orphan 关联 | 全部 job 为 `succeeded/cancelled/dead_letter`；无 `leased/running`、无 orphan attempt；retry_wait 必须有结束时间 | 63/63 job 终态（22 cancelled、10 dead_letter、31 succeeded）；76 attempts；17 abandoned、9 cancelled、10 dead_letter、9 retry_wait（均已结束）、31 succeeded；无 active/orphan | passed；终态 gate artifact 独立保存 | `artifacts/mysql/source-job-terminal-final.json`、`artifacts/preflight/source-job-terminal-final.json` | Codex | 用户 approved | verified-live |
| `E2-10-recovery-live` | MySQL `8.4.11` | E2 source -> restore | verified-live | guarded container-exec `mysqldump --single-transaction`、manifest verify、restore-forward、独立 restore inventory | source metadata 完整；bundle/digest/结构/行数/约束零差异；篡改和非空目标 fail-closed | 最终 bundle content SHA-256 `7fa3e0888b99823cbb4650dc792e34c352d8fd9b5308ae0da331d50be3f20b9d`；restore-forward verified；source/restore inventory SHA-256 相同 | passed；历史 host-side `[WinError 2]` 和非空 restore 拒绝单独保留，不覆盖成功结果；restore 库仅在批准范围内清理后重试 | `artifacts/mysql/source-final-execution.bundle/manifest.json`、`artifacts/logs/source-empty-dump.log`、`artifacts/logs/source-empty-dump-container.log`、`artifacts/logs/restore-forward-final-execution.log`、`artifacts/mysql/restore-inventory-before-final-reset.json`、`artifacts/mysql/source-restore-inventory-compare-final.json` | Codex | 用户 approved | verified-live |
| `E2-11-preflight-final` | MySQL `8.4.11` / Docker metadata | source + restore | verified-live | 重新签发 15 分钟 preflight，并核对 container id/image/network/port/server UUID | 记录未过期；目标只在 allowlist；server UUID 与连接指纹一致 | source/restore gate preflight 已签发并用于最终 inventory；两容器均运行 `mysql:8.4`，server UUID 与 live fingerprint 校验通过 | passed；token 原文未写入 artifact/stdout | `artifacts/preflight/source-gate-final.json`、`artifacts/preflight/restore-gate-final.json` | Codex | 用户 approved | verified-live |
| `E2-13-resource-boundary` | Docker | E1 protected + E2 approved topology | verified-live | 关闭前只读 `docker inspect`、network inspect、volume list | E1 containers stopped and untouched; E2 only on `doki-e2-20260828-net` with loopback ports `33317/33318`; approved volumes retained | 关闭前快照：E1 containers `exited` with no host ports; E2 containers `running` on the dedicated bridge; network contains exactly the two E2 containers; E1/E2 volumes retained | passed；未执行任何 Docker mutation or cleanup | `artifacts/logs/resource-boundary-final.json` | Codex | 用户 approved | verified-live |
| `E2-14-close-resource-boundary` | Docker | E1 protected + E2 approved topology | verified-live | 用户确认关闭后停止 E2 两个容器，再只读核对容器、network 和 volume | 两个 E2 容器 stopped；E1 容器仍 stopped；四个 volume 和两个 network 保留；不删除资源 | `doki-e2-20260828-mysql`、`doki-e2-20260828-mysql-restore` 均 `exited (0)`；E1 两容器仍 `exited`；四个 volume 保留；E2 network 保留且无连接容器 | passed；仅停止 E2 容器，未执行 prune、删除或 Git 操作 | `artifacts/logs/resource-boundary-closure.json` | Codex | 用户 approved | verified-live |
| `E2-15-close-static-gates` | Python 3.12/uv/PowerShell | source tree + tmp_path/SQLite | verified-local | 全量 pytest、Ruff、OpenAPI `--check`、`uv lock --check`、无 Git Markdown fence/link 检查 | 全部 exit 0；不调用 Git；不连接业务依赖 | `344 passed, 1 warning in 23.81s`；Ruff passed；OpenAPI current；lock resolved 235 packages；Markdown `225 files, 171 local links` | passed；warning 仍为 Python 3.12 `aiosqlite` datetime adapter 弃用提示；按用户要求未运行任何 Git 命令 | 命令输出、本文件 | Codex | 用户 approved | verified-local |
| `E2-12-final-static-gates` | Python 3.12/uv | backend source tree + pytest 临时隔离根目录 | verified-local | 完整 pytest、Ruff、OpenAPI/API contract、`uv lock --check`、docs、`git diff --check` | 全部 exit 0；无最终 OpenAPI drift/断链/whitespace error；不连接业务依赖 | 完整 `344 passed, 1 warning in 27.17s`；API contract `11 passed in 12.22s`；Ruff passed；`uv lock --check` resolved 235 packages；OpenAPI 重新生成后 `--check` passed；文档 `182 files, 161 local links`；diff check exit 0 | passed；首次 OpenAPI gate 捕获缺少 `/health/runner`，只重生成该路由合同后复检通过；warning 为 Python 3.12 `aiosqlite` datetime adapter 弃用提示 | `backend/openapi.json`、pytest/Ruff/OpenAPI/lock/docs/diff 输出、本文件 | Codex | 用户 approved | verified-local |

## 数据对账

- 源/恢复表行数：两库均 33 张表；`jobs=63`、`job_attempts=76`、`audit_events=312`，其余表行数与 inventory 记录一致。
- source/content digest：最终 source bundle content SHA-256 为 `7fa3e0888b99823cbb4650dc792e34c352d8fd9b5308ae0da331d50be3f20b9d`；source/restore inventory SHA-256 均为 `df1bad4c3e31b51b5b7e73da3f69f129524b4192ea70549249d9dc696469071f`。
- Alembic revision：source 与 restore 均为 `20260828_0005_rag_skill`；migration 日志显示从空库按五条线性 revision 到 head。
- job/attempt/fencing/audit：真实 probe 与终态 gate 通过；无 active/orphan attempt，旧 fencing token 提交被拒绝，audit actions 与 probe jobs 关联完整。
- 差异及处理：早期 restore-forward 使用旧 bundle 的结果保留为历史；最终 bundle 重新 restore-forward 零差异。非空 restore 目标拒绝、受控清理和 fixture cleanup 均有独立记录。

## 负向与恢复覆盖

- denylist DSN、unknown revision、自动 DDL：本地负向合同已通过；真实 preflight、空库 migration 和 target fingerprint 已验证。
- duplicate、lease expiry、heartbeat、旧 fencing token、retry、cancel、DLQ、backpressure：真实 MySQL probe 已通过；`GET_LOCK` 与 `SKIP LOCKED` 路径有 live 证据。
- graceful shutdown：本地 runner 测试和真实 kill/restart 已通过；旧进程退出后新进程以 fencing token 2 完成 job。
- manifest 篡改、恢复到已存在目标、restore-forward：离线 fixture 合同已通过；真实 E2 bundle/restore-forward 零差异；非空目标拒绝单独保留。
- Chroma generation 重建属于 E5；E2 只预留 SQL schema，不把 Chroma E2E 列为本阶段退出证据。

## 不能证明的内容

- 静态盘点不能证明 MySQL 行锁、`SKIP LOCKED`、事务隔离、lease/fencing、恢复或性能。
- E1 的 MySQL/Chroma 证据不能替代 E2 新 schema/runner 的真实依赖证据。
- SQLite/mock/unit test 不能替代 MySQL 8.4 的并发、DDL 和恢复证据。
- E2 不证明登录、refresh/revocation、业务迁移、RAG 查询、Skill 发布、真实 UI E2E、HA 或生产 RPO/RTO。
- 最终静态门禁（`E2-12-final-static-gates`）已通过；用户于 2026-08-28 审阅并批准 E2 关闭。

## 关闭确认

- 关闭口令：`批准关闭 E2`（用户，2026-08-28）。
- 关闭范围：E2/S1/AR-1 执行计划及其证据；不扩展到后续阶段或其他发布门禁。
- 关闭后保留所有成功/失败 probe、manifest、dump、日志、volume、network 和 E1 保护资源。
