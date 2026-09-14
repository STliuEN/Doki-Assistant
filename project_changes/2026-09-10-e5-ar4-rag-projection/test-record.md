# E5 最终测试与迁移证据

状态：`已关闭`；2026-09-14 当前工作树完成 V01–V09。P01–P06、L01–L08、旧 R01–R05 及当时未通过结果原样保存在 [historical test record](./artifacts/history/test-record.md.txt)，不覆盖当前判定。负责人 Codex；用户已授权执行/收口并核定来源，无验收豁免。

## 环境与层次

- Windows、Python 3.12、Chroma 1.5.9、真实 MySQL、Ollama、现有 RTX 5070 Ti/CUDA 和完整本地 reranker；未下载模型。
- 原目标只限定 `127.0.0.1:33427/doki_e4`；破坏性故障、注册/上传、schema 演练均在新副本和新目录。
- 确定性负例使用 SQLite＋真实 Chroma＋合成 embedding；真实模型质量、MySQL 进程和路由故障另外列证据。
- TCP HTTP/Edge 浏览器使用生产 routers 的 scoped FastAPI harness，只在 harness 关闭限流以隔离现有 Redis 不可用。完整 main/Redis/MCP/最终部署未纳入本阶段。
- 公开文件不含凭据、token、SQL dump 或来源正文；题目、来源 ID、分数、摘要、数量和模型指纹保留。

## V01–V09 最终矩阵

| ID | 必须证明 | 本次证据与结果 | 状态 |
|---|---|---|---|
| V01 | 身份、备份、空库/populated 升级、FK/active/revision | [restore](./artifacts/restore-current.json) 41 表 counts/digest 一致；[schema](./artifacts/schema-upgrades.json) 2/2；[audit](./artifacts/final-audit.json) 52 FK 孤儿 0、4 active/0 staging；本轮先备份/preflight 再写入 | verified-live |
| V02 | envelope、分数、用户隔离、SQL 追溯 | query authority/branches/settings 回归；[target smoke](./artifacts/target-smoke.json) 6/6；[faults](./artifacts/faults.json) owner/content/foreign source/tool；[HTTP](./artifacts/http-queued.json) building 503/core 200 | verified-local + live |
| V03 | 乱序、source/config 漂移、删除、cancel、lease/fence | query authority/reconciliation 确定性测试；[lifecycle](./artifacts/lifecycle.json) 4/4，同 job fence 1→2，22.25 秒恢复 ready，过期 generation 已删 | verified-local + live |
| V04 | SQL/Chroma 分裂窗口、线程取消、清理重试、heartbeat | attempt lock/tombstone/reconcile 回归；真实进程在 Chroma build 后暂停并 kill，重启回收；12 秒 lease 持续 heartbeat，同 fence；第二进程 SQL 锁拒绝 | verified-local + live |
| V05 | 损坏/权限/版本/collection/模型故障，核心可用 | [faults](./artifacts/faults.json) 9/9；真实文件 [corrupt](./artifacts/filesystem-corrupt.json)/[permission](./artifacts/filesystem-permission.json) 2/2；503/core 200；修复 job 去重，查询模型故障无误重建 | verified-live |
| V06 | 真实各分支质量、来源、隔离、时延 | [frozen plan](./artifacts/quality-plan.json) 测试前冻结；[quality](./artifacts/quality-results.json) 5×8＋独立 BM25 8 题；HyDE 7/8、其余 8/8，均达≥0.75、越权 0、冷暖预算通过；用户核定来源 | verified-live |
| V07 | queued/ready/failed、配置版本、刷新/重启恢复，query 不重建 | HTTP 13/13；[browser](./artifacts/browser.json) 11 个捕获：状态、query/index 保存、consumer 恢复、API 重启、chunks、上传 queued→ready；SQL revision/原子性回归 | verified-local + live |
| V08 | 恢复 SQL→全新 Chroma，全量 manifest/回收，无旧 fallback | [replica rebuild](./artifacts/replica-rebuild.json) 两原用户 ready；真实故障修复反复重建；[target execution](./artifacts/target-execution.json) 再次受控全量重建；最终 collection 仅 active 4 个 | verified-live |
| V09 | 回归、Ruff/build、docs/diff，边界透明 | 后端 529 passed / 1 warning；前端 29 passed；TypeScript/Vite build、app/tests/scripts/ops Ruff、docs/diff 通过；[checks](./artifacts/checks.json) | verified-local |

本地核心测试：`test_e5_query_authority.py`、`test_e5_reconciliation.py`、`test_e5_settings.py`、`test_e5_guard.py`、既有 projection/branches/runner/OpenAPI，以及前端 client refresh 测试。完整后端第一次暴露缺失 OpenAPI typed response，修复后 529 通过；旧 527/1 不是最终成功结果。前端新增并发 refresh 恢复/不持久化本地 token 验证。

## 质量和性能

计划冻结于 `2026-09-14T06:59:58.942125+00:00`，测试 `07:00:48.365294`→`07:04:30.539816 UTC`。计划 SHA-256 `d3a10400d2470e53dd229d36bb68e0ab836bd1702760e8e0918da3d8a21cd4f4`，语料 manifest `e9532e5ebdd4b376a62790abea895b619fcc19f08df47ac9f861e7a25a7f5e25`。6 知识＋2 笔记来源由 Codex 对照 SQL 标注，用户测试后确认；非独立盲评，详见[来源表](./quality-labels-review.md)。

| 分支 | hit@5 | 首请求秒数 | 后续 7 请求样本 p95 秒数 | 预冻结暖样本上限 |
|---|---:|---:|---:|---:|
| vector | 8/8 | 3.141 | 3.906 | 10 |
| vector + BM25 | 8/8 | 2.594 | 3.906 | 10 |
| HyDE | 7/8 | 6.218 | 7.672 | 30 |
| reranker | 8/8 | 14.953 | 6.047 | 60 |
| combined | 8/8 | 7.641 | 8.516 | 60 |

独立 BM25 8/8；HyDE Q4 漏检保留。最低质量门槛 0.75、首请求预算 180 秒、越权零命中均达标。样本 p95 为 nearest-rank 最大值，不是总体 p95；首请求不保证所有缓存冷启动。事件循环最大间隔 0.782 秒，空用户隔离通过。本结果不证明广泛语料质量、答案正确率或持续吞吐。

原目标 smoke 固定 UTF-8 `计算机技术专业的课程有哪些？`，vector/BM25/HyDE/rerank/combined/empty 6/6；耗时 11.235/4.172/8.125/19.594/8.781/1.266 秒，非空各 5 hits、空用户 0。smoke 不另作质量判据。

## 复现与限制

命令见 [ops README](../../backend/ops/e5/README.md)。副本已停止，复跑需新目录/副本及即时 preflight；历史输出不得覆盖。应用文件与 target execution 的 code manifest 一致；ops 后续仅格式化/bootstrap noqa 及归档工具增补。最终文件 SHA 见[索引](./artifacts/evidence-index.json)。

原生 Linux/macOS、生产部署/RPO/RTO、完整 main/Redis/MCP、高并发和广泛盲测未执行。历史 6 个 enrichment dead-letter 保留。早期乱码 query、坏 dump、过期 preflight、失败资源删除及依赖拒连维持历史记录；本轮无豁免，未启动 E6。
