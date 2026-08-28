# 当前执行计划

`docs/` 一级目录只保留当前架构执行所需的计划、蓝图和阶段记录模板，避免把历史方案或已完成批次误认为当前任务。

## 当前事实源

1. [架构重写计划](./architecture_rewrite_plan.md)：唯一的 AR/SK 状态、依赖、门禁、当前队列和关闭条件。
2. [最终重构蓝图](./architecture-target-blueprint-2026-08-26.md)：单机局域网、单 FastAPI、单 MySQL、SQL runner、Chroma RAG 和分阶段目标。
3. [阶段执行记录模板](./stage-execution-record-template-2026-08-26.md)：每阶段的 `plan.md`、`change-log.md` 和 `test-record.md` 格式。
4. [架构重构执行交接手册](./architecture-execution-handoff-2026-08-26.md)：交接入口、唯一执行路径、停线条件、回滚规则和 E2 待确认清单。

## 当前状态

- E1/AR-0/SK-0 已于 2026-08-27 经用户明确确认关闭；下一阶段 E2/S1/AR-1 已于 2026-08-28 获用户授权，当前 `实施中`。
- E1 的隔离依赖、故障矩阵、恢复、characterization、最终回归和事故边界位于 [`project_changes/2026-08-27-e1-ar0-evidence/`](../project_changes/2026-08-27-e1-ar0-evidence/)，批次状态为 `已关闭`。
- E2 的可审阅边界、隔离拓扑、UoW/job 不变量、任务顺序和证据矩阵位于 [`project_changes/2026-08-28-e2-ar1-sql-foundation/`](../project_changes/2026-08-28-e2-ar1-sql-foundation/)；该目录是准备产物，不构成实施授权。
- P0-0 至 P0-6 已完成 E1 范围收口；这不表示 `SKILL-GATE`、`ARCH-GATE` 或任何发布门禁已经通过。
- 未经用户单独确认 E2，不实施 AR-1、不创建或执行 migration、不迁移/删除数据，也不清理 E1 证据资源。
- 统一 SQL schema、UoW/durable runner、FastAPI 认证接管与授权审计、业务迁移、Skill/RAG 收敛、单机部署和最终恢复验收仍未收口；新功能发布继续冻结。

## 历史归档

已完成批次、评审报告、运行说明、专项规格和故障手册统一位于 [`archive/2026-08-26/`](./archive/2026-08-26/)。归档内容只用于追溯，不是当前执行入口；与当前计划冲突时，以本目录列出的四份核心文档和本 README 为准。

阶段执行证据继续保存在 [`project_changes/`](../project_changes/) 对应批次目录。
