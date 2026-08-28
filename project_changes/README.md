# 历史变更档案

本目录按日期保存功能方案、变更日志、开发记录和测试记录。

这些文件描述的是当时的代码状态，其中可能包含已经删除的文件、旧端口、旧架构和已完成的待办。它们用于追溯设计过程，不作为当前运行和开发说明。

当前文档入口：

- [项目 README](../README.md)
- [文档索引](../docs/README.md)
- [当前架构归档](../docs/archive/2026-08-26/project_develop.md)
- [下一阶段路线图归档](../docs/archive/2026-08-26/roadmap_next.md)
- [架构重写计划](../docs/architecture_rewrite_plan.md)

## 2026-08-28 E2 AR-1/S1 统一 SQL 基础准备

本批已完成 E1 关闭复核、现有 Alembic/SQLAlchemy/UoW/outbox/backup 静态盘点，并提交 E2 的隔离拓扑、schema/UoW/job/runner 不变量、任务顺序、回滚边界和证据矩阵。用户已完成 Q1-Q91 grilling 并明确授权实施；当前状态为 `实施中`，后续写入仅限批准的 E2 隔离资源和合成数据。

| 主题 | 方案 | 变更记录 | 验证记录 | 补充盘点 |
|------|------|----------|----------|----------|
| E2 AR-1/S1 统一 SQL 基础与 durable runner | [plan](./2026-08-28-e2-ar1-sql-foundation/plan.md) | [change log](./2026-08-28-e2-ar1-sql-foundation/change-log.md) | [test record](./2026-08-28-e2-ar1-sql-foundation/test-record.md) | [目标 Schema Ownership 草案](./2026-08-28-e2-ar1-sql-foundation/schema-map.md)、[当前 SQL 与运行时盘点](./2026-08-28-e2-ar1-sql-foundation/current-sql-inventory.md) |

## 2026-08-27 E1 AR-0/SK-0 真实依赖与恢复证据

本批已完成隔离 MySQL/Chroma、故障注入、备份恢复、API/UI/Prompt/route characterization、隔离完整 pytest `284 passed` 和 offline benchmark smoke `4/4`、regression `117/117`；用户于 2026-08-27 明确确认关闭，当前状态为 `已关闭`。历史失败、误连事故和无法绝对证明数据库/Redis 零写入的限制继续保留；原生 Linux/macOS 为 `out-of-scope/frozen`，真实模型质量不属于 E1 门禁。E2/AR-1 已于 2026-08-28 获得实施授权并进入 `实施中`，仍未宣称完成。

| 主题 | 方案 | 变更记录 | 验证记录 | 补充证据 |
|------|------|----------|----------|----------|
| E1 AR-0/SK-0 真实依赖与恢复证据 | [plan](./2026-08-27-e1-ar0-evidence/plan.md) | [change log](./2026-08-27-e1-ar0-evidence/change-log.md) | [test record](./2026-08-27-e1-ar0-evidence/test-record.md) | [威胁模型](./2026-08-27-e1-ar0-evidence/threat-model.md)、[characterization 矩阵](./2026-08-27-e1-ar0-evidence/characterization-matrix.md)、[平台限制](./2026-08-27-e1-ar0-evidence/platform-limitations.md) |

## 2026-08-25 工作计划与代码现实校准

本批只校准 2026-08-25 当时的活计划与代码现实，不修改业务实现，也不表示任何 AR/SK 门禁已经通过。当时停留在 `AR-0 + SK-0`：发布原子性、Registry 单包隔离、授权撤销/审计、Skill OpenAPI、Chroma 安全恢复、通用 worker/UoW 和真实依赖基线仍是阻断项。本地 A/B `SKILL-GATE`、本地 `ARCH-GATE`、可选 `EXEC-SKILL-GATE` 与 `PUBLIC-HA-GATE` 相互分开；工作包 `7-10` 只暂停到本地门，通过本地门不会解锁 C 级或公网/HA。当前阶段状态和门禁定义以[架构重写计划](../docs/architecture_rewrite_plan.md)为唯一事实源。

| 主题 | 方案 | 变更记录 | 验证记录 |
|------|------|----------|----------|
| 工作计划与代码现实校准 | [plan](./2026-08-25-plan-reality-alignment/plan.md) | [change log](./2026-08-25-plan-reality-alignment/change-log.md) | [test record](./2026-08-25-plan-reality-alignment/test-record.md) |

