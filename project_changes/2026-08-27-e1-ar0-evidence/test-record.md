# E1 测试与迁移证据

状态：已关闭

## 关闭确认

2026-08-27，用户在审阅 E1 技术结果、事故边界和未覆盖项后明确确认关闭 E1。本确认接受本文件记录的 E1 范围证据，不把历史失败或误连结果改写为有效证据，也不声称真实模型质量、真实目标 schema UI E2E、AR-1 durable runner、AR-2 授权审计或后续发布门禁已经通过。E2/AR-1 仅进入 `待你确认`，未在本批启动。

## 环境限制

- 主机：Microsoft Windows 11 专业版 64-bit build 26100，PowerShell 5.1。
- 运行时：Python 3.12.3、uv 0.8.17、Docker Desktop 4.77.0 / Engine 29.5.3（Linux/amd64）。
- 前端：Node 22.20.0、npm 10.9.3；最终门禁通过绝对 `C:\\nvm4w\\nodejs\\node.exe` 调用；默认 PowerShell PATH 不含 node/npm。
- 浏览器：Playwright Firefox 1539；本机没有 Chrome/Chromium，因此浏览器证据不外推到 Chrome。
- Git：分支 `ai_document_assistant`，HEAD `d0b882683111adee4d6edfcec4d085cadf14a42a`；开始时存在用户保留的文档归档脏工作树，本批未清理。
- MySQL/Chroma/模型拓扑：隔离真实 MySQL 和真实 Chroma 已运行；向量使用确定性 Embedding 测试桩；真实 LLM/Embedding/Reranker 质量未运行。
- 保护边界：E1 隔离依赖演练未接既有业务资源；但一次未隔离的完整 pytest 在 `2026-08-27 15:39:54 +08:00` 读取 `backend/.env` 后连接了本机 `localhost:3306` 和已配置 Redis，该次绿色结果无效。CORS 失败复现和一次 benchmark 复跑还触碰了默认 Skill Storage；事故、证据限制和修复见下节。最终接受的 pytest/benchmark 验证均使用隔离资源。

## 隔离拓扑

| 组件 | 资源 | 版本/端口/路径 | 责任边界 |
|---|---|---|---|
| MySQL 源 | `doki-e1-20260827-mysql` | `mysql:8.4`，解析 8.4.11，`127.0.0.1:33307 -> 3306`，volume `doki-e1-20260827-mysql-data`，DB `doki_e1` | E1 合成业务数据，仅 loopback |
| MySQL 恢复 | `doki-e1-20260827-mysql-restore` | 8.4.11，`127.0.0.1:33308 -> 3306`，volume `doki-e1-20260827-mysql-restore-data`，同一 E1 network | 只接受本批 bundle 恢复 |
| Chroma | E1 `artifacts/chroma/*` | 项目锁定 Chroma 运行库；独立持久目录、`rag_collection` + `notes_collection` | 可重建 projection，不是业务权威 |
| 备份 | `artifacts/backups/*` | MySQL dump、Storage tree、Chroma projection manifest | 每个 payload 先做 SHA-256 校验 |

## 资源收尾

2026-08-27 12:47（UTC+08:00）已执行 `docker stop doki-e1-20260827-mysql doki-e1-20260827-mysql-restore`，两个容器均以 `Exited (0)` 结束。`doki-e1-20260827-mysql-data`、`doki-e1-20260827-mysql-restore-data` volume 和 `doki-e1-20260827-net` network 保留用于审阅/恢复；`33307`、`33308`、`18080` 均无监听。E1 Vite、Playwright daemon 和 Firefox 测试进程已停止；`.playwright-cli/` 截图/快照和本批证据目录未删除。

## 测试隔离事故与修复

