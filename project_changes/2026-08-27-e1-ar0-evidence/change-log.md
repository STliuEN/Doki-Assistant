# E1 变更日志

状态：已关闭

| 时间 | commit/文件/schema | 变更 | 原因 | 影响 | 回滚点 | 负责人 | 证据 |
|---|---|---|---|---|---|---|---|
| 2026-08-27 | `project_changes/2026-08-27-e1-ar0-evidence/` | 建立 E1 计划、变更日志和测试记录 | 用户授权开始 E1，固定真实依赖验证边界 | 新增阶段记录，不触碰业务数据 | 删除本批新增记录；不影响运行状态 | Codex | `plan.md`、`test-record.md` |
| 2026-08-27 | Git/主机/Docker 基线 | 固定 branch、HEAD、脏工作树和工具版本 | 保证命令可复现且不把历史改动归入 E1 | 只读检查 | 无需回滚 | Codex | `test-record.md` 的 `E1-00-baseline` |
| 2026-08-27 | `backend/app/rag/vector_store.py` | 增加 Chroma 持久目录只读 preflight、collection/迁移兼容性校验、quarantine 状态和重启边界 | 防止损坏或部分 projection 在构造客户端时被隐式迁移/重建 | Chroma projection 失败闭环为 `ChromaProjectionUnavailable`；健康目录不被覆盖 | 恢复本文件并重启应用；不删除原 projection | Codex | `tests/test_chroma_containment.py`、`artifacts/logs/chroma-rebuild-attempt2.json` |
| 2026-08-27 | `backend/app/core/failed_response_register.py`、`backend/app/router/knowledge_router.py`、`backend/app/router/chat.py` | 统一 Chroma 故障 HTTP 503 envelope；stream/config mutation 在开始前 preflight；OpenAPI 声明 503 | 让查询/写入失败可诊断且 fail-closed | Chroma 不可用时不启动流、不确认成功；source list 保持独立 | 恢复路由和 handler 变更并重新生成 OpenAPI | Codex | `tests/test_chroma_http_containment.py`、`backend/openapi.json` |
| 2026-08-27 | `backend/tests/test_chroma_http_containment.py` | 新增 13 条 Chroma 相关 route 的 503、source list 例外和 OpenAPI containment 测试 | 固定 API 错误合同，覆盖非流式和流式路径 | 定向测试 30 passed（与 Chroma containment suite 合并运行） | 删除新增测试文件 | Codex | `backend/tests/test_chroma_http_containment.py` |
| 2026-08-27 | E1 隔离 MySQL `doki-e1-20260827-*` | 使用 MySQL 8.4.11 合成数据执行 dump、manifest、恢复、restore-forward 和 digest 对账 | 补齐 AR-0 真实依赖与恢复证据，不连接现有业务库 | 3 行基线恢复一致；restore-forward 后 4 行源/恢复 digest 一致 | 从只读 `mysql-bundle` 恢复到新的隔离目标 | Codex | `artifacts/logs/mysql-recovery-summary.json` |
| 2026-08-27 | E1 隔离 Chroma 目录与备份 | 执行真实写入/查询、损坏、ACL、迁移 hash、collection 缺失、重启、rebuild/quarantine | 验证 projection 可重建且失败不覆盖健康目录 | 健康语义 digest 一致；五类故障 quarantine/fail-closed；重启后 ready | 从只读 `chroma-bundle` rebuild 到新的 `fault-*` 目标 | Codex | `artifacts/logs/chroma-rebuild-attempt2.json` |
| 2026-08-27 | Storage/Chroma tamper bundles | 修改 payload 后尝试恢复 | 验证 manifest/digest 篡改不会创建目标 | 两种恢复均 exit 1，错误为 `backup payload does not match manifest`，目标不存在 | 删除隔离 tamper 副本；健康 bundle 未修改 | Codex | `artifacts/tamper-rejection/` |
| 2026-08-27 | `threat-model.md`、`characterization-matrix.md`、`platform-limitations.md` | 补齐资产/威胁、API/UI/Prompt/route 表征和跨平台限制 | 记录替身、真实依赖、未运行项和责任边界 | 只新增证据文档，不改变运行权威 | 删除本批文档；不影响代码或数据 | Codex | 三份 E1 文档 |
| 2026-08-27 | `benchmarks/cases/*.yaml`、`backend/tests/test_benchmark_runner.py`、`benchmarks/README.md` | 为显式工具 fixture 绑定最小授权 Skill，并增加生产解析合同测试 | benchmark 必须服从与生产相同的 Skill 授权上界 | 不放宽生产授权，不允许 `tool_ids` 成为独立授权源；smoke/regression 恢复全绿 | 恢复本批 fixture、测试和说明；生产授权代码未改 | Codex | `benchmarks/results/20260827-e1-final-isolated-*` |
| 2026-08-27 | `backend/app/skills/seed.py`、`benchmarks/runners/harness.py`、`benchmarks/runners/run_benchmarks.py`、`backend/app/core/logger_handler.py` | 为离线 snapshot 注入结果目录 Storage，并在导入 harness 前把 benchmark 日志根目录指向结果目录 | 首次全绿 benchmark 仍更新默认 `staging` 和应用日志，未满足隔离阈值；全新环境也不能先创建默认日志文件 | 默认生产行为不变；offline runner 的 seed ZIP/日志仅写结果目录；完整 pytest 与 benchmark 四类资源监控不变 | 恢复四处文件；结果目录可丢弃，默认 Storage 对象未修改 | Codex | `benchmarks/results/20260827-e1-final-isolated-*`、`test-record.md` |
| 2026-08-27 | `backend/conftest.py`、`backend/tests/test_api_contracts.py` | pytest 收集前隔离外部服务/持久化路径/日志；CORS 预检不再启动 lifespan | 防止合同测试读取 `.env` 后连接本机服务或探测真实 Storage | 当前完整 pytest `284 passed`；受保护 Chroma、Skill Storage、对象 ZIP 和应用日志在最终复跑中未变化 | 恢复两处测试文件；不涉及生产 migration 或 schema | Codex | `test-record.md` 的 `E1-09d-final-isolated-pytest` |
| 2026-08-27 | 测试/benchmark 隔离事故审计 | 记录无隔离 pytest 误连 `localhost:3306`/已配置 Redis、CORS 失败复现触发 Storage probe，以及首次全绿 benchmark 触碰默认 Storage/日志 | 无效绿色结果和资源误触不得隐藏或作为最终隔离证据 | 未再查询业务库；不能绝对证明数据库/Redis 零写入；对象 ZIP 与 Chroma 未变化，`staging` 和应用日志最终误触时间为 `2026-08-27 16:09:33` | 审计事实不可回滚；后续 pytest/benchmark 均强制隔离 | Codex | `backend/logs/agent_20260827.log`、`test-record.md` |
| 2026-08-27 | E1 阶段状态与活计划记录 | 用户明确要求确认关闭 E1 并更新相关记录；将 E1/AR-0/SK-0 从 `待验证` 转为 `已关闭`，下一阶段 E2/AR-1 标为 `待你确认` | 满足阶段状态机的用户关闭确认要求，同时防止关闭 E1 被误解为自动实施 E2 | 仅更新阶段与交接文档；不启动 E2、不执行 migration、不清理 E1 容器/volume/network/证据 | 文档状态可通过 Git 回退；技术证据和事故事实保持不变 | Codex；批准人：用户 | `plan.md`、`test-record.md`、`docs/architecture_rewrite_plan.md` |
| 2026-08-28 | E1 后续阶段归属勘误 | 将“真实业务 UI E2E 整体移交 E2”更正为 E2 schema/runner/recovery、E3 认证、E4 业务写入、E5 RAG 成功流 | 防止 E2 准备阶段越权实施认证、业务迁移或 RAG | 只修正后续阶段归属；E1 证据、关闭结论和未执行事实不变 | 恢复相关说明文字 | Codex | E2 计划审阅；`plan.md`、`platform-limitations.md`、`characterization-matrix.md`、`threat-model.md` |

## 明确未做

- 未执行项目 Alembic/Django migration、统一 schema、UoW、durable runner、认证接管或业务数据迁移；E2/AR-1 尚未获得实施确认。
- 除已登记的 pytest 隔离事故外，未连接、修改或删除现有业务 MySQL、Redis、Storage、文件、MD5 sidecar、`backend/data/chromadb` 或历史归档。事故中不能绝对证明数据库/Redis 零写入；未继续查询业务库，且未回滚被更新的 Storage 目录时间戳。
- 未下线 Django/Redis、删除旧 adapter、执行 C 级 Skill、解冻工作包 `7-10` 或声称 `SKILL-GATE`/`ARCH-GATE` 通过。
- benchmark fixture 只补充最小授权 Skill；未修改生产 Skill/Tool 授权、未让 harness 自动补 Skill，也未允许显式 `tool_ids` 绕过授权。
- 未宣称真实 LLM/Embedding/Reranker 质量、原生 Linux/macOS、Chrome/Chromium、HA、高并发或生产 RPO/RTO 已验证；Linux/macOS 支持范围已冻结。
