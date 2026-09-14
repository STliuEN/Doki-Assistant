# E5 最终收口判定（2026-09-14）

**阶段状态：`已关闭`。C1–C6 与 V01–V09 在 Windows 本机、单实例、runner 并发 1 的范围内全部通过，无剩余 E5 阻塞项，无验收豁免。** E6 未启动，`SKILL-GATE`、`ARCH-GATE` 和产品工作包 7–10 继续冻结。

用户已确认 Q1–Q7，并明确要求“修改更新相关文档 执行e5收口”“执行剩下所有的缺口直到最终的e5执行判定”。本结论依据持续执行/收口授权和补齐后的技术证据作出，不把授权当作技术豁免。用户随后回复“确认这 8 条来源映射（推荐）”，补齐 F6 来源人工核定。标签由 Codex 在测试前对照 SQL 原文冻结，用户确认发生在测试后，**不是独立盲标或测试前人工审定**。

代码基线为 `aa3adf4b8d89a8e8f6bb62099cdb4b3e4fbbd5e5` 加本次未提交工作树。最终文件摘要见[证据索引](./artifacts/evidence-index.json)，机器判定见 [closure-review.json](./artifacts/closure-review.json)。先前阻塞报告原样保留在 [history](./artifacts/history/)，Ollama connection refused 是已恢复的历史故障。

## 1. 关闭项与证据

| 项目 | 实现与实际验收 | 判定 |
|---|---|---|
| C1 查询权威和隔离 | 独立 SQL 快照、全部候选 source/chunk/digest 校验、返回前复核、知识/笔记成组健康、认证 tool context 必需。伪造候选、在途删除/配置/重建负例回归，以及真实副本 owner/content/foreign-filter/tool 验证通过 | 通过；V02/V03/V06 |
| C2 生命周期与清理 | OS attempt lock、retired tombstone、启动/周期 reconciliation、清理重试。真实 MySQL heartbeat、第二进程锁拒绝、kill→租约回收 fence 1→2→ready、取消通过；目标无 staging/待清理/未登记 collection | 通过；V03/V04/V08 |
| C3 故障合同 | 全局统一 E5 503；修复任务去重，查询模型故障不误触发重建。真实 SQL/Chroma 路由故障 9 项、真实文件损坏/Windows ACL 拒读 2 项、TCP HTTP 合同 13 项通过，认证/会话/原文保持可用 | 通过；V02/V05 |
| C4 配置与浏览器 | SQL query/index 配置及乐观版本、状态/重建 API、轮询、失败重试、真实 chunks。浏览器覆盖 queued/building/ready/failed、保存/刷新、consumer 恢复与 API 重启、上传 queued→indexed；修复刷新会话恢复 | 通过；V07 |
| C5 真实检索与时延 | 本机真实 embedding、HyDE、BM25、CUDA reranker；冻结 8 条来源样本及阈值，用户确认来源。所有分支达到 source hit@5≥0.75、隔离零泄露及冷/暖样本预算 | 通过；V06 |
| C6 受控执行与完整恢复 | E5 单目标 allowlist、即时 preflight、先二进制备份再本轮目标写入、真实进程锁。恢复副本 41 表 counts/digest 一致并向全新 Chroma 重建；空库/历史 populated 库真实 Alembic 升级 2 项通过 | 通过；V01/V08 |

在途删除、乱序发布、清理失败和线程竞争等使用 SQLite＋真实 Chroma＋合成 embedding 的确定性测试；进程 kill/heartbeat/fence 和故障路由使用真实 MySQL 副本。没有把全部负例宣称为原目标破坏性试验。详见[测试记录](./test-record.md)。

## 2. 最终目标状态

目标 `doki-e4-20260903-mysql`，`127.0.0.1:33427/doki_e4`，server UUID `0c0d3e33-a743-11f1-af41-ea47e0ceb469`。schema `20260914_0009_e5_rag_runtime`，41 表，52 项外键检查孤儿数均为 0。最终重建 16.953 秒，两项 `e5.rag.rebuild` 均 succeeded。

| 用户 | SQL 状态 | 知识 / 笔记源 | 知识 / 笔记 chunks | active / staging |
|---|---|---|---|---|
| 内容用户 `2e2c05f2…` | ready，revision 4，query_revision 2 | 6 / 7 | 57 / 11 | 2 / 0 |
| 空用户 `f4aff4a5…` | ready，revision 5，query_revision 2 | 0 / 0 | 0 / 0 | 2 / 0 |