1. 原 CORS 合同用例使用 `with TestClient(app)`，因此启动完整 lifespan。最初在不满足 schema 的环境得到 `280 passed, 1 failed`，该失败证明一个纯 CORS 中间件合同被错误绑定到数据库启动条件。
2. 随后一次未设置隔离变量的 `cd backend; uv run pytest -q` 读取 `backend/.env`，连接了本机 `localhost:3306` 和已配置 Redis。输出虽为 `282 passed`，但日志出现 `Database schema revision verified`、`Standard Skill registry initialized: installed=0 revision=1 skills=10`、数据库会话/Redis/后台模型初始化与正常关闭，因此该结果标为 **无效，不作为 E1 证据**。
3. 不再查询业务库确认副作用。`installed=0` 和现有代码路径不足以绝对证明数据库或 Redis 零写入；本记录不作该声明。`backend/data/chromadb` 最新时间仍为 `2026-08-24 21:24:27 +08:00`，Skill 对象 ZIP 最新时间仍为 `2026-08-24 17:46:46 +08:00`，没有发现这两类持久对象被改写。
4. 用 `MYSQL_HOST=127.0.0.1`、`MYSQL_PORT=33309` 单独复现原 CORS 用例时，lifespan 先执行 Storage 可写探针，随后因 MySQL 无监听失败；`backend/data/skill_packages/staging` 目录时间被更新为 `2026-08-27 15:48:50 +08:00`。该时间戳不回滚、不隐藏；探针临时文件已由生产逻辑自行删除，对象 ZIP 未变化。
5. 修复：`backend/conftest.py` 在任何应用导入前把 MySQL、Redis、JWT Redis、Django API 指向不可连接 loopback，把 Skill Storage、Chroma、知识文件、MD5 sidecar 和测试日志指向 `TemporaryDirectory`；CORS 用例改用不启动 lifespan 的 `TestClient` 请求/显式关闭。
6. 修复过程第一次运行因 pytest hook 参数名写成 `_session/_exitstatus`，在收集前被 Pluggy 拒绝，未执行测试且三项监控未变化；改成规范参数名后继续验证。前端最初经 `npm.cmd` 调用时因 PATH 中没有 `node` 而未启动 Vitest/ESLint；最终改用绝对 `node.exe` 入口，测试、lint、build 均通过。
7. `2026-08-27 16:09:19 +08:00` 的 benchmark 复跑已将 MySQL/Redis 指向不可连接端口，行为结果为 smoke `4/4`、regression `117/117`，但 `build_seed_runtime_snapshot()` 仍使用全局 Skill Storage，且 runner 仍写应用日志；`staging` 目录和 `backend/logs/agent_20260827.log` 时间更新为 `16:09:33`。该轮结果只证明行为，不满足隔离证据；Skill 对象 ZIP 和 Chroma 未变化。
8. benchmark 修复：seed snapshot 接受显式 `SkillPackageStorage`；harness 将 10 个 seed ZIP 暂存在每个结果目录的 `.runtime/skill_packages`；runner 将文件日志写入同目录的 `benchmark.log`。最终复跑 smoke `4/4`、regression `117/117`，且真实 Chroma、Skill `staging`、全部 Skill 对象 ZIP 元数据和应用日志前后均未变化。

## 证据表