## 2026-08-24 标准 Skill 核心重构

本目录记录了标准 package A 级与有限 B 级的实现切片，包括 parser、content-addressed Storage、领域/API/UI、固定 seed、资源编辑、CapabilityGrant、SkillRunBinding、private 过滤和 revision/outbox 机制；它不是完成声明。缺失或损坏 package 仍可能破坏发布与 Registry 健康，授权撤销/审计、Skill OpenAPI、Storage staging/GC、durable import、per-user scope、累计预算、真实 A/B E2E 和迁移对账均未闭环，因此不能声称多实例一致性、统一 stale `503` 或 OpenAPI 已完成。旧运行目录被提前删除且固定 seed 已存在，也不等于通用 Legacy inventory、迁移器和零数据证明完成。该批 A/B 证据进入本地 `SKILL-GATE`；C 级与公网/HA 分别进入独立门禁，工作包 `7-10` 只暂停到本地 `ARCH-GATE`。

| 主题 | 方案 | 变更记录 | 验证记录 |
|------|------|----------|----------|
| 标准兼容 Skill 单轨重构 | [plan](./2026-08-24-standard-skill-core-rewrite/plan.md) | [change log](./2026-08-24-standard-skill-core-rewrite/change-log.md) | [test record](./2026-08-24-standard-skill-core-rewrite/test-record.md) |

## 2026-08-20 架构重写计划

本批次是 2026-08-20 当时的计划文档化记录；“尚未开始”只描述当时状态，不是当前事实。现行状态、`AR-0` 至 `AR-6` 的分层范围，以及本地 `ARCH-GATE`、`EXEC-SKILL-GATE`、`PUBLIC-HA-GATE` 以[活架构重写计划](../docs/architecture_rewrite_plan.md)为准。

| 主题 | 方案 | 变更记录 | 验证记录 |
|------|------|----------|----------|
| 架构重写计划文档化 | [plan](./2026-08-20-architecture-rewrite-plan/plan.md) | [change log](./2026-08-20-architecture-rewrite-plan/change-log.md) | [test record](./2026-08-20-architecture-rewrite-plan/test-record.md) |

## 2026-08-17 大版本改进批次

最终复核：2026-08-18

工作包 1-6 已执行完成。每个工作包按 `日期-主题/` 目录保存方案、变更记录和测试记录：

| 序号 | 工作包 | 方案 | 变更记录 | 测试记录 |
|------|--------|------|----------|----------|
| 1 | 知识库路径 containment | [plan](./2026-08-17-knowledge-path-containment/plan.md) | [change log](./2026-08-17-knowledge-path-containment/change-log.md) | [test record](./2026-08-17-knowledge-path-containment/test-record.md) |
| 2 | 聊天 Markdown 安全渲染 | [plan](./2026-08-17-chat-markdown-security/plan.md) | [change log](./2026-08-17-chat-markdown-security/change-log.md) | [test record](./2026-08-17-chat-markdown-security/test-record.md) |
| 3 | Token 生命周期 | [plan](./2026-08-17-token-lifecycle/plan.md) | [change log](./2026-08-17-token-lifecycle/change-log.md) | [test record](./2026-08-17-token-lifecycle/test-record.md) |
| 4 | 部署与认证可靠性 | [plan](./2026-08-17-deployment-auth-reliability/plan.md) | [change log](./2026-08-17-deployment-auth-reliability/change-log.md) | [test record](./2026-08-17-deployment-auth-reliability/test-record.md) |
| 5 | 版本化数据库迁移 | [plan](./2026-08-17-versioned-database-migrations/plan.md) | [change log](./2026-08-17-versioned-database-migrations/change-log.md) | [test record](./2026-08-17-versioned-database-migrations/test-record.md) |
| 6 | API 与 SSE 合同 | [plan](./2026-08-17-api-sse-contract/plan.md) | [change log](./2026-08-17-api-sse-contract/change-log.md) | [test record](./2026-08-17-api-sse-contract/test-record.md) |

工作包 7“回答引用与一键沉淀”、8“知识处理任务中心”、9“统一搜索”和 10“运行追踪、导出与恢复”保留在[产品路线图归档](../docs/archive/2026-08-26/roadmap_next.md)中，本批次未实施，也没有创建完成归档。
