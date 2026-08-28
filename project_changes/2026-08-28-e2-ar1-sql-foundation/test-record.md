# E2/AR-1/S1 测试与迁移证据

状态：实施中

## 环境限制

- 准备平台：Windows 11 / PowerShell；Git 分支 `ai_document_assistant`，HEAD `33a8054dedd62745fb9fe0528efa2880a5fcc8a8`。
- 当前已获 E2 实施授权；实现和验证仍只允许使用批准的 E2 隔离拓扑与合成数据。
- E2 MySQL/restore 拓扑尚未批准或创建；本文件没有 `verified-live` 的 E2 SQL 证据。
- 未读取项目 `.env`，未连接或修改 MySQL、Redis、Chroma、Storage、文件/MD5 sidecar。
- E1 两个 stopped 容器、两个 volume 和一个 network 只做名称/状态核对，未启动、挂载、修改或清理。

## 证据字段

- `状态` 只使用 `verified-local`、`verified-live`、`blocked`、`not-run`。
- `结果/处置` 记录 `passed`、`failed`、`invalid`、`limitation` 或后续动作；fixture/mock/historical 是证据类型，不是状态。

## 证据表

| ID | 环境/版本 | 拓扑 | 证据类型 | 命令/动作 | 阈值 | 实际结果 | 结果/处置 | 日志/文件 | owner | approver | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `E2-PREP-01` | Git | 当前工作树 | 只读本地 | `git rev-parse HEAD`、`git branch --show-current`、`git status --porcelain=v1 -uall` | 固定基线；准备前干净 | HEAD `33a8054dedd62745fb9fe0528efa2880a5fcc8a8`；分支 `ai_document_assistant`；porcelain 无条目 | passed | 本文件、命令输出 | Codex | 用户 approved | verified-local |
| `E2-PREP-02` | Markdown/rg | 活计划、交接手册、E1 证据 | 静态本地 | 核对 E1/E2 状态和关闭确认 | E1 所有当前事实源一致为已关闭；E2 未实施 | E1 计划/测试/日志、主计划、蓝图、手册和索引均为 `已关闭`；E2 为 `待你确认`。仅根 README 有 2026-08-25 旧“当前”口径 | passed；本批同步 README | `plan.md`、活计划 | Codex | 用户 pending | verified-local |
| `E2-PREP-03` | Python source/Alembic | source tree only | 静态本地 | 盘点 models、migrations、DB session、outbox、backup 工具和测试 | 明确可复用切片与缺口，不声称 runtime 通过 | 2 条 Alembic revision/18 张 FastAPI 表；Django user 表独立；无通用 job/runner/UoW；局部 outbox 无 lease/fencing/DLQ；backup 工具只封装离线 dump | passed；见 `current-sql-inventory.md` | 盘点文档 | Codex | 用户 pending | verified-local |
| `E2-PREP-04` | Docker metadata | 本机 Docker | 只读本地 | `docker ps -a --filter name=doki-e1`、volume/network list | E1 资源存在且 stopped；不得变更 | 两个 E1 MySQL 容器均 `Exited (0)`；两个 volume 和 `doki-e1-20260827-net` 保留 | passed；E2 禁止复用 | 本文件、命令输出 | Codex | 用户 pending | verified-local |
| `E2-PREP-05` | Python 3.12/uv | tmp_path + SQLite/source tree | fixture/静态本地 | `uv run pytest -q -p no:cacheprovider tests/test_migration_contract.py tests/test_skill_domain_models.py tests/test_skill_service_transactions.py tests/test_backup_restore.py` | 零失败；不连接外部服务；测试后工作树仍 clean | `45 passed in 42.25s`；执行时 E2 文档尚未写入，测试后 porcelain 无条目 | passed；只证明现有局部合同 | pytest 输出、现有测试 | Codex | 用户 pending | verified-local |
| `E2-PREP-06` | Markdown/Git | source tree only | 静态本地 | `scripts/check-docs.ps1`；`git diff --check`；文件范围核对 | 零断链/围栏错误；diff check exit 0；无 backend/schema 变更 | `Markdown checks passed: 182 files, 163 local links`；diff check exit 0；工作树只含计划/证据文档 | passed；CRLF 提示不是 diff error | 命令输出、`git status --short` | Codex | 用户 pending | verified-local |
| `E2-PREP-07` | Markdown/source tree | target schema proposal | 静态设计 | 逐表核对 E2/E3/E4/E5/E6 ownership、canonical 名称和 deferred DDL | 不把空结构、真实数据迁移和行为切换混在同一阶段 | 已形成 `schema-map.md` 草案；等待用户确认 UUID、audit/job 限额、lease/retry/backpressure 和 revision 拆分 | passed as draft；尚未冻结或生成 DDL | `schema-map.md` | Codex | 用户 pending | verified-local |
| `E2-01-schema` | MySQL 8.4 | E2 源/恢复库 | 真实隔离 | 空库 bootstrap、head/model parity、schema/constraint diff | exact match；无 auto-DDL | 未运行 | 等待 E2 授权 | future artifacts | Codex | 用户 pending | not-run |
| `E2-02-uow` | Python + MySQL 8.4 | E2 源库 | 真实隔离 + unit | commit/rollback/cancel/constraint/job enqueue 原子性 | 无部分提交或孤儿 job | 未运行 | 等待实现 | future tests/logs | Codex | 用户 pending | not-run |
| `E2-03-runner` | MySQL 8.4 | 单 runner、并发 1 | 真实隔离 | claim/lease/heartbeat/fencing/idempotency/retry/cancel/DLQ/backpressure | 满足 plan 冻结不变量 | 未运行 | 等待实现 | future tests/logs | Codex | 用户 pending | not-run |
| `E2-04-restart` | MySQL 8.4 | runner process + SQL | 真实隔离 | 在 claim/start/side-effect/commit 前后 kill/restart | 旧 fencing token 0 行提交；可恢复 job 只执行允许的重试 | 未运行 | 等待实现 | future logs | Codex | 用户 pending | not-run |
| `E2-05-recovery` | MySQL 8.4 | E2 源/恢复库 | 真实隔离 | dump/manifest/tamper/restore/restore-forward；结构/行数/digest/约束对账 | 无差异；篡改 fail-closed | 未运行 | 等待实现与拓扑批准 | future bundles/logs | Codex | 用户 pending | not-run |
| `E2-06-regression` | Python/source tree | 隔离测试环境 | local/fixture | pytest、Ruff、OpenAPI、lock、docs、diff | 全部 exit 0 | 未运行（准备收口仅运行文档/diff 检查） | implementation 后运行完整矩阵 | future output | Codex | 用户 pending | not-run |

