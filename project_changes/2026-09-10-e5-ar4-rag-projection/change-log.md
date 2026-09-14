# E5 变更日志

状态：实施中

| 时间 | commit/文件/schema | 变更 | 原因 | 影响 | 回滚点 | 负责人 | 证据 |
|---|---|---|---|---|---|---|---|
| 2026-09-10 | docs/architecture_rewrite_plan.md、architecture-target-blueprint-2026-08-26.md、architecture-execution-handoff-2026-08-26.md | 同步 E4 已关闭、E5 待你确认 | HEAD a2d7381 已有 E4 关闭记录，三份主文档仍写实施中 | 修正入口状态；未改变已有架构决策 | 本轮前 HEAD 与 git diff | Codex | E4 artifacts/e4-closure-20260910.json |
| 2026-09-10 | 本目录 plan.md、change-log.md、test-record.md | 建立 E5 审查、决策树、任务依赖、故障/恢复合同与验收矩阵 | 阶段概要缺少执行顺序和关键失败窗口 | 供 grilling 与实施前审阅，待决方案未生效 | 本轮新增文档 diff | Codex | E5-P01/E5-P02 |
| 2026-09-10 | 本目录 plan.md、test-record.md | 补充 SQL/Chroma fence 边界、原文变更发布缺口、完整 scope generation、降级吞错与环境/命令基线 | 两项独立只读核验发现具体执行缺口 | 明确必做实施项与启动前检查；未运行应用或消费任务 | 本轮新增文档 diff | Codex | E5-P02/E5-P04 |
| 2026-09-10 | 交接手册与本目录文档 | 修正行尾空格并完成文档门禁 | 首轮 diff 检查发现新行空格 | 199 Markdown 文件、205 本地链接及 diff 检查通过 | 本轮 diff | Codex | E5-P03 |
| 2026-09-10 | 三份主文档与本目录 plan.md/test-record.md | 写回 Q1/Q2 按建议、Q3 全量迁移且不考虑旧访问性；提出 Q4-Q7 | 用户已回答第一轮设计前沿 | 固定每用户隔离、索引/查询配置分类及首次迁移 RAG 503；移除健康旧 RAG 连续服务/自动回退建议 | 本轮文档 diff；第一轮问题保留确认记录 | Codex | E5-P05；plan.md 第 4 节 |
| 2026-09-14 | 本目录 plan.md、change-log.md、test-record.md | 写回 Q4-Q7 全部按建议，并进入 E5 实施中 | 用户已确认全部执行建议 | 固定相关停写、知识/笔记成组开放、全量失败阻断、日常重建 503 | 本轮前 E5 计划版本 | Codex | E5-P06 |

## 明确未做

- 未修改业务代码、SQL schema、任务状态、模型配置或 Chroma collection。
- 未连接业务数据库、启动/停止应用、运行迁移或故障注入。
- 未使用现有凭据、启动 E5 consumer、清空 E4 queued job 或删除旧输入/中间材料。
- 未重跑 E4 全量测试；历史结果不记为本轮通过。

| 2026-09-14 | backend/app/rag/projection, business_authority.py, knowledge/note paths, API/UI | Implemented E5 SQL snapshot to per-user/per-kind generation projection, source/config drift fail-closed checks, application-scoped write gate, and async UI status handling | Q1-Q7 decisions and host boundary correction | E5 implementation can be locally checked without touching live services; real migration/runtime remains gated | E5 code diff and isolated test records | Codex | E5-L01..E5-L08 |
