# 产品路线图

状态：工作包 `1-6` 的保护性切片已完成；工作包 `7-10` 暂停到本地 `ARCH-GATE`

最近复核：2026-08-25

本文只维护产品工作包和 R0-R8 职责映射。阶段状态、依赖、门禁、当前执行顺序和完成证据只在[架构重写计划](./architecture_rewrite_plan.md)维护；当前运行事实见[当前架构](./project_develop.md)。

## 目标架构

本地 `ARCH-GATE` 通过后，项目应具备：

- 一个同源入口和一个 FastAPI 模块化业务单体；API 与 worker 保持独立进程和资源池。
- 一个关系数据写权威；Redis 只保存有 TTL/容量/故障合同的短期状态。
- Storage 保存 immutable canonical objects，Chroma 是带版本、可对账和可重建的 projection。
- 长任务使用 durable job、UoW/outbox、lease/fencing、重试、取消、DLQ 和背压。
- 前端按功能域组织，OpenAPI、SSE、migration 和前端类型进入自动合同检查。

该门只解锁 README 明确的本地档位。C 级 Node/Python 执行需要 `EXEC-SKILL-GATE`；公网、多实例和 HA 需要 `PUBLIC-HA-GATE`。

## R0-R8 职责

R0-R8 是追踪维度，不是另一条阶段链。执行顺序以架构主计划为准。

| 维度 | 职责 | 当前摘要 |
|------|------|----------|
| R0 安全与可靠性 | P0 containment、egress、readiness、SLO/RPO/RTO、备份与故障矩阵 | 路径、渲染、token 等保护切片已落地；Chroma reset 和 Skill 发布安全仍阻断 |
| R1 合同与特征测试 | HTTP/SSE、数据清单、characterization、恢复语义 | 通用 API/SSE 基线存在；Skill 增量合同和真实依赖基线未完成 |
| R2 平台与任务 | settings、UoW、migration、Storage/Vector ports、durable worker | migration 与局部 outbox 已有；通用 worker/UoW/隔离进程协议未完成 |
| R3 身份与认证 | FastAPI 用户权威、角色、会话、撤销、审计和迁移 | token 保护切片存在；身份收敛、角色分离和完整审计未完成 |
| R4 后端模块 | `skills/tools/mcp` 起步的功能域边界 | Skill 首域实现中；其余域等待前置合同 |
| R5 Agent/RAG/投影 | Run 状态、取消、预算、索引状态、重建和对账 | Agent/Skill 切片存在；通用任务、Tool/MCP policy 固定和投影恢复未完成 |
| R6 前端模块 | shared/auth、skills、chat、knowledge、notes 与剩余页面 | 安全渲染、认证和 Skill UI 切片存在；完整拆分/E2E 未完成 |
| R7 质量平台 | unit/API/integration/E2E/benchmark、CI、观测和证据模板 | 从 AR-0 前置启动；当前 Node/npm 与前端/browser R7 已复跑，真实依赖/跨平台矩阵未建立 |
| R8 切换与部署 | 单一入口、本地清理；可选公网 canary/HA/DR | 本地有提前清理切片；公网部分属于 `PUBLIC-HA-GATE` |

## 已完成保护工作包

| 工作包 | 结果 |
|--------|------|
| 1 知识路径 containment | 统一路径校验、链接拒绝和批量预算 |
| 2 聊天安全渲染 | 统一安全 Markdown，拒绝危险 HTML/URL |
| 3 Token 生命周期 | access/refresh、轮换、撤销和前端单一认证状态 |
| 4 部署与鉴权保护 | 移除固定账号/启动副作用，增加生产配置、CORS 和限流 fail-fast |
| 5 版本化 migration | Django migration 与 Alembic baseline 进入版本控制，启动只校验 revision |
| 6 API/SSE 基线 | 通用 envelope、SSE schema 和认证合同测试；Skill 增量合同仍开口 |

这些工作包只表示其原始范围完成，不表示任何 AR/SK 退出门通过。

## 产品队列

工作包 `11` 的本地 A/B Skill 主线属于架构首个 consumer，具体要求见[标准 Skill 规格](./standard_skill_integration_requirements.md)，不在本表重复。

| 工作包 | 功能 | 状态 | 解锁后的专项依赖 |
|--------|------|------|------------------|
| 7 | 回答引用、来源抽屉、一键沉淀为笔记/记忆 | 暂停到 `ARCH-GATE` | 引用权限、SSE/API 合同、模块边界 |
| 8 | 知识处理任务中心 | UI/API 暂停；底层任务前置 | AR-1 durable job、AR-4 projection 状态与对账 |
| 9 | 笔记/记忆/会话/知识统一搜索 | 暂停到 `ARCH-GATE` | AR-3/AR-4 用户隔离、统一数据边界和检索质量基线 |
| 10 | Agent 运行记录、版本化导出与本地恢复 | UI/API 暂停；观测/恢复前置 | run/event 合同、AR-3/AR-4 manifest 和本地恢复 |

本地 `ARCH-GATE` 通过后，建议先实施工作包 7，再按专项依赖选择 8-10。涉及 C 级代码或公网流量的功能仍等待各自独立门禁。

## 工作约束

- 每个变更先建 `project_changes/<日期-主题>/plan.md`，完成后补 `change-log.md` 和 `test-record.md`。
- 不在同一批同时切换认证源、权威 schema、全部 API 和前端路由。
- 不在无备份、dry-run、对账和恢复证据时迁移或删除用户数据、源文件或索引。
- 不以绿色 unit test、生成文件 current、目录删除或已有数据表代替真实退出门。
- 不建立长期 v1/v2、双 Registry、双权威或请求内权威后台任务。
