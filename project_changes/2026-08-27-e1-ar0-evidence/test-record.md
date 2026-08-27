# E1 测试与迁移证据

状态：待验证

## 环境限制

- 主机：Microsoft Windows 11 专业版 64-bit build 26100，PowerShell 5.1。
- 运行时：Python 3.12.3、uv 0.8.17、Docker Desktop 4.77.0 / Engine 29.5.3（Linux/amd64）。
- 前端：Node 22.20.0、npm 10.9.3，通过 `C:\\nvm4w\\nodejs` 的任务级 PATH 调用；默认 PowerShell PATH 不含 node/npm。
- 浏览器：Playwright Firefox 1539；本机没有 Chrome/Chromium，因此浏览器证据不外推到 Chrome。
- Git：分支 `ai_document_assistant`，HEAD `d0b882683111adee4d6edfcec4d085cadf14a42a`；开始时存在用户保留的文档归档脏工作树，本批未清理。
- MySQL/Chroma/模型拓扑：隔离真实 MySQL 和真实 Chroma 已运行；向量使用确定性 Embedding 测试桩；真实 LLM/Embedding/Reranker 质量未运行。
- 未连接或未修改：既有 MySQL（尤其 `localhost:3306`）、Redis、Storage、文件/MD5 sidecar、`backend/data/chromadb`、历史归档和用户脏工作树。

## 隔离拓扑

| 组件 | 资源 | 版本/端口/路径 | 责任边界 |
|---|---|---|---|
| MySQL 源 | `doki-e1-20260827-mysql` | `mysql:8.4`，解析 8.4.11，`127.0.0.1:33307 -> 3306`，volume `doki-e1-20260827-mysql-data`，DB `doki_e1` | E1 合成业务数据，仅 loopback |
| MySQL 恢复 | `doki-e1-20260827-mysql-restore` | 8.4.11，`127.0.0.1:33308 -> 3306`，volume `doki-e1-20260827-mysql-restore-data`，同一 E1 network | 只接受本批 bundle 恢复 |
| Chroma | E1 `artifacts/chroma/*` | 项目锁定 Chroma 运行库；独立持久目录、`rag_collection` + `notes_collection` | 可重建 projection，不是业务权威 |
| 备份 | `artifacts/backups/*` | MySQL dump、Storage tree、Chroma projection manifest | 每个 payload 先做 SHA-256 校验 |

## 资源收尾

2026-08-27 12:47（UTC+08:00）已执行 `docker stop doki-e1-20260827-mysql doki-e1-20260827-mysql-restore`，两个容器均以 `Exited (0)` 结束。`doki-e1-20260827-mysql-data`、`doki-e1-20260827-mysql-restore-data` volume 和 `doki-e1-20260827-net` network 保留用于审阅/恢复；`33307`、`33308`、`18080` 均无监听。E1 Vite、Playwright daemon 和 Firefox 测试进程已停止；`.playwright-cli/` 截图/快照和本批证据目录未删除。

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
| `E1-09-full-pytest` | Python 3.12.3；主应用 lifespan | 当前工作树；真实 lifespan 需要 DB schema | 完整 pytest（含 fixture） | `cd backend; uv run pytest -q` | 0 failures；schema gate 可解释且不执行 migration | `280 passed, 1 failed`；唯一失败 `test_skill_import_idempotency_header_is_allowed_by_cors`，因 required revision `20260824_0002` 的主应用启动阻断 | pytest 输出；`backend/app/db/db_config.py` | Codex | 用户 | blocked |
| `E1-10-benchmark` | Python 3.12.3；offline harness | scripted model + fixture-backed tool data；无真实 MySQL/LLM | smoke/regression offline benchmark | `uv run python ..\\benchmarks\\runners\\run_benchmarks.py --suite smoke --offline --fail-under 0.9`；`--mode offline --tag regression --fail-on-veto` | smoke/regression 应无未解释 error；Tool policy 与 Skill grant 一致 | smoke 4 cases：3 passed/1 error，平均 0.75；regression 117 cases：78 passed/39 errors，平均 0.6667；集中于 `skill_tool_selection`/`tool_safety` 的 Skill/Tool 授权 fixture 冲突 | `benchmarks/cases/skill_routing.yaml`、`benchmarks/cases/tool_safety.yaml`、`plan.md` | Codex | 用户 | blocked |
| `E1-11-cross-platform` | Windows 主机 + Docker Linux 内核 | 无原生 Linux/macOS 主机 | 平台边界记录 | 复核 Windows ACL、路径/symlink fixture 和浏览器运行时 | Windows/Docker 结论已记录；原生 Linux/macOS、Chrome/Chromium 为 not-run | `platform-limitations.md` | Codex | 用户 | not-run |

