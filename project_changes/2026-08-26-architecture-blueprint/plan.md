# 2026-08-26 最终重构蓝图文档阶段

日期：2026-08-26  
阶段：S0 文档与决策冻结（AR-0/SK-0 证据仍未通过）
状态：已关闭  
负责人：架构重构协作代理  
审阅/批准人：用户（最终决策人）

## 目标

- 将 q1-q92 已确认边界整理为一份最终重构蓝图。
- 明确单机局域网、单 FastAPI、单 MySQL、SQL 内置单并发 runner 和 Chroma RAG projection 的最终形态。
- 固化 SQL/Chroma/本地调试通道的权威边界、RAG generation 合同、Skill 插口和 AR/SK 门禁。
- 为每个后续阶段记录目标、依赖、产物、测试、回滚和关闭确认。

## 非目标

- 不进入 AR-1，不实现统一 schema、认证迁移、SQL runner、Skill/RAG 重构或删除过渡依赖。
- 不连接、迁移、删除或修改现有 MySQL、Redis、文件目录、MD5 sidecar 或 Chroma 数据。
- 不解冻新功能发布，不启用 C 级 Skill、公网、HA 或多实例能力。

## 依赖与入口条件

- 依据 0826 P0 执行计划和收口报告；当前执行状态为 `AR-0 + SK-0`。
- q85-q92 已回答并确认；最终蓝图和执行交接手册已确认，下一阶段仍需单独建立批次并确认入口。
- 现有 P0 代码和离线证据不构成 AR-0 退出证据。

## 任务清单

- [x] 新建 `docs/architecture-target-blueprint-2026-08-26.md`。
- [x] 将 `docs/architecture_rewrite_plan.md` 收敛为唯一 AR/SK 状态和门禁事实源。
- [x] 将标准 Skill 规格中的 Storage/独立 worker/Redis 目标表述与最终单 SQL/内置 runner 对齐。
- [x] 新建分阶段执行记录模板。
- [x] 记录 q85-q92 决策和单机/SQL/Chroma/RAG/Skill 边界。
- [x] 同步 README、路线图、当前架构、Benchmark/MCP/Memory 文档的目标链接和旧锚点。
- [x] 修正标准 Skill 和安全计划中对 AR-1/C 级 runner 的过渡表述。
- [x] 用户审阅并确认最终蓝图。
- [x] 建立执行交接手册并明确下一阶段 E1/AR-0 入口。
- [ ] 建立 E1/AR-0 单机真实依赖与恢复证据阶段记录。

## 风险与保护

- 旧主计划曾把 Redis 和 Storage 描述为目标依赖；本批已明确其仅为过渡/当前现实，避免继续误导。
- 旧 Chroma、MD5 sidecar 和 Skill 内部结构不可作为最终恢复权威；删除前必须完成 SQL 对账和备份。
- 本地 debug/import/export/rollback 默认开启但不得自动 fallback，正式部署可关闭。

## 退出条件

- [x] 蓝图、主计划和记录模板已生成。
- [x] 阶段顺序、状态枚举、门禁和未收口项已记录。
- [x] 用户确认蓝图内容。
- [x] 本阶段标记为 `已关闭`；E1/AR-0 待建立并确认。

## 回滚方案

本阶段只有文档变更。若用户否决蓝图，保留现有 0826 P0 证据，修订文档并回到 `草案`；不回滚或修改业务代码，不执行数据操作。

## 未完成与阻塞

| 项目 | 状态 | 原因/解除条件 |
|---|---|---|
| E1/AR-0 真实依赖与恢复证据 | 阻塞 | 尚无获批的真实等价 MySQL/Chroma 单机拓扑；建立批次并获批环境后解除。 |
| AR-2 授权闭环 | 未开始 | 仅有 fail-closed 合同，待统一 SQL schema 和 FastAPI 认证阶段。 |