| ID | 环境/版本 | 拓扑 | fixture/真实依赖 | 命令/动作 | 阈值 | 实际结果 | 日志/文件 | owner | approver | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|
| `E1-00-baseline` | Windows 11；Git；Docker | 当前工作树 + Docker | 只读盘点 | `git rev-parse/status`、系统版本、`docker version/ps/volume/network` | HEAD 固定；E1 资源可识别；保留既有脏工作树 | HEAD 固定；启动前无 E1 容器/volume/network；既有资源未改 | 本文件、`plan.md` | Codex | 用户 | verified-local |
| `E1-01-topology` | Docker Engine 29.5.3；MySQL 8.4.11 | 两个 loopback MySQL 容器 + E1 network；独立 Chroma 路径 | 真实服务 + 合成数据/确定性向量 | `docker inspect/exec`；`chroma_live_probe.py seed/verify/inspect-sqlite` | 版本、端口、路径、collection、责任边界明确 | MySQL/Chroma 资源均只在 E1 名称和路径；Chroma `rag=3`、`notes=1` | `artifacts/logs/mysql-recovery-summary.json`、`artifacts/logs/chroma-rebuild-attempt2.json` | Codex | 用户 | verified-live |
| `E1-02-p0-rerun` | Python 3.12.3；uv lock | 当前工作树；SQLite/TestClient/隔离 fixture | P0-1 至 P0-5 fixture + 真实 E1 probe | `uv run pytest -q tests/test_backup_restore.py tests/test_chroma_containment.py tests/test_chroma_http_containment.py`；全仓 Ruff/OpenAPI/lock；前端 test/lint/build | 定向 containment 30 passed；静态检查和前端构建 exit 0 | Chroma containment 合并 30 passed；前端 6 files/28 passed、lint/build 通过；Ruff、OpenAPI、`uv lock --check` 通过 | `backend/tests/`、`backend/openapi.json`、本文件 | Codex | 用户 | verified-local |
| `E1-03-mysql-recovery` | MySQL 8.4.11 | 源 `33307` -> 恢复 `33308` | 真实隔离服务 + 合成 SQL | 隔离 `mysqldump`/`mysql` 导入；manifest verify；行数/digest；应用 `artifacts/mysql/forward.sql` 后再对账 | 基线 dump/restore 一致；restore-forward 源/恢复一致 | 基线 3 行，row digest `da95ff109088d5b50ea08cb1a81efabed63136e6426a174bbcc37e835401d327`；最终 4 行，双方 digest `0f44325e701a5f9ae562494a386dec056b0b5441e7bae66aaa6e0de1408b1709` | `artifacts/logs/mysql-recovery-summary.json`；bundle digest `69c5f4e3bcfc1856508268d8897c03a6e54e2a9208b407799a981998b964033a` | Codex | 用户 | verified-live |
| `E1-04-chroma-live` | Chroma 真实运行库；确定性 Embedding | E1 独立持久目录 | 真实 Chroma 写入/查询/重启 | `chroma_live_probe.py seed/verify/copy/service-init`；fresh interpreter restart | collection/count/ID/content/query/health 一致 | `rag_collection=3`、`notes_collection=1`；ID digest `553fb7ddc7df167a7be6713745a4ab1b57dd5af66f8453e4782dfc0c27335db2`；content digest `372c112fa4b57ede204505397170ae040ec1aada11c04f6ea13fdc9c5e9ef092`；query `alpha document`；health `ready` | `artifacts/logs/chroma-rebuild-attempt2.json`、`artifacts/backups/chroma-bundle/manifest.json` | Codex | 用户 | verified-live |
| `E1-05-chroma-faults` | Windows ACL + Chroma SQLite | `fault-*` 副本与 quarantine 目录 | 真实 Chroma 故障注入 | 损坏 SQLite、ACL deny-read、迁移 hash mismatch、删除 `rag_collection`、首次初始化失败；随后显式恢复 | 每个故障 quarantine/fail-closed；失败路径不改变故障副本或健康快照；恢复 ready | 五类故障均 quarantine；错误包含 `file is not a database`、`[WinError 5]`、migration hash mismatch、missing collection；健康快照前后 digest 相同；损坏 quarantine digest `c08d20a705927b321a8110acd8817015577b6b6cfe8a9032829079ca4a32e5ac` | `artifacts/logs/chroma-rebuild-attempt2.json` | Codex | 用户 | verified-live |
| `E1-06-rebuild-and-tamper` | Python 3.12.3；E1 bundle | 新 `fault-*` 目标；不接现有 projection | 真实 Chroma projection + Storage/Chroma manifest | `backup_restore.py verify/restore/rebuild-projection`；篡改 payload 后重复恢复 | manifest mismatch exit 1；新目标不创建；健康目录不覆盖 | Storage、Chroma 恢复均 exit 1，错误 `backup payload does not match manifest`；`fresh_target_exists=False`；合法 rebuild 后 quarantine 旧副本，安装快照与 manifest 一致 | `artifacts/tamper-rejection/`、`artifacts/logs/chroma-rebuild-attempt2.json`；Chroma bundle digest `6774c829580a9d217c6a4c5b94177201aefa0859cdb12e0ae7188453b8644896` | Codex | 用户 | verified-local |
| `E1-07-api-ui-characterization` | FastAPI TestClient；Node 22.20.0/npm 10.9.3；Firefox | API route doubles + Vite `127.0.0.1:18080`；Skill UI mock API | 当前代码合同、fixture/mock、浏览器本地表征 | `tests/test_chroma_http_containment.py`；Playwright login/register/skills snapshot/screenshot；前端 Vitest/lint/build | 503 envelope 稳定；source list 可独立 200；页面可加载；无 JS error | 13 条 Chroma 相关 route 返回统一 503；`/knowledge/list` 例外 200；login/register 可渲染；注册代理 `POST /user/register/ -> 502` 显示“注册失败，请重试”；mock SkillManager 可渲染 | `characterization-matrix.md`、`platform-limitations.md`、`.playwright-cli/page-*.yml/.png` | Codex | 用户 | verified-local |
| `E1-08-static-contracts` | Python 3.12.3；当前工作树 | source tree only | static/contract checks | `uv run ruff check main.py app tests scripts`；`uv run python scripts/export_openapi.py --check`；`uv lock --check`；`powershell -File scripts/check-docs.ps1`；`git diff --check` | exit 0；OpenAPI 无 drift；文档无断链 | 全仓 Ruff、OpenAPI、uv lock、diff check 通过；文档 `174 files, 145 local links` 通过 | 本文件、`backend/openapi.json`、`scripts/check-docs.ps1` 输出 | Codex | 用户 | verified-local |
| `E1-09-full-pytest` | Python 3.12.3；主应用 lifespan | 当前工作树；真实 lifespan 需要 DB schema | 完整 pytest（含 fixture） | `cd backend; uv run pytest -q` | 0 failures；schema gate 可解释且不执行 migration | **历史失败，保留不覆盖**：`280 passed, 1 failed`；唯一失败为 CORS 用例错误启动 lifespan 后被 required revision `20260824_0002` 阻断 | pytest 输出；`backend/app/db/db_config.py` | Codex | 用户 | historical-failed |
| `E1-09a-isolation-incident` | Python 3.12.3；`.env` + 本机服务 | `localhost:3306`、已配置 Redis、默认 Storage | 未隔离的完整 pytest | `cd backend; uv run pytest -q` | 不得连接既有资源 | 输出 `282 passed`，但 15:39:54 日志证明 lifespan 已连接本机资源；结果无效，数据库/Redis 是否零写入无法证明且不再查询 | `backend/logs/agent_20260827.log`；本节事故记录 | Codex | 用户 | invalid-not-evidence |
| `E1-09b-isolation-reproduction` | Python 3.12.3；无监听 MySQL | `127.0.0.1:33309` + 默认 Storage | 原 CORS 用例的隔离复现 | `$env:MYSQL_HOST='127.0.0.1'; $env:MYSQL_PORT='33309'; uv run pytest -q tests/test_api_contracts.py::test_skill_import_idempotency_header_is_allowed_by_cors` | CORS 合同不应启动 lifespan | `1 failed`；Storage 探针先执行，`staging` 目录时间更新为 15:48:50，随后 schema 连接失败；证明测试边界错误 | pytest 输出；本节事故记录 | Codex | 用户 | audited-failed |
| `E1-09c-isolated-pytest` | Python 3.12.3；pytest 临时根目录 | loopback 端口 `1`；临时 Storage/Chroma/知识/日志 | 完整隔离 pytest | `cd backend; uv run pytest -q` | 0 failures；受保护目录/日志不变；不启动不需要的 CORS lifespan | CORS 定向 `1 passed`；完整 `282 passed in 20.54s`；最终复跑前后 `backend/data/chromadb`、`backend/data/skill_packages/staging`、`backend/logs/agent_20260827.log` 的时间和长度均未变化 | `backend/conftest.py`、`backend/tests/test_api_contracts.py` | Codex | 用户 | verified-local |
| `E1-09d-final-isolated-pytest` | Python 3.12.3；当前代码 | pytest 临时根目录 + benchmark 隔离实现 | 完整隔离 pytest | `cd backend; uv run pytest -q` | 当前代码 0 failures；Chroma/默认 Storage/对象 ZIP/应用日志不变 | `284 passed in 21.03s`；四类受保护资源前后全部不变 | pytest 输出；`backend/conftest.py` | Codex | 用户 | verified-local |
| `E1-10-benchmark` | Python 3.12.3；offline harness | scripted model + fixture-backed tool data；无真实 MySQL/LLM | smoke/regression offline benchmark | `uv run python ..\\benchmarks\\runners\\run_benchmarks.py --suite smoke --offline --fail-under 0.9`；`--mode offline --tag regression --fail-on-veto` | smoke/regression 应无未解释 error；Tool policy 与 Skill grant 一致 | **历史失败，保留不覆盖**：smoke `3/4`、平均 0.75；regression `78/117`、平均 0.6667；39 个授权 fixture 冲突 | 原 benchmark 输出；`plan.md` | Codex | 用户 | historical-failed |
| `E1-10a-benchmark-contract` | Python 3.12.3；offline harness | 显式工具 + 最小授权 Skill；生产 `resolve_skills` | 授权修复后的首次全绿复跑 | 合同单测；smoke/regression 显式设置不可连接 MySQL/Redis；输出到 `20260827-e1-final-*` | 不放宽授权、不自动补 Skill；零 error/veto；删除不执行；不得触碰默认 Storage/日志 | 合同 `1 passed`；smoke `4/4`、regression `117/117`、平均分 `1.0`，但默认 `staging` 和应用日志时间更新到 16:09:33，隔离阈值未达 | `benchmarks/results/20260827-e1-final-*`；本节事故记录 | Codex | 用户 | behavior-passed-isolation-failed |
| `E1-10b-isolated-benchmark` | Python 3.12.3；offline harness | 结果目录内 runtime Storage/日志；不可连接 MySQL/Redis | 最终隔离 benchmark | smoke/regression 原命令，输出到 `20260827-e1-final-isolated-*` | 不放宽授权；零 error/veto；删除不执行；四类受保护资源不变 | smoke `4/4`、regression `117/117`；均平均分 `1.0`、零 error/硬 veto；每个结果有 10 个 runtime seed ZIP 和独立日志；四类监控全部不变 | `benchmarks/results/20260827-e1-final-isolated-smoke/20260827-163011/`、`benchmarks/results/20260827-e1-final-isolated-regression/20260827-163024/` | Codex | 用户 | verified-local |
| `E1-11-cross-platform` | Windows 主机 + Docker Linux 内核 | Windows 11 是唯一正式支持主机 | 平台边界记录 | 复核 Windows ACL、路径/symlink fixture 和浏览器运行时 | Windows/Docker 结论已记录；原生 Linux/macOS 不设门禁 | Windows 证据有效；原生 Linux/macOS 标为 `out-of-scope/frozen`；Chrome/Chromium 仍为 not-run 且不由 Firefox 结果代替 | `platform-limitations.md` | Codex | 用户 | scoped-complete |
| `E1-12-final-gates` | Python 3.12.3；Node 22.20.0 | source tree + 绝对 Node 入口 | 最终静态/前端回归 | Ruff、OpenAPI `--check`、`uv lock --check`、文档检查、Vitest、ESLint、TypeScript/Vite build、`git diff --check` | 全部 exit 0；无 OpenAPI drift/断链 | Ruff/OpenAPI/lock 通过；关闭记录更新后文档 `177 files, 154 local links`；前端 `6 files/28 passed`、lint/build 通过；最终 `git diff --check` 通过 | 本文件、命令输出 | Codex | 用户 | verified-local |

