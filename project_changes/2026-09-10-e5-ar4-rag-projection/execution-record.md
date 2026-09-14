# E5 执行记录

- 执行日期：2026-09-14
- 结果：E5 全量重建完成；两位 canonical 用户均为 `ready`，队列中无 queued 任务。
- 数据目标：`doki-e4-20260903-mysql` / `doki_e4` / `127.0.0.1:33427`。目标 schema revision 为 `20260914_0009_e5_rag_runtime`。
- 写入边界：只使用 E5 target 的专用应用账号和 E5 隔离 Chroma 工作区；没有设置 MySQL 全局 `read_only`、`super_read_only`，没有锁库、停主机服务或修改 `new-api`。
- 模型：本机 Ollama `qwen3-embedding:0.6b`，digest `ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d`，维度 1024。
- 投影：4 个 active collection；有内容用户生成 57 个 knowledge chunks 与 11 个 notes chunks；无内容用户生成空 collection，查询返回正常空结果。
- 恢复证据：[restore-rehearsal.json](../../.runtime/e5-20260914/restore-rehearsal.json)。二进制备份 SHA-256 为 `30aa9eada7a60285859bb4191792bb4acf199211bd38ecade401fd7d4fa20d18`，独立恢复逐表行数和数据摘要一致。
- 旧文件 `.runtime/e5-20260914/target-before-e5.sql` 保留但标记为无效：早期 PowerShell 文本管道导出没有保留换行，不能作为恢复证据。有效备份是在 additive schema 完成后、consumer 启动前生成的，因此不是 schema 变更前快照。
- 偏差：先前曾复用旧 E4 preflight 生成准备记录，未用于本次真实 consumer 授权；本次消费使用 E5 target、独立隔离路径和新运行参数。目标 additive migration 已先执行，随后才生成有效备份，故恢复演练验证的是 post-schema 状态。

## 验证

- E5/Chroma/API 专项：24 passed；查询分支专项新增 3 项，均通过。
- E5 执行与真实 Chroma/故障用例：9 passed。
- 相关后端回归：514 passed，Ruff 和 compileall 通过。
- 前端：28 passed，生产构建通过。
- 真实查询：有内容用户返回 20 个命中；无内容用户返回 0 个命中；未使用旧 Chroma fallback。
- 分支证据：[e5-vector-bm25-hyde.json](../../.runtime/e5-20260914/e5-vector-bm25-hyde.json) 和 [e5-reranker.json](../../.runtime/e5-20260914/e5-reranker.json)；向量、BM25、HyDE、reranker live case 均为 ready/10 hits。
- 分支自动测试：BM25 使用真实 `rank_bm25.BM25Okapi`，HyDE 验证 Ollama `/api/generate` 合同，reranker 验证 chunk identity 保留。
- 主机边界：`new-api` 容器仍 running，restart count 为 0；E5 target `@@global.read_only=0`、`@@global.super_read_only=0`。

## 尚未作为完成条件宣称

真实分支已形成证据；仍需用户审阅这些结果后，才能正式关闭 E5。
