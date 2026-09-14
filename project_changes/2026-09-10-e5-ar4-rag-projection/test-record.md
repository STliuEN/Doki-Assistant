# E5 测试与迁移证据

状态：实施中

## 环境与证据边界

- 准备前基线：`a2d7381` (`e4结束`)，工作树干净。
- 本轮范围：文档、代码和本地工具的只读核验，以及准备文档编辑。
- E4 关闭和恢复数据作为 historical 输入记录；未重新连接 SQL、打开 Chroma 或调用模型。
- E5 实施、真实依赖测试与验收尚未开始。未运行命令不能写为 verified。

## 准备证据

| ID | 环境/版本 | 拓扑 | 证据类型 | 命令 | 阈值 | 实际结果 | 结果/处置 | 日志/文件 | owner | approver | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| E5-P01 | Git HEAD a2d7381 | 本地仓库 | 静态/历史对照 | git status --short; git log -5; 读取 E4 closure 与主文档（分别执行） | 关闭记录可追溯、基线明确 | 工作树准备前干净；E4 closure 明确 closed/follow_on_stages not_activated；主文档仍写实施中 | passed；本轮同步状态 | ../2026-09-02-e4-ar3-business-migration/artifacts/e4-closure-20260910.json；本轮 diff | Codex | 用户待审阅 | verified-local |
| E5-P02 | 仓库文件 | 无运行依赖 | 静态审查 | rg / Get-Content | 目标、实现、测试、环境和未决设计分开记录 | plan.md 记录审查与任务；首次审查时 Q1-Q3 待答复，后续确认见 E5-P05 | passed；不代表实现完成 | plan.md | Codex | 用户待审阅 | verified-local |
| E5-P03 | Markdown / Git | 本地仓库 | 文档检查 | ./scripts/check-docs.ps1；git -c core.autocrlf=false diff --check；rg 检查新增文档行尾空格（分别执行） | 本地链接和代码围栏有效、diff 无错误 | 199 Markdown 文件 / 205 本地链接通过；diff 检查 exit 0；新增文档无行尾空格 | passed；首次发现交接手册新增行的 Markdown 行尾双空格，已修正并复跑通过 | scripts/check-docs.ps1 输出；本轮 diff | Codex | 用户待审阅 | verified-local |
| E5-P04 | Python 3.12.3 / uv 0.8.17 / Chroma 1.5.9 | 本地工具与 Docker/端口元数据 | 只读环境观察 | venv python -I -S --version、uv --version、importlib.metadata、Get-Command、Docker 元数据与监听端口检查 | 明确运行工具来源和当前依赖状态 | venv 和锁定包元数据可用；E4 target/restore/Redis Exited (255)，应用与 Ollama 无监听 | passed；runtime/模型推理仍未验证 | plan.md 第 7.1 节 | Codex（独立只读核验） | 用户待审阅 | verified-local |
| E5-P05 | 2026-09-10 会话答复/文档 | 无运行依赖 | 决策与文档对照 | 对照用户 Q1-Q3 答复及主文档；运行 ./scripts/check-docs.ps1、git -c core.autocrlf=false diff --check 及新增文档行尾空格检查 | 已回答项不再标待答复；日常可用性/停写等未回答项不推定 | Q1/Q2 按建议，Q3 首次全量迁移不保旧访问；Q4-Q7 待答复；199 文件/205 链接通过，diff exit 0，无新增行尾空格 | passed；只验证文档和已收到的决策，不代表迁移完成 | plan.md 第 4 节与本轮 diff | Codex | 用户已确认 Q1-Q3 | verified-local |
| E5-P06 | 2026-09-14 会话答复/文档 | 无运行依赖 | 决策与文档对照 | 对照用户 Q1-Q7 答复及本计划；运行文档/diff 检查 | Q1-Q7 已明确，计划进入实施中，未把设计决策当作代码证据 | Q1-Q7 全部按建议确认；Q4 停写，Q5 成组开放，Q6 失败阻断，Q7 重建 503 | passed；实施授权已收到，代码和真实依赖尚未验证 | plan.md 第 4 节与本轮 diff | Codex | 用户已确认 Q1-Q7 | verified-local |

## 实施证据矩阵