## 数据对账

- MySQL bundle manifest content digest：`69c5f4e3bcfc1856508268d8897c03a6e54e2a9208b407799a981998b964033a`；dump/source/restored SQL digest 均为 `fd3c0f86215d41bf2187fd77b2904f35709cd15c681ce395cf81384606c2cb06`。
- MySQL：基线 3 行，digest `da95ff109088d5b50ea08cb1a81efabed63136e6426a174bbcc37e835401d327`；restore-forward 后 4 行，源/恢复 digest 均为 `0f44325e701a5f9ae562494a386dec056b0b5441e7bae66aaa6e0de1408b1709`。
- Chroma bundle digest：`6774c829580a9d217c6a4c5b94177201aefa0859cdb12e0ae7188453b8644896`；健康语义为 `rag_collection=3`、`notes_collection=1`；ID digest `553fb7ddc7df167a7be6713745a4ab1b57dd5af66f8453e4782dfc0c27335db2`；内容 digest `372c112fa4b57ede204505397170ae040ec1aada11c04f6ea13fdc9c5e9ef092`。
- Storage bundle content digest：`48de077343fa6cb5ea232689b9d5a8f485b45be7f488d7b778684b31ecb716b5`；源/恢复 catalog 均为 `installed_disabled` 的 E1 合成包。
- Chroma generation/active pointer：当前实现没有最终 generation 表；E1 只证明隔离 projection、quarantine 和重启语义，不宣称 AR-4 generation 完成。
- 审计事件/correlation ID：E1 操作以证据 ID 和日志文件关联；统一 SQL 审计字段属于 AR-2，未在本批实现。
- 差异处理：真实隔离数据无行数/digest 差异；旧 pytest/benchmark 失败与误连结果完整保留，新隔离结果独立追加。原生 Linux/macOS 已冻结在支持范围外；真实模型质量仍为 `not-run/non-blocking`，不通过改数据或放宽授权掩盖。

