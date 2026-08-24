# 架构重写计划文档化

日期：2026-08-20

状态：文档计划完成；可靠性优先修订完成；架构阶段尚未执行

## 目标

将架构重写明确为工作包 7-10 和后续非 P0 改进的强制前置条件，并按可靠性优先重排 `AR-0` 至 `AR-6`：先完成 SLO/RPO/RTO、故障隔离、持久任务、备份恢复和可证明回滚，再迁移身份、关系数据、Storage/索引和业务模块；同时细化 `ARCH-GATE`、数据权威矩阵、迁移顺序、回滚点和验收门。

## 范围

- 新增 `docs/architecture_rewrite_plan.md`。
- 更新 `README.md`、`docs/README.md`、`docs/project_develop.md`、`docs/development_setup.md`。
- 更新 `docs/roadmap_next.md` 和 `docs/improvement_execution_plan.md` 的阶段状态、依赖和冻结规则。
- 将 API/worker 故障域、durable job、SSE replay、分层 readiness、Storage manifest 和 Chroma quarantine 纳入架构前置基础。
- 将产品工作包 8/10 的 UI/API 冻结与其可靠性底座前置实施明确区分。
- 更新本目录索引，保留可追溯的计划、变更和验证记录。

## 非目标

- 不修改业务代码、依赖、配置或数据库。
- 不连接、读取、迁移或写入现有 MySQL。
- 不执行工作包 7-10 或任何新的产品功能。

## 预期结果

- 当前三进程架构与目标 FastAPI 模块化单体明确区分。
- 目标态改为“一个代码库和关系写权威、多个隔离运行时”，不再把单进程作为可靠性目标。
- 只有通过 `ARCH-GATE` 才能解锁 7-10。
- 每个架构阶段都有入口、产物、验证、回滚和退出门。
- 可靠性合同包含可量化 SLO/RPO/RTO、故障矩阵、迁移 checkpoint/delta replay 和 restore-forward 回滚。
- 未来实施批次可以按同目录三件套记录实际变更。