| ID | 对应任务 | 环境 | 必须证明 | 阈值 | 当前状态 |
|---|---|---|---|---|---|
| E5-V01 | E5-01/02 | 真实 MySQL 独立恢复目标 | 资源身份、备份恢复、空库与 populated additive migration、FK/唯一 active/revision | 对账差异与孤儿 FK 为零 | not-run |
| E5-V02 | E5-03 | 合同测试 + 真实 Chroma | 正常/空结果/降级 envelope、分数含义、用户隔离和 SQL source 追溯 | 所有必需字段和隔离负例通过 | not-run |
| E5-V03 | E5-04/05 | SQL runner + 独立 Chroma | 重复/乱序、source/config 漂移、删除、cancel、lease/fencing、kill/restart | 错误激活/越权写入/错误清理为零 | not-run |
| E5-V04 | E5-04/05 | 真实故障注入 | Chroma 已写 SQL 未提交、SQL 已激活清理未完成、迁移开始时在途查询/缓存旁路、heartbeat | 迁移期间 RAG 503；新 active 完整可恢复；过期任务不能污染 | not-run |
| E5-V05 | E5-05/08 | 真实 Chroma 测试副本 | 损坏、权限、版本不兼容、缺 collection、重启、embedding 失败 | RAG 稳定降级；核心登录/会话成功；旧输入不变 | not-run |
| E5-V06 | E5-06/08 | 真实 embedding/reranker + 固定样本 | 向量/HyDE/BM25/笔记/rerank，各来源与分支单独观察 | 质量/时间阈值待方案收束后测试前冻结；隔离负例零泄露 | not-run |
| E5-V07 | E5-07 | API/SSE + 浏览器 | accepted/queued/active/failed、迁移期间 503、配置生效、刷新恢复；查询配置不入重建队列 | UI 与 SQL job/generation 一致，索引/查询配置分类准确 | not-run |
| E5-V08 | E5-08 | SQL 恢复目标 + 全新 Chroma 目录 | 仅从 SQL 原文/配置全量重建、每用户/index 独立、manifest 对账、运行期旧 generation 回收 | 纳入范围源无遗漏、差异为零，受保护输入摘要不变；失败不回旧 RAG | not-run |
| E5-V09 | E5-08/09 | 后端/前端回归 | 相关及完整测试、Ruff、前端 build、文档/diff | 必需检查全通过，限制明确 | not-run |

实际执行时按阶段模板补齐每条证据的版本、拓扑、精确命令、时间、实际结果、日志、owner/approver。fixture 成功不升级为 verified-live；真实依赖缺失单独登记。

## 不能证明的内容

- E4 的 502 项后端测试、28 项前端测试和本地 Ollama 矩阵不是 E5 的 Chroma/embedding/重建证据。
- 既有 offline benchmark 的 smoke/regression 主要验证 scripted stream、路由和合同，不证明真实 RAG 质量。
- 本轮静态检查不证明当前容器、数据库、模型或服务仍可用，不证明 queued job 可直接消费。
- generation 表或 staging fixture 存在不证明业务路径已接入生命周期，也不证明旧 generation 已安全回收。
- 当前 Redis 不可用会通过既有限流使部分 HTTP 请求返回 503；E5 的 Chroma 故障隔离测试需固定 Redis 健康基线，不能把这类 503 混记为 Chroma 造成的核心业务回归。移除 Redis 依赖仍属 E8。

## 2026-09-14 Local implementation checks

| ID | Command / scope | Result | Status |
|---|---|---|---|
| E5-L01 | `backend/.venv` Ruff + compileall | All app/tests checks passed; Python modules compiled | verified-local |
| E5-L02 | `ENV=test E5_RAG_ENABLED=true` import smoke | Required schema revision resolved to `20260914_0009_e5_rag_runtime`; E5 modules imported | verified-local |
| E5-L03 | E5 contract tests | 5 passed: user scope gate, building block, manifest drift, global read-only SQL rejection | verified-local |
| E5-L04 | E2/E4 regression with E5 disabled | 40 passed, including the E5 contract suite | verified-local |
| E5-L05 | Live MySQL/Chroma/embedding/runner/UI E2E | Not connected, migrated, started, or consumed in this round | not-run |

The implementation contains no MySQL global `read_only`, full-database lock, host write freeze, or connection privilege change. The E5 gate is bound to the authenticated user's application SQL write paths.

| E5-L06 | Frontend Vitest | 28 passed in 6 files | verified-local |
| E5-L07 | Frontend TypeScript/Vite build | Production build passed | verified-local |
| E5-L08 | Chroma HTTP containment regression | 15 passed; stable 503 contract preserved | verified-local |