## 数据对账

- 源表/目标表行数：not-run；未创建 E2 数据库。
- source/content digest：not-run；未生成 E2 dump 或 bundle。
- Alembic revision：代码当前 head 为 `20260824_0002`；E2 revision 尚未创建。
- job/attempt/fencing/audit：not-run；现有代码没有通用 durable job 表。
- 差异及处理：准备阶段只记录静态差异，禁止用现有业务库补数。

## 负向与恢复覆盖

- denylist DSN、unknown revision、自动 DDL：待实现/待运行。
- duplicate、lease expiry、heartbeat、旧 fencing token、retry、cancel、DLQ、backpressure：待实现/待运行。
- kill/restart、超时、graceful shutdown、孤儿 job：待实现/待运行。
- manifest 篡改、恢复到已存在目标、restore-forward：待 E2 隔离拓扑批准后运行。
- Chroma generation 重建属于 E5；E2 只预留 SQL schema，不把 Chroma E2E 列为本阶段退出证据。

## 不能证明的内容

- 静态盘点不能证明 MySQL 行锁、`SKIP LOCKED`、事务隔离、lease/fencing、恢复或性能。
- E1 的 MySQL/Chroma 证据不能替代 E2 新 schema/runner 的真实依赖证据。
- SQLite/mock/unit test 不能替代 MySQL 8.4 的并发、DDL 和恢复证据。
- E2 不证明登录、refresh/revocation、业务迁移、RAG 查询、Skill 发布、真实 UI E2E、HA 或生产 RPO/RTO。
