# 当前执行计划

`docs/` 一级目录只保留当前架构执行所需的计划、蓝图和阶段记录模板，避免把历史方案或已完成批次误认为当前任务。

## 当前事实源

1. [架构重写计划](./architecture_rewrite_plan.md)：唯一的 AR/SK 状态、依赖、门禁、当前队列和关闭条件。
2. [最终重构蓝图](./architecture-target-blueprint-2026-08-26.md)：单机局域网、单 FastAPI、单 MySQL、SQL runner、Chroma RAG 和分阶段目标。
3. [阶段执行记录模板](./stage-execution-record-template-2026-08-26.md)：每阶段的 `plan.md`、`change-log.md` 和 `test-record.md` 格式。
4. [架构重构执行交接手册](./architecture-execution-handoff-2026-08-26.md)：交接入口、唯一执行路径、停线条件、回滚规则和 E1 立即执行清单。

## 当前状态

- 当前停留在 `AR-0 + SK-0`；S0 文档收束已完成，E1 真实依赖与恢复证据已提交 `待验证`，等待审阅和用户关闭确认。
- E1 批次已经建立并进入 `待验证`；隔离依赖、故障矩阵、恢复和 characterization 证据位于 [`project_changes/2026-08-27-e1-ar0-evidence/`](../project_changes/2026-08-27-e1-ar0-evidence/)。
- 0826 P0-0 至 P0-5 的证据已完成当前环境部分；P0-6 未通过。
- 未经用户确认，不进入 AR-1，不迁移/删除数据，不解冻新功能发布。
- 真实依赖、恢复、授权审计、统一 SQL schema、FastAPI 认证接管、SQL runner、Skill/RAG 收敛和单机验收仍未收口。

## 历史归档

已完成批次、评审报告、运行说明、专项规格和故障手册统一位于 [`archive/2026-08-26/`](./archive/2026-08-26/)。归档内容只用于追溯，不是当前执行入口；与当前计划冲突时，以本目录列出的四份核心文档和本 README 为准。

阶段执行证据继续保存在 [`project_changes/`](../project_changes/) 对应批次目录。