## 负向与恢复覆盖

- Chroma：损坏、权限、迁移版本不兼容、collection 缺失、进程 restart、初始化失败、活动客户端 retarget、配置外目标、manifest 篡改；失败后原目录/健康快照未覆盖，查询/API 统一 `degraded/503`。
- Storage/backup：manifest 文件 digest、payload 篡改、路径穿越、盘符/UNC、symlink、额外条目和已存在目标均 fail-closed。
- Skill/Tool：显式 Skill unknown/private/disabled、工具授权上界、revision/digest binding、高风险 confirmation；完整真实撤销/过期/角色分离等待 AR-2。
- 进程/任务：Chroma 新解释器重启通过；runner kill/restart、lease/fencing/retry/DLQ 属于 AR-1/E2，本阶段禁止实现或声称验证。
- 备份/恢复：MySQL dump/restore/restore-forward、Chroma rebuild/quarantine、Storage/Chroma tamper rejection 均已演练；生产 RPO/RTO 数值未测量。

## 不能证明的内容

- fixture、mock、TestClient、确定性 Embedding 和 scripted model 只能证明代码合同、错误边界和数据完整性逻辑，不能证明真实 LLM/Embedding/Reranker 质量、吞吐或外部服务可用性。
- Windows 主机与 Docker Linux 内核不能证明原生 Linux/macOS、Chrome/Chromium、HA、多实例、公网和高并发；其中 Linux/macOS 支持范围已明确冻结，不设门禁。
- 当前 E1 没有实现最终 SQL schema、generation、统一授权审计或 durable runner，因此不能替代 AR-1 至 AR-6 门禁。
- Playwright 的真实浏览器证据只覆盖 Vite 页面和 mock/代理失败表征；注册 502 不是业务注册成功或真实后端 E2E 证据。
