# E5 执行记录

- 日期：2026-09-14；阶段：`已关闭`；代码基线：`aa3adf4` 加本次未提交工作树。
- Q1–Q7 与持续执行/收口授权均已收到；8 条来源由用户在测试后核定。
- 结论见[收口判定](./closure-review.md)，逐项验收见[测试记录](./test-record.md)，摘要见[证据索引](./artifacts/evidence-index.json)。

## 实际执行

| 对象 | 实际动作 / 结果 |
|---|---|
| 原 target | 精确锁定 `doki-e4-20260903-mysql`，容器 ID `35efc06e8a3b377ace2d9ac7e99f9d78ceb8c9a7a73464cc23701413f1d37182`；`127.0.0.1:33427/doki_e4`，UUID `0c0d3e33-a743-11f1-af41-ea47e0ceb469` |
| 本轮写入前备份 | `.runtime/e5-final-20260914/target-before-final.sql`，2,643,151 bytes，SHA-256 `c867e54467866b67347517d08add1a647d879524a306bcdcf724ab729f4167cf`；二进制传输，先于本轮目标写入 |
| 最终受控执行 | 单目标 E5 allowlist、即时 preflight、真实 SQL 进程锁；持久配置 pin reranker digest，提交两用户重建；并发 1、lease 60 秒/heartbeat 15 秒 |
| 重建结果 | 16.953 秒，2 个 `e5.rag.rebuild` succeeded；runner 正常 drain/停止，无 active job 遗留 |
| 投影与原文 | `.runtime/e5-20260914/chroma-live`；6 知识/7 笔记全覆盖，57/11 chunks；空用户 0/0；两用户 ready，4 active/0 staging |
| 最终只读复核 | 6/6 真实分支 smoke；52 FK 无孤儿，4 collection 与 SQL 复算 chunks/receipt 一致，无未登记 collection，cleanup 仅 retained/deleted |
| 恢复副本 | `doki-e5-accept-d48133c1`，loopback 38486，独立卷/网络、2 GB/2 CPU；恢复 41 表 counts/digest 一致，再从 SQL 原文向全新 Chroma 全量重建，两原用户 ready |
| schema 演练 | 新容器内 `e5_empty` / `e5_populated` 独立数据库真实 Alembic upgrade；历史 populated 数据摘要前后相同 |
| 故障与浏览器 | 新副本用户/合成上传；真实 kill/restart、租约、文件权限/损坏、模型/collection 路由故障和浏览器状态/配置/刷新/重启恢复通过 |

最终内容用户知识 generation `d1c6f595-44d8-4f78-8354-82c4dba96dbf`，笔记 `2e641fea-d37f-4eaa-a3e0-4c23e95fe3c1`；空用户知识 `899abae2-ff10-43fe-a576-2c1e5c24fc60`，笔记 `a4a4e447-3607-4a17-b23d-25dc7786e6d9`。旧 E5 运行期投影按合同回收，受保护旧输入和 sidecar 保留。

## 模型与 UI

真实 `qwen3-embedding:0.6b`、`qwen3:0.6b`、CUDA `qwen3-reranker-4b` 和 BM25 完成冻结 8 样本验收。HyDE 7/8、其余分支与独立 BM25 8/8，均达预冻结 hit@5≥0.75。用户确认来源发生在测试后，不属于独立盲测。见 [quality-results.json](./artifacts/quality-results.json)。

浏览器通过本轮 Vite 18081 连接 scoped API 18050 和新副本。top-k=3、chunk_size=800 保存后，经刷新及 API 进程重启仍保留；上传先显示“已进入索引队列”，消费成功后才显示“索引已就绪”；chunks drawer 显示真实切片。见 [browser.json](./artifacts/browser.json)。

## 收尾与保留

consumer 按停止文件正常退出；API/Vite 核对 PID 和命令后停止，专属 Playwright 会话关闭。本轮副本 `doki-e5-accept-d48133c1` 和首次设置失败的 `doki-e5-accept-8e33af9a` 均停止，卷/网络保留。原目标、既有 new-api、Ollama 及旧恢复容器未被停止。凭据、token、SQL dump、可能含用户输入的浏览器快照留在 `.runtime`。

目标 `read_only=0`、`super_read_only=0`，没有全局只读、全库锁、host 3306 连接或 new-api 连接/权限变更。new-api ID、StartedAt、restart_count=0/running 前后相同。6 个历史 `e4.note.enrich` dead-letter 原样保留，不属于两项 RAG rebuild 结果。

无效 dump、post-schema 才备份、过期 preflight、前序失败资源删除、乱码查询和 Ollama 短暂拒连的历史记录见[收口判定](./closure-review.md)及 [history](./artifacts/history/)。新受控执行与完整恢复补齐当前门槛，不追认过去的程序偏差。E6 未启动。
