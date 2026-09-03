# 当前执行计划

`docs/` 一级目录只保留当前架构执行所需的计划、蓝图和阶段记录模板，避免把历史方案或已完成批次误认为当前任务。

## 当前事实源

1. [架构重写计划](./architecture_rewrite_plan.md)：唯一的 AR/SK 状态、依赖、门禁、当前队列和关闭条件。
2. [最终重构蓝图](./architecture-target-blueprint-2026-08-26.md)：单机局域网、单 FastAPI、单 MySQL、SQL runner、Chroma RAG 和分阶段目标。
3. [阶段执行记录模板](./stage-execution-record-template-2026-08-26.md)：每阶段的 `plan.md`、`change-log.md` 和 `test-record.md` 格式。
4. [架构重构执行交接手册](./architecture-execution-handoff-2026-08-26.md)：交接入口、唯一执行路径、停线条件、回滚规则和 E2 执行/关闭记录。

## 当前状态

- E1/AR-0/SK-0 已于 2026-08-27 经用户明确确认关闭；E2/S1/AR-1 已于 2026-08-28 获用户授权、完成实现与真实隔离验证并经用户批准关闭。
- E1 的隔离依赖、故障矩阵、恢复、characterization、最终回归和事故边界位于 [`project_changes/2026-08-27-e1-ar0-evidence/`](../project_changes/2026-08-27-e1-ar0-evidence/)，批次状态为 `已关闭`。
- E2 的边界、隔离拓扑、UoW/job 不变量、任务顺序、证据矩阵和关闭确认位于 [`project_changes/2026-08-28-e2-ar1-sql-foundation/`](../project_changes/2026-08-28-e2-ar1-sql-foundation/)；该批真实依赖和最终门禁已记录，状态为 `已关闭`。
- P0-0 至 P0-6 已完成 E1 范围收口；这不表示 `SKILL-GATE`、`ARCH-GATE` 或任何发布门禁已经通过。
- E2 已完成代码、SQLite/fixture、真实 migration、MySQL/容器、恢复和 kill/restart 验证；不迁移/删除现有数据，也不清理 E1 证据资源。关闭后 E2 容器已停止，volume、network 和证据保留。
- E2 的统一 SQL schema、UoW/durable runner live 验证、恢复对账和关闭已收口；E3 FastAPI 认证接管、2 个测试用户迁移、授权审计和恢复对账已完成，用户于 2026-09-01 明确回复 `批准关闭 E3`，当前状态为 `已关闭`；E4/AR-3 已于 2026-09-02 获执行确认并进入 `实施中`，当前进行独立 allowlist/preflight、分批 inventory 和 shadow 迁移准备；Skill/RAG 收敛、单机部署和最终恢复验收仍未收口，新功能发布继续冻结。

## 历史归档

已完成批次、评审报告、运行说明、专项规格和故障手册统一位于 [`archive/2026-08-26/`](./archive/2026-08-26/)。归档内容只用于追溯，不是当前执行入口；与当前计划冲突时，以本目录列出的四份核心文档和本 README 为准。

阶段执行证据继续保存在 [`project_changes/`](../project_changes/) 对应批次目录。