## 数据对账

- MySQL bundle manifest content digest：`69c5f4e3bcfc1856508268d8897c03a6e54e2a9208b407799a981998b964033a`；dump/source/restored SQL digest 均为 `fd3c0f86215d41bf2187fd77b2904f35709cd15c681ce395cf81384606c2cb06`。
- MySQL：基线 3 行，digest `da95ff109088d5b50ea08cb1a81efabed63136e6426a174bbcc37e835401d327`；restore-forward 后 4 行，源/恢复 digest 均为 `0f44325e701a5f9ae562494a386dec056b0b5441e7bae66aaa6e0de1408b1709`。
- Chroma bundle digest：`6774c829580a9d217c6a4c5b94177201aefa0859cdb12e0ae7188453b8644896`；健康语义为 `rag_collection=3`、`notes_collection=1`；ID digest `553fb7ddc7df167a7be6713745a4ab1b57dd5af66f8453e4782dfc0c27335db2`；内容 digest `372c112fa4b57ede204505397170ae040ec1aada11c04f6ea13fdc9c5e9ef092`。
- Storage bundle content digest：`48de077343fa6cb5ea232689b9d5a8f485b45be7f488d7b778684b31ecb716b5`；源/恢复 catalog 均为 `installed_disabled` 的 E1 合成包。
- Chroma generation/active pointer：当前实现没有最终 generation 表；E1 只证明隔离 projection、quarantine 和重启语义，不宣称 AR-4 generation 完成。
- 审计事件/correlation ID：E1 操作以证据 ID 和日志文件关联；统一 SQL 审计字段属于 AR-2，未在本批实现。
- 差异处理：真实隔离数据无行数/digest 差异；pytest schema gate、benchmark fixture、原生平台和真实模型质量保留为阻塞或未运行，不通过改数据掩盖。

## 负向与恢复覆盖

- Chroma：损坏、权限、迁移版本不兼容、collection 缺失、进程 restart、初始化失败、活动客户端 retarget、配置外目标、manifest 篡改；失败后原目录/健康快照未覆盖，查询/API 统一 `degraded/503`。
- Storage/backup：manifest 文件 digest、payload 篡改、路径穿越、盘符/UNC、symlink、额外条目和已存在目标均 fail-closed。
- Skill/Tool：显式 Skill unknown/private/disabled、工具授权上界、revision/digest binding、高风险 confirmation；完整真实撤销/过期/角色分离等待 AR-2。
- 进程/任务：Chroma 新解释器重启通过；runner kill/restart、lease/fencing/retry/DLQ 属于 AR-1/E2，本阶段禁止实现或声称验证。
- 备份/恢复：MySQL dump/restore/restore-forward、Chroma rebuild/quarantine、Storage/Chroma tamper rejection 均已演练；生产 RPO/RTO 数值未测量。

## 不能证明的内容

- fixture、mock、TestClient、确定性 Embedding 和 scripted model 只能证明代码合同、错误边界和数据完整性逻辑，不能证明真实 LLM/Embedding/Reranker 质量、吞吐或外部服务可用性。
- Windows 主机与 Docker Linux 内核不能证明原生 Linux/macOS、Chrome/Chromium、HA、多实例、公网和高并发。
- 当前 E1 没有实现最终 SQL schema、generation、统一授权审计或 durable runner，因此不能替代 AR-1 至 AR-6 门禁。
- Playwright 的真实浏览器证据只覆盖 Vite 页面和 mock/代理失败表征；注册 502 不是业务注册成功或真实后端 E2E 证据。