SQL 原文 artifact 与笔记内容摘要保持一致。4 个 active collection 全量校验通过，运行期被替代的 E5 generation 已回收，无未登记 collection。旧 Chroma、sidecar、原始输入、E1–E4 证据和备份继续保留。6 个历史 `e4.note.enrich` dead-letter 仍在原处，不能写成“所有历史任务健康”。最终原目标真实分支 smoke 6/6 通过，查询前后 SQL 清单相同。

## 3. 质量与性能范围

计划在 `2026-09-14T06:59:58.942125+00:00` 冻结，SHA-256 `d3a10400d2470e53dd229d36bb68e0ab836bd1702760e8e0918da3d8a21cd4f4`；测试在其后开始，未事后调整阈值。所有分支 top-k=5。

| 分支 | 来源命中 | 首请求秒数 | 后续 7 请求样本 p95 秒数 | 暖样本预算秒数 |
|---|---:|---:|---:|---:|
| vector | 8/8 | 3.141 | 3.906 | 10 |
| vector + BM25 | 8/8 | 2.594 | 3.906 | 10 |
| HyDE | 7/8 | 6.218 | 7.672 | 30 |
| reranker | 8/8 | 14.953 | 6.047 | 60 |
| combined | 8/8 | 7.641 | 8.516 | 60 |

独立 BM25 为 8/8。HyDE 漏检 Q4 软件工程授权/招生年份资料；保留漏检，仍满足预冻结 0.75 门槛。首请求上限 180 秒；该请求包含当次加载，不代表清空所有缓存。暖样本 p95 使用 nearest-rank，在 7 个样本中等于最大值，不是总体 p95、持续吞吐或跨语料质量保证。事件循环最大观测间隔 0.782 秒；真实长任务 heartbeat 另行通过。

实际模型：Ollama `qwen3-embedding:0.6b`（1024 维）、`qwen3:0.6b`，本地 `qwen3-reranker-4b`；reranker 使用 CUDA、dtype auto、max_length 2048、batch 1。完整模型文件摘要、source/chunk/generation 和正文 SHA 见[质量证据](./artifacts/quality-results.json)。未下载模型或修改旧 sidecar。

## 4. 检查、主机边界与历史偏差

最终应用回归：后端 **529 passed / 1 warning**，前端 **29 passed**，TypeScript/Vite build、Ruff、文档和 diff 门禁通过。警告为 SQLite/Python 3.12 datetime 适配弃用。门禁命令及证据来源见 [checks.json](./artifacts/checks.json)。

HTTP/浏览器验收使用生产 routers、middleware、异常处理器和真实 SQL/Chroma 的 scoped FastAPI harness，只在该 harness 关闭限流以隔离现有 Redis 不可用因素。它不验证完整 main lifespan、MCP 启动或 Redis/最终部署；既定 E8 范围不被此次关闭覆盖。原生 Linux/macOS、生产 RPO/RTO 和高并发未验收。

未设置 MySQL 全局只读/全库锁，未连接 host 3306，未改变 `new-api` 连接/权限或重启主机既有服务。目标全局只读标志均为 0。`new-api` 容器身份、StartedAt `2026-09-13T23:07:05.767008989Z`、restart_count=0/running 一致；这不是整机负载/延迟测量。临时 consumer 正常停止，API、Vite、专属浏览器会话及本轮两个副本容器已停止；卷、网络及成功/失败资源保留，见 [task-cleanup.json](./artifacts/task-cleanup.json)。原目标仍运行。

历史偏差继续保留：早期 `target-before-e5.sql` 因 BOM/换行损坏无效；有效 `target-e5-schema-before-consumer.sql` 仅为升级后/consumer 前快照；早期消费复用过期 E4 preflight，缺新进程锁闭环；前序曾删除 restore-test-1/2 失败容器/卷；旧两份 query 为 `?? ?? ??` 的 JSON 无中文质量效力。本轮新的先备份、即时 preflight、进程锁及完整恢复证据补齐当前门槛，**不追认或改写历史执行顺序**。

当前 E5 阻塞清单为空。已知 HyDE 漏检、小样本时延边界、历史 enrichment 死信和执行偏差如实保留。后续阶段按各自计划另行启动。
