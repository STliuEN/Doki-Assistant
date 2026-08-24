# 架构重写计划文档化变更记录

日期：2026-08-20

状态：完成（仅文档）

## 2026-08-20 可靠性优先复审修订

- 将目标拓扑从“可选 worker/单体进程”修订为同一代码库下的 API 与 worker 独立故障域。
- 新增数值化 SLO、RPO、RTO、队列、索引新鲜度、容量和备份保留门槛。
- 将 AR 顺序重排为：可靠性契约与 P0 止血 -> 运行时隔离与 durable job -> 认证迁移 -> 可恢复关系迁移 -> canonical Storage/索引投影 -> 业务模块化 -> 灰度切换/HA/停用。
- 将 durable outbox/job、lease/fencing、重试/DLQ/背压、UoW、SSE replay、分层 readiness 和依赖故障矩阵前移到 AR-0/AR-1。
- 将认证撤销/审计持久化、snapshot/change capture、checkpoint/delta replay、restore-forward 回滚和 N/N-1 schema 兼容写入 AR-2/AR-3 门禁。
- 将 Storage immutable object、generation manifest、Chroma quarantine/version fencing/rebuild 和唯一投影 owner 写入 AR-4 门禁。
- 将 canary、连接 drain、MySQL PITR/故障转移、Redis 丢失、磁盘满、进程 kill 和组合故障演练写入 AR-6/ARCH-GATE。
- 明确工作包 8/10 的产品 UI/API 仍冻结，但其任务、观测和恢复底座不冻结，必须作为架构前置基础实施。
- 指定本文件为 AR 阶段和 ARCH-GATE 的唯一事实源，路线图与执行计划改为摘要/状态入口。

## 已更新

- 新增 `docs/architecture_rewrite_plan.md`，定义 `AR-0` 至 `AR-6`、数据权威矩阵、`ARCH-GATE` 和回滚策略。
- 将 `docs/roadmap_next.md` 的表述从“渐进式重构、不进行一次性重写”调整为分阶段、可回滚的架构重写。
- 将工作包 7-10 的状态改为 `ARCH-GATE` 前冻结，并把下一步改为 `AR-0`。
- 在根 README、文档索引、当前架构和开发运行说明中区分当前三进程过渡态与目标架构。
- 将 FastAPI 缓存失效时到 Django 用户状态校验的临时依赖补入当前架构说明。
- 补充 MySQL、Redis、Storage、Chroma 和本地配置的当前角色与目标权威性。

## 未执行

- 没有修改 Python、TypeScript、PowerShell 或 YAML 业务实现。
- 没有执行任何 migration、数据库连接、数据迁移、删除或服务切换。
- 没有声称任何 `AR-*` 阶段或 `ARCH-GATE` 已完成。
