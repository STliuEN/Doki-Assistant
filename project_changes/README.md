# 历史变更档案

本目录按日期保存功能方案、变更日志、开发记录和测试记录。

这些文件描述的是当时的代码状态，其中可能包含已经删除的文件、旧端口、旧架构和已完成的待办。它们用于追溯设计过程，不作为当前运行和开发说明。

当前文档入口：

- [项目 README](../README.md)
- [文档索引](../docs/README.md)
- [当前架构](../docs/project_develop.md)
- [下一阶段路线图](../docs/roadmap_next.md)
- [架构重写计划](../docs/architecture_rewrite_plan.md)

## 2026-08-24 标准 Skill 核心重构

本目录先记录需求与门禁，随后持续记录同主题实现。当前已形成标准 package 的 A 级和有限 B 级开发支持，包含 parser/Storage/领域/API/UI/seed、资源编辑、CapabilityGrant、SkillRunBinding、private 过滤、多实例 reconcile、OpenAPI 和旧运行目录退出。durable import、per-user scope、累计 token 预算、C 级隔离执行和完整真实 E2E 仍未完成；`SKILL-GATE` 与 `ARCH-GATE` 均未通过，工作包 `7-10` 继续保留并冻结。

| 主题 | 方案 | 变更记录 | 验证记录 |
|------|------|----------|----------|
| 标准兼容 Skill 单轨重构 | [plan](./2026-08-24-standard-skill-core-rewrite/plan.md) | [change log](./2026-08-24-standard-skill-core-rewrite/change-log.md) | [test record](./2026-08-24-standard-skill-core-rewrite/test-record.md) |

## 2026-08-20 架构重写计划

本批次只更新活文档和计划，不代表架构重写已经开始。可靠性优先的 `AR-0` 至 `AR-6` 和 `ARCH-GATE` 说明见[架构重写计划](./2026-08-20-architecture-rewrite-plan/plan.md)；工作包 7-10 的产品 UI/API 在门禁通过前冻结，但任务、观测、投影和恢复底座属于门禁前置基础。

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

工作包 7“回答引用与一键沉淀”、8“知识处理任务中心”、9“统一搜索”和 10“运行追踪、导出与恢复”仅保留在[改进执行计划](../docs/improvement_execution_plan.md)中，本批次未实施，也没有创建完成归档。
